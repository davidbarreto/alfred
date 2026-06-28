"""Tag chunks in language_chunks_*.yaml with grammar scope values using Gemini.

For each untagged chunk, classifies it against the scope list defined in
language_grammar_scopes_<code>.yaml. Processes in batches of 50 chunks per
LLM call (compact pipe-separated format) to minimise token usage.

Writes grammar_scope: <value> (or null) back into the chunk YAML.
Chunks with grammar_scope already set (even null) are skipped on re-runs.

After running, execute:
    python db/seeds/seed_grammar_scopes.py   # load scopes to DB
    python db/seeds/seed_language_chunks.py  # sync grammar_scope_id on chunks

Usage:
    GOOGLE_API_KEY=... python db/seeds/tag_grammar_scopes.py
    GOOGLE_API_KEY=... python db/seeds/tag_grammar_scopes.py --lang fr
    GOOGLE_API_KEY=... python db/seeds/tag_grammar_scopes.py --lang fr --force
    GOOGLE_API_KEY=... python db/seeds/tag_grammar_scopes.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import yaml
from google import genai
from google.genai import types

SEEDS_DIR = Path(__file__).parent
BATCH_SIZE = 50
MODEL = "gemini-2.5-flash"

# Only these types carry grammar patterns; plain words are auto-nulled without an LLM call.
_GRAMMAR_TYPES = {"verb_form", "sentence_pattern", "collocation"}


def _scope_path(code: str) -> Path:
    return SEEDS_DIR / f"language_grammar_scopes_{code}.yaml"


def _chunk_path(code: str) -> Path:
    return SEEDS_DIR / f"language_chunks_{code}.yaml"


def _load_scopes(code: str) -> list[dict]:
    path = _scope_path(code)
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text()) or {}
    return data.get(code, [])


def _load_chunks(code: str) -> list[dict]:
    path = _chunk_path(code)
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text()) or {}
    return data.get(code, [])


def _save_chunks(code: str, entries: list[dict]) -> None:
    path = _chunk_path(code)
    header = (
        f"# Vocabulary seed for {code}. Auto-generated — edit freely.\n"
        f"# Re-run generate_language_chunks.py to append more entries.\n"
        f"# seed_language_chunks.py loads this on startup (idempotent).\n"
    )
    path.write_text(
        header + yaml.dump({code: entries}, allow_unicode=True, default_flow_style=False, sort_keys=False)
    )


def _build_scope_index(scopes: list[dict]) -> list[str]:
    """Return ordered list of scope values (index = position in list)."""
    return [s["value"] for s in scopes]


def _build_prompt(scope_values: list[str], batch: list[dict]) -> str:
    scope_line = ", ".join(f"{i}={v}" for i, v in enumerate(scope_values))
    lines = [
        "Assign a grammar scope to each item. Return a JSON array where position = item index and value = scope index (integer).",
        "Use null only when no scope fits at all.",
        "",
        f"Scopes: {scope_line}",
        "",
        "Items (index|type|text|translation):",
    ]
    for i, entry in enumerate(batch):
        lines.append(f"{i}|{entry.get('type', 'word')}|{entry['text']}|{entry.get('translation', '')}")
    return "\n".join(lines)


async def _classify_batch(
    client: genai.Client,
    scope_values: list[str],
    batch: list[dict],
) -> dict[int, str | None]:
    prompt = _build_prompt(scope_values, batch)
    response = await client.aio.models.generate_content(
        model=MODEL,
        contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
        config=types.GenerateContentConfig(
            temperature=0.0,
            response_mime_type="application/json",
        ),
    )
    raw = (response.text or "").strip()
    data = json.loads(raw)

    def _resolve(v) -> str | None:
        if v is None:
            return None
        try:
            scope_idx = int(v)
            return scope_values[scope_idx] if 0 <= scope_idx < len(scope_values) else None
        except (ValueError, TypeError):
            return None

    result: dict[int, str | None] = {}
    if isinstance(data, list):
        for idx, v in enumerate(data):
            result[idx] = _resolve(v)
    elif isinstance(data, dict):
        for k, v in data.items():
            try:
                result[int(k)] = _resolve(v)
            except ValueError:
                continue
    return result


async def _tag_language(client: genai.Client, code: str, force: bool, dry_run: bool) -> None:
    scopes = _load_scopes(code)
    if not scopes:
        print(f"  [{code}] no grammar scope file found — skipping")
        return

    scope_values = _build_scope_index(scopes)
    entries = _load_chunks(code)
    if not entries:
        print(f"  [{code}] no chunk file found — skipping")
        return

    # Split untagged entries: plain words → auto null; grammar types → LLM
    auto_null_indices = []
    classify_indices = []
    for i, e in enumerate(entries):
        if not force and "grammar_scope" in e:
            continue
        if e.get("type", "word") in _GRAMMAR_TYPES:
            classify_indices.append(i)
        else:
            # Never overwrite a real (non-null) grammar scope with auto-null,
            # even when --force is set — word entries can carry manually-assigned scopes.
            if e.get("grammar_scope") is None:
                auto_null_indices.append(i)

    total_untagged = len(auto_null_indices) + len(classify_indices)
    print(f"  [{code}] {len(entries)} chunks, {total_untagged} to process "
          f"({len(classify_indices)} via LLM, {len(auto_null_indices)} auto-null words) | {len(scopes)} scopes")

    if total_untagged == 0:
        print(f"  [{code}] all chunks already tagged — done")
        return

    # Auto-null plain words (no LLM call needed)
    for i in auto_null_indices:
        entries[i]["grammar_scope"] = None

    if not dry_run and auto_null_indices:
        _save_chunks(code, entries)

    # Classify grammar-bearing types via LLM
    tagged = 0
    total_batches = (len(classify_indices) + BATCH_SIZE - 1) // BATCH_SIZE if classify_indices else 0

    for batch_num, batch_start in enumerate(range(0, len(classify_indices), BATCH_SIZE), 1):
        batch_indices = classify_indices[batch_start:batch_start + BATCH_SIZE]
        batch = [entries[i] for i in batch_indices]

        attempt = 0
        result: dict[int, str | None] = {}
        while attempt < 3:
            attempt += 1
            try:
                result = await _classify_batch(client, scope_values, batch)
                break
            except Exception as exc:
                print(f"    attempt {attempt} failed: {exc}")
                if attempt < 3:
                    await asyncio.sleep(3)
                else:
                    print("    giving up on this batch — skipping")

        for local_idx, chunk_idx in enumerate(batch_indices):
            scope_val = result.get(local_idx, None)
            entries[chunk_idx]["grammar_scope"] = scope_val
            if scope_val:
                tagged += 1

        scoped = sum(1 for i in batch_indices if entries[i].get("grammar_scope"))
        print(f"    batch {batch_num}/{total_batches}: {scoped}/{len(batch)} assigned a scope")

        if not dry_run:
            _save_chunks(code, entries)

        await asyncio.sleep(0.5)

    print(f"  [{code}] done — {tagged}/{len(classify_indices)} grammar chunks assigned a scope "
          f"({len(auto_null_indices)} words auto-nulled)")
    if dry_run:
        print(f"  [{code}] dry-run: no files written")


async def main(lang_filter: list[str] | None, force: bool, dry_run: bool) -> None:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Error: GOOGLE_API_KEY env var is not set", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    scope_files = sorted(SEEDS_DIR.glob("language_grammar_scopes_*.yaml"))
    codes = [p.stem.replace("language_grammar_scopes_", "") for p in scope_files]

    if lang_filter:
        codes = [c for c in codes if c in lang_filter]
        if not codes:
            print(f"No scope files matched: {lang_filter}", file=sys.stderr)
            sys.exit(1)

    for code in codes:
        await _tag_language(client, code, force=force, dry_run=dry_run)

    print("\nDone. Next steps:")
    print("  python db/seeds/seed_grammar_scopes.py")
    print("  python db/seeds/seed_language_chunks.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tag vocabulary chunks with grammar scopes")
    parser.add_argument("--lang", metavar="CODES", help="Comma-separated language codes, e.g. fr,ru")
    parser.add_argument("--force", action="store_true", help="Re-tag chunks that are already tagged")
    parser.add_argument("--dry-run", action="store_true", help="Classify but do not write files")
    args = parser.parse_args()
    lang_filter = [c.strip() for c in args.lang.split(",")] if args.lang else None
    asyncio.run(main(lang_filter, force=args.force, dry_run=args.dry_run))
