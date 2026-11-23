"""Travel times are rows between locations

`organizer.location_travel_times`: minutes from one location to another by one mode (unique per origin,
destination and mode; both FKs RESTRICT). The `planning.travel_times` setting (a JSON list of
{origin, place, mode, minutes} with lowercase names, origin defaulting to home) becomes rows: "home" is the Home
location, any other name the location with that name (case-insensitive), created when missing (office -> kind
work, school -> school, gym -> gym, anything else -> other). Then the setting is deleted.

Downgrade writes the rows back into the setting in the same JSON shape (Home as "home", other names lowercased)
and drops the table; locations created here stay.

Revision ID: 096
Revises: 095
Create Date: 2026-11-23
"""
import json

from alembic import op
import sqlalchemy as sa

revision = "096"
down_revision = "095"
branch_labels = None
depends_on = None

_SETTING_KEY = "planning.travel_times"
_HOME = "home"
_GUESSED_KINDS = {"office": "work", "work": "work", "school": "school", "gym": "gym"}


def _location_id(bind, name: str) -> int:
    if name == _HOME:
        found = bind.execute(sa.text("SELECT id FROM organizer.locations WHERE kind = 'home'")).scalar()
        if found is not None:
            return found
    found = bind.execute(
        sa.text("SELECT id FROM organizer.locations WHERE lower(name) = :name"), {"name": name}
    ).scalar()
    if found is not None:
        return found
    kind = _HOME if name == _HOME else _GUESSED_KINDS.get(name, "other")
    return bind.execute(
        sa.text("INSERT INTO organizer.locations (name, kind) VALUES (:name, :kind) RETURNING id"),
        {"name": name[:1].upper() + name[1:], "kind": kind},
    ).scalar_one()


def upgrade() -> None:
    op.create_table(
        "location_travel_times",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "origin_id", sa.Integer(), sa.ForeignKey("organizer.locations.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "destination_id", sa.Integer(), sa.ForeignKey("organizer.locations.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("mode", sa.String(40), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("origin_id <> destination_id", name="ck_location_travel_times_distinct"),
        sa.CheckConstraint("minutes BETWEEN 1 AND 600", name="ck_location_travel_times_minutes"),
        sa.UniqueConstraint("origin_id", "destination_id", "mode", name="uq_location_travel_times_route"),
        schema="organizer",
    )
    op.create_index("ix_location_travel_times_id", "location_travel_times", ["id"], schema="organizer")
    op.create_index("ix_location_travel_times_origin_id", "location_travel_times", ["origin_id"], schema="organizer")
    op.create_index(
        "ix_location_travel_times_destination_id", "location_travel_times", ["destination_id"], schema="organizer"
    )

    bind = op.get_bind()
    raw = bind.execute(sa.text("SELECT value FROM core.settings WHERE key = :key"), {"key": _SETTING_KEY}).scalar()
    for entry in json.loads(raw) if raw else []:
        origin = str(entry.get("origin") or _HOME).strip().lower()
        place = str(entry["place"]).strip().lower()
        if origin == place:
            continue
        bind.execute(
            sa.text("""
                INSERT INTO organizer.location_travel_times (origin_id, destination_id, mode, minutes)
                VALUES (:origin, :destination, :mode, :minutes)
                ON CONFLICT (origin_id, destination_id, mode) DO NOTHING
            """),
            {
                "origin": _location_id(bind, origin), "destination": _location_id(bind, place),
                "mode": str(entry["mode"]).strip().lower(), "minutes": int(entry["minutes"]),
            },
        )
    bind.execute(sa.text("DELETE FROM core.settings WHERE key = :key"), {"key": _SETTING_KEY})


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("""
        SELECT CASE WHEN o.kind = 'home' THEN 'home' ELSE lower(o.name) END,
               CASE WHEN d.kind = 'home' THEN 'home' ELSE lower(d.name) END,
               t.mode, t.minutes
        FROM organizer.location_travel_times t
        JOIN organizer.locations o ON o.id = t.origin_id
        JOIN organizer.locations d ON d.id = t.destination_id
        ORDER BY t.id
    """)).all()
    if rows:
        value = json.dumps([
            {"origin": origin, "place": place, "mode": mode, "minutes": minutes} for origin, place, mode, minutes in rows
        ])
        bind.execute(
            sa.text("""
                INSERT INTO core.settings (key, value) VALUES (:key, :value)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
            """),
            {"key": _SETTING_KEY, "value": value},
        )
    op.drop_index("ix_location_travel_times_destination_id", table_name="location_travel_times", schema="organizer")
    op.drop_index("ix_location_travel_times_origin_id", table_name="location_travel_times", schema="organizer")
    op.drop_index("ix_location_travel_times_id", table_name="location_travel_times", schema="organizer")
    op.drop_table("location_travel_times", schema="organizer")
