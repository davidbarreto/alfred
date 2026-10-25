"""One-off maintenance script: fill task planning fields from tags used before they existed.

Before organizer.tasks had estimate_minutes and context, those hints lived in tags such as
`context:phone` or `30m` / `2h`. This maps them onto the new Alfred-only columns so day planning
can use them. Dry-run by default: it prints a diff and writes nothing until --apply.

- `context:<value>` sets context when the value is one of the planner's contexts
  (computer, phone, home, out, anywhere); other values are reported and left alone.
- A single duration tag (`30m`, `45min`, `2h`, `1.5h`, `1h30m`) sets estimate_minutes. Several
  different duration tags on one task are ambiguous and are reported, not guessed.
- A field that is already set is never overwritten.
- The tags themselves are left on the tasks: tags are mirrored to Notion, and this script only
  touches Alfred-only columns, so nothing is sent to Notion.
- --rename-area-tags additionally renames `area:<name>` tags to plain `<name>` (the planner uses
  plain tag names). A rename that would collide with an existing tag of the same provider is
  skipped. The rename happens in Alfred's database only; Notion's own option list is untouched.

No routines, activities or other personal data are created by this script.

parse_duration_tag(), plan_task_change() and plan_area_renames() hold the decisions and are
covered by tests/test_backfill_task_planning_fields.py with plain Python inputs -- no DB needed.

Usage (from backend/, with the venv active):
    python scripts/backfill_task_planning_fields.py                       # dry run
    python scripts/backfill_task_planning_fields.py --rename-area-tags    # dry run incl. renames
    python scripts/backfill_task_planning_fields.py --apply [--rename-area-tags]
"""
import argparse
import asyncio
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import selectinload

import app.main  # noqa: F401 -- importing every router transitively imports every tables.py,
# which SQLAlchemy needs to fully configure before a flush can resolve any model's FKs/relationships.
from app.db.session import async_session
from app.features.organizer.tags.tables import Tag
from app.features.organizer.tasks.schemas import TASK_CONTEXTS
from app.features.organizer.tasks.tables import Task

_CONTEXT_PREFIX = "context:"
_AREA_PREFIX = "area:"
_HOURS_MINUTES = re.compile(r"^(\d+)h(\d+)(?:m|min)?$")
_DURATION = re.compile(r"^(\d+(?:\.\d+)?)(m|min|h|hr)$")


@dataclass(frozen=True)
class TaskChange:
    task_id: int
    title: str
    estimate_minutes: int | None = None
    context: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def sets_anything(self) -> bool:
        return self.estimate_minutes is not None or self.context is not None


@dataclass(frozen=True)
class TagRename:
    provider_id: str
    old: str
    new: str


def parse_duration_tag(tag: str) -> int | None:
    """Minutes for tags like 30m, 45min, 2h, 1.5h, 1h30m; None for anything else (or zero)."""
    value = tag.strip().lower()
    combined = _HOURS_MINUTES.match(value)
    if combined:
        minutes = int(combined.group(1)) * 60 + int(combined.group(2))
        return minutes or None
    match = _DURATION.match(value)
    if not match:
        return None
    amount = float(match.group(1))
    minutes = round(amount * 60) if match.group(2) in ("h", "hr") else round(amount)
    return minutes or None


def plan_task_change(
    task_id: int, title: str, tags: list[str], current_estimate: int | None, current_context: str | None
) -> TaskChange:
    notes: list[str] = []
    context = None
    estimate = None

    context_values = [t[len(_CONTEXT_PREFIX):].strip().lower() for t in tags if t.lower().startswith(_CONTEXT_PREFIX)]
    known = [c for c in context_values if c in TASK_CONTEXTS]
    for value in context_values:
        if value not in TASK_CONTEXTS:
            notes.append(f"unknown context {value!r} left alone")
    if len(set(known)) > 1:
        notes.append(f"conflicting contexts {sorted(set(known))} left alone")
    elif known and current_context is None:
        context = known[0]
    elif known:
        notes.append(f"context already set to {current_context!r}")

    durations = {m for m in (parse_duration_tag(t) for t in tags) if m is not None}
    if len(durations) > 1:
        notes.append(f"conflicting duration tags {sorted(durations)} minutes left alone")
    elif durations and current_estimate is None:
        estimate = durations.pop()
    elif durations:
        notes.append(f"estimate already set to {current_estimate}")

    return TaskChange(task_id=task_id, title=title, estimate_minutes=estimate, context=context, notes=notes)


def plan_area_renames(tags_by_provider: dict[str, list[str]]) -> tuple[list[TagRename], list[str]]:
    """Renames for `area:<name>` tags plus a note for every one that must be skipped."""
    renames: list[TagRename] = []
    skipped: list[str] = []
    for provider_id, names in tags_by_provider.items():
        existing = {n.lower() for n in names}
        claimed: set[str] = set()
        for name in sorted(names):
            if not name.lower().startswith(_AREA_PREFIX):
                continue
            plain = name[len(_AREA_PREFIX):].strip()
            if not plain:
                skipped.append(f"{name!r} has nothing after the prefix")
            elif plain.lower() in existing or plain.lower() in claimed:
                skipped.append(f"{name!r} -> {plain!r} would collide with an existing tag")
            else:
                renames.append(TagRename(provider_id=provider_id, old=name, new=plain))
                claimed.add(plain.lower())
    return renames, skipped


async def main(apply: bool, rename_area_tags: bool) -> None:
    async with async_session() as session:
        tasks = (
            await session.execute(select(Task).options(selectinload(Task.tags)).where(Task.deleted_at.is_(None)))
        ).scalars().all()
        changes = []
        for task in tasks:
            change = plan_task_change(
                task.id, task.title, [t.name for t in task.tags], task.estimate_minutes, task.context
            )
            if change.sets_anything or change.notes:
                changes.append((task, change))

        updated = 0
        for task, change in changes:
            parts = []
            if change.estimate_minutes is not None:
                parts.append(f"estimate_minutes -> {change.estimate_minutes}")
            if change.context is not None:
                parts.append(f"context -> {change.context}")
            parts.extend(f"({note})" for note in change.notes)
            print(f"  task {change.task_id} {change.title!r}: {', '.join(parts)}")
            if apply and change.sets_anything:
                if change.estimate_minutes is not None:
                    task.estimate_minutes = change.estimate_minutes
                if change.context is not None:
                    task.context = change.context
                updated += 1

        renamed = 0
        if rename_area_tags:
            tags = (await session.execute(select(Tag))).scalars().all()
            by_provider: dict[str, list[str]] = {}
            for tag in tags:
                by_provider.setdefault(tag.provider_id, []).append(tag.name)
            renames, skipped = plan_area_renames(by_provider)
            lookup = {(t.provider_id, t.name): t for t in tags}
            for rename in renames:
                print(f"  tag {rename.old!r} -> {rename.new!r} (provider {rename.provider_id})")
                if apply:
                    lookup[(rename.provider_id, rename.old)].name = rename.new
                    renamed += 1
            for note in skipped:
                print(f"  skipped: {note}")

        if apply:
            await session.commit()
            print(f"Updated {updated} task(s), renamed {renamed} tag(s).")
        else:
            print("Dry run: nothing written. Re-run with --apply to save these changes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    parser.add_argument("--rename-area-tags", action="store_true", help="also rename area:<name> tags to <name>")
    args = parser.parse_args()
    asyncio.run(main(apply=args.apply, rename_area_tags=args.rename_area_tags))
