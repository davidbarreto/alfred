"""Generate language vocabulary chunks via Gemini and write per-language YAML files.

Writes db/seeds/language_chunks_<code>.yaml for each track.
Each file is written incrementally after every batch, so the script is safe
to interrupt and re-run — it resumes from where it left off.

Usage (from the backend/ directory):
    GOOGLE_API_KEY=... python db/seeds/generate_language_chunks.py
    GOOGLE_API_KEY=... python db/seeds/generate_language_chunks.py --lang fr,es
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

TRACKS = [
    {"code": "fr", "name": "French",   "level": "A2", "challenge": "B1"},
    {"code": "ru", "name": "Russian",  "level": "A1", "challenge": "A2"},
    {"code": "es", "name": "Spanish",  "level": "A2", "challenge": "B1"},
    {"code": "it", "name": "Italian",  "level": "A1", "challenge": "A2"},
    {"code": "en", "name": "English",  "level": "B2", "challenge": "C1"},
]

# (cefr_level, target_count) per track level
LEVEL_PLAN: dict[str, list[tuple[str, int]]] = {
    "A1": [("A1", 800), ("A2", 200)],
    "A2": [("A1", 400), ("A2", 450), ("B1", 150)],
    "B1": [("A2", 300), ("B1", 550), ("B2", 150)],
    "B2": [("B1", 200), ("B2", 650), ("C1", 150)],
}

BATCH_SIZE = 50
MODEL = "gemini-2.5-flash"


def _yaml_path(code: str) -> Path:
    return SEEDS_DIR / f"language_chunks_{code}.yaml"


def _load_existing(code: str) -> tuple[list[dict], set[str], list[str]]:
    path = _yaml_path(code)
    if not path.exists():
        return [], set(), []
    data = yaml.safe_load(path.read_text()) or {}
    entries: list[dict] = data.get(code, [])
    seen = {str(e["text"]) for e in entries if e.get("text")}
    # Keep only the most recent texts for dedup hints — 30 is enough to avoid
    # repeating recent entries without bloating every prompt with hundreds of tokens.
    recent = [str(e["text"]) for e in entries[-30:] if e.get("text")]
    return entries, seen, recent


def _save(code: str, entries: list[dict]) -> None:
    path = _yaml_path(code)
    header = (
        f"# Vocabulary seed for {code}. Auto-generated — edit freely.\n"
        f"# Re-run generate_language_chunks.py to append more entries.\n"
        f"# seed_language_chunks.py loads this on startup (idempotent).\n"
    )
    path.write_text(
        header + yaml.dump({code: entries}, allow_unicode=True, default_flow_style=False, sort_keys=False)
    )


async def _generate_batch(
    client: genai.Client,
    lang_name: str,
    cefr_level: str,
    count: int,
    seen_texts: set[str],
    recent_texts: list[str],
    freq_start: int,
) -> list[dict]:
    prompt = f"""Generate {count} {lang_name} vocabulary entries for CEFR {cefr_level}, frequency ranks {freq_start}–{freq_start + count - 1}.

JSON array, each item: type (word/collocation/verb_form/sentence_pattern), text, translation (string), example, example_translation, cefr_level.
Mix: 55% word, 20% collocation, 15% verb_form, 10% sentence_pattern. High-frequency practical vocabulary across topics.
Do NOT repeat: {json.dumps(recent_texts)}
Return ONLY the JSON array."""

    response = await client.aio.models.generate_content(
        model=MODEL,
        contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
        config=types.GenerateContentConfig(
            temperature=0.8,
            response_mime_type="application/json",
        ),
    )
    raw = (response.text or "").strip()
    data = json.loads(raw)

    entries: list[dict] = []
    for i, item in enumerate(data):
        text = str(item.get("text", "")).strip()
        if not text or text in seen_texts:
            continue
        seen_texts.add(text)
        entries.append({
            "type": str(item.get("type", "word")),
            "text": text,
            "translation": str(item.get("translation", "")),
            "example": str(item.get("example", "")),
            "example_translation": str(item.get("example_translation", "")),
            "cefr_level": str(item.get("cefr_level", cefr_level)),
            "frequency_rank": freq_start + i,
        })
    return entries


async def _generate_track(client: genai.Client, track: dict) -> None:
    code = track["code"]
    name = track["name"]
    level = track["level"]

    all_entries, seen_texts, _ = _load_existing(code)
    freq_counter = len(all_entries) + 1

    plan = LEVEL_PLAN.get(level, [("A1", 850), (track["challenge"], 150)])

    print(f"\n[{code}] {name} — {len(all_entries)} existing entries")
    for lvl, target in plan:
        have = sum(1 for e in all_entries if e.get("cefr_level") == lvl)
        label = "(challenge)" if lvl == track["challenge"] else ""
        print(f"  {lvl}{label}: {have}/{target}")

    for cefr_level, target in plan:
        have = sum(1 for e in all_entries if e.get("cefr_level") == cefr_level)
        remaining = max(0, target - have)

        if remaining == 0:
            print(f"  [{cefr_level}] already complete — skipping")
            continue

        print(f"  [{cefr_level}] generating {remaining} entries in batches of {BATCH_SIZE}...")
        batch_num = 0

        while remaining > 0:
            batch_size = min(BATCH_SIZE, remaining)
            batch_num += 1
            attempt = 0
            recent_texts = [e["text"] for e in all_entries[-30:] if e.get("text")]
            while attempt < 3:
                attempt += 1
                try:
                    batch = await _generate_batch(
                        client, name, cefr_level, batch_size, seen_texts, recent_texts, freq_counter
                    )
                    all_entries.extend(batch)
                    freq_counter += len(batch)
                    remaining -= len(batch)
                    _save(code, all_entries)
                    print(f"    batch {batch_num}: +{len(batch)} (total {len(all_entries)}, {remaining} remaining)")
                    break
                except Exception as exc:
                    print(f"    batch {batch_num} attempt {attempt} failed: {exc}")
                    if attempt < 3:
                        await asyncio.sleep(3)
                    else:
                        print(f"    giving up on batch {batch_num} — continuing")

            # Small pause to respect rate limits
            await asyncio.sleep(1)

    print(f"  [{code}] done — {len(all_entries)} total entries")


async def main(lang_filter: list[str] | None) -> None:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Error: GOOGLE_API_KEY env var is not set", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    tracks = TRACKS
    if lang_filter:
        tracks = [t for t in TRACKS if t["code"] in lang_filter]
        if not tracks:
            print(f"No tracks matched: {lang_filter}", file=sys.stderr)
            sys.exit(1)

    for track in tracks:
        await _generate_track(client, track)

    print("\nAll done. Run seed_language_chunks.py (or redeploy) to load into the database.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate language vocabulary via Gemini")
    parser.add_argument(
        "--lang",
        metavar="CODES",
        help="Comma-separated language codes to generate, e.g. fr,es (default: all)",
    )
    args = parser.parse_args()
    lang_filter = [c.strip() for c in args.lang.split(",")] if args.lang else None
    asyncio.run(main(lang_filter))
