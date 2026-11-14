"""Store tag names lowercase everywhere

Tag names are now lowercased when written (travel, metrics, interview, finance, study, language chunk and
organizer tags; CS tags already were). This converts the existing rows. Where two tags only differed by case
(for the case-sensitive tables) the rows are merged: links move to the lowercase tag and the duplicate is
deleted. The original capitalization is not restored on downgrade.

Revision ID: 089
Revises: 088
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa

revision = "089"
down_revision = "088"
branch_labels = None
depends_on = None

# (tag table, scope column or None, [(link table, item column)], [(other table, tag_id column)])
_TAG_TABLES = [
    ("travel.tags", None, [("travel.trips_tags", "trip_id"), ("travel.places_tags", "place_id")], []),
    ("metrics.tags", None, [("metrics.entries_tags", "entry_id")], []),
    (
        "organizer.interview_tags",
        None,
        [("organizer.interview_story_tag_links", "story_id"), ("organizer.interview_question_tag_links", "question_id")],
        [],
    ),
    ("finance.tags", None, [("finance.transactions_tags", "transaction_id")], [("finance.budget_targets", "tag_id")]),
    ("study.tags", None, [("study.plans_tags", "plan_id")], []),
    ("language.tags", None, [("language.chunks_tags", "chunk_id")], []),
    (
        "organizer.tags",
        "provider_id",
        [
            ("organizer.tasks_tags", "task_id"),
            ("organizer.notes_tags", "note_id"),
            ("organizer.calendar_events_tags", "event_id"),
            ("organizer.activities_tags", "activity_id"),
        ],
        [],
    ),
]


def _lowercase(bind, table, scope, links, others) -> None:
    where_scope = f" AND {scope} IS NOT DISTINCT FROM :scope" if scope else ""
    select_cols = f"id, name, {scope}" if scope else "id, name"
    rows = bind.execute(sa.text(f"SELECT {select_cols} FROM {table} WHERE name <> lower(name) ORDER BY id")).all()
    for row in rows:
        tag_id, name = row[0], row[1]
        params = {"lower": name.lower(), "id": tag_id}
        if scope:
            params["scope"] = row[2]
        target = bind.execute(
            sa.text(f"SELECT id FROM {table} WHERE name = :lower AND id <> :id{where_scope}"), params
        ).scalar()
        if target is None:
            bind.execute(sa.text(f"UPDATE {table} SET name = :lower WHERE id = :id"), params)
            continue
        for link, item in links:
            bind.execute(
                sa.text(
                    f"INSERT INTO {link} ({item}, tag_id) SELECT {item}, :target FROM {link} WHERE tag_id = :id "
                    "ON CONFLICT DO NOTHING"
                ),
                {"target": target, "id": tag_id},
            )
            bind.execute(sa.text(f"DELETE FROM {link} WHERE tag_id = :id"), {"id": tag_id})
        for other, column in others:
            bind.execute(sa.text(f"UPDATE {other} SET {column} = :target WHERE {column} = :id"), {"target": target, "id": tag_id})
        bind.execute(sa.text(f"DELETE FROM {table} WHERE id = :id"), {"id": tag_id})


def upgrade() -> None:
    bind = op.get_bind()
    for table, scope, links, others in _TAG_TABLES:
        _lowercase(bind, table, scope, links, others)


def downgrade() -> None:
    pass
