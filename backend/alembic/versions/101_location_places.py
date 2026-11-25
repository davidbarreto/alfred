"""One places table: travel places and organizer locations become location.places

Phase 2 of the location domain.

Upgrade:
1. `travel.places` moves to `location.places` (ids kept, so visits, stays, tags, links and transaction links need no
   remap). `lat`/`lng` become `latitude`/`longitude` NUMERIC(9,6), both or neither; `opening_hours` and `active` are
   added; the kind CHECK takes the union of both kind lists; names are unique per city ignoring case; one home.
2. `organizer.everyday_places` marks a place as one of the everyday places (Home is everyday without a row).
3. Every `organizer.locations` row becomes a place in the home city (the `travel.home_city_id` setting), and an
   everyday place unless it is Home. A database with locations but no home city (a fresh install: migration 095 seeds
   Home) gets a placeholder city "Home city" in "Unknown", set as the home city, to be renamed. The migration aborts
   when a location's name is already a place in the home city.
4. `locations_shopping_categories` and `location_travel_times` become `places_shopping_categories` and
   `travel_times` keyed by place ids; `calendar_events.location_id` becomes `place_id`; the `weather.location_id`
   setting becomes `weather.place_id`. All through a location id -> place id map.
5. `organizer.locations` is dropped.

Downgrade: the reverse. Everyday places and Home go back to `organizer.locations` (new ids) and everything else back
to `travel.places`. It aborts, naming the places, when the data can't be split back: an everyday place (or Home) with
visits, stays, tags or links; a place that isn't everyday with opening hours, travel times, shopping categories,
calendar events, an archived flag or a kind travel doesn't have; or two everyday places with the same name.

Revision ID: 101
Revises: 100
Create Date: 2026-11-25
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "101"
down_revision = "100"
branch_labels = None
depends_on = None

# The kinds as they were before this migration (organizer.locations and travel.places), and the union after it.
LOCATION_KINDS = (
    "home", "work", "school", "gym", "sports", "supermarket", "pharmacy", "bakery", "market", "mall", "variety_store",
    "hardware_store", "shop", "restaurant", "cafe", "health", "park", "playground", "venue", "other",
)
TRAVEL_KINDS = ("hotel", "restaurant", "cafe", "activity", "museum", "attraction", "shop", "other")
PLACE_KINDS = (
    "home", "work", "school", "gym", "sports", "supermarket", "pharmacy", "bakery", "market", "mall", "variety_store",
    "hardware_store", "shop", "restaurant", "cafe", "health", "park", "playground", "venue", "hotel", "activity",
    "museum", "attraction", "other",
)

_LOCATION_COLUMNS = "name, kind, address, maps_url, latitude, longitude, opening_hours, notes, active, created_at, updated_at"


def _in(column: str, values: tuple[str, ...]) -> str:
    return "{} IN ({})".format(column, ", ".join(f"'{v}'" for v in values))


def _rows(sql: str) -> list:
    return list(op.get_bind().execute(sa.text(sql)).all())


def _abort_if(problems: list[str], what: str) -> None:
    if problems:
        raise RuntimeError(f"Migration 101 {what}: " + "; ".join(problems))


def home_city_id() -> int | None:
    """The `travel.home_city_id` setting when it names an existing city, else None."""
    rows = _rows(
        "SELECT c.id FROM core.settings s JOIN location.cities c ON s.value ~ '^[0-9]+$' AND c.id = s.value::int "
        "WHERE s.key = 'travel.home_city_id'"
    )
    return rows[0][0] if rows else None


def _placeholder_home_city() -> int:
    """A city for the locations of a database with no home city: "Home city" in "Unknown", made the home city."""
    country = _rows("SELECT id FROM location.countries WHERE lower(name) = 'unknown'")
    country_id = country[0][0] if country else _rows(
        "INSERT INTO location.countries (name) VALUES ('Unknown') RETURNING id"
    )[0][0]
    city = _rows(f"SELECT id FROM location.cities WHERE lower(name) = 'home city' AND country_id = {int(country_id)}")
    city_id = city[0][0] if city else _rows(
        f"INSERT INTO location.cities (name, country_id) VALUES ('Home city', {int(country_id)}) RETURNING id"
    )[0][0]
    op.execute(
        "INSERT INTO core.settings (key, value) VALUES ('travel.home_city_id', "
        f"'{int(city_id)}') ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
    )
    return city_id


def _upgrade_checks(city_id: int | None) -> int | None:
    if not _rows("SELECT 1 FROM organizer.locations LIMIT 1"):
        return city_id
    if city_id is None:
        city_id = _placeholder_home_city()
    clashes = _rows(
        "SELECT l.name FROM organizer.locations l JOIN travel.places p "
        f"ON lower(p.name) = lower(l.name) AND p.city_id = {int(city_id)} ORDER BY l.name"
    )
    _abort_if([f"{name!r} is both a location and a travel place in the home city" for (name,) in clashes], "found clashes")
    return city_id


def upgrade() -> None:
    city_id = _upgrade_checks(home_city_id())

    # 1. The base table.
    op.execute("ALTER TABLE travel.places SET SCHEMA location")
    op.execute("ALTER INDEX location.ix_travel_places_id RENAME TO ix_location_places_id")
    op.execute("ALTER INDEX location.ix_travel_places_city_id RENAME TO ix_location_places_city_id")
    op.drop_constraint("ck_travel_places_kind", "places", schema="location")
    op.drop_constraint("ck_travel_places_coordinates", "places", schema="location")
    op.alter_column("places", "lat", new_column_name="latitude", schema="location")
    op.alter_column("places", "lng", new_column_name="longitude", schema="location")
    for column in ("latitude", "longitude"):
        op.execute(
            f"ALTER TABLE location.places ALTER COLUMN {column} TYPE NUMERIC(9, 6) USING round({column}::numeric, 6)"
        )
    # A travel place with only one of the two had no usable coordinates anyway.
    op.execute("UPDATE location.places SET latitude = NULL, longitude = NULL WHERE (latitude IS NULL) <> (longitude IS NULL)")
    op.alter_column("places", "kind", type_=sa.String(30), schema="location")
    op.add_column("places", sa.Column("opening_hours", JSONB(), nullable=True), schema="location")
    op.add_column(
        "places", sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")), schema="location"
    )
    op.create_check_constraint("ck_places_kind", "places", _in("kind", PLACE_KINDS), schema="location")
    op.create_check_constraint(
        "ck_places_coordinates", "places", "(latitude IS NULL) = (longitude IS NULL)", schema="location"
    )
    op.execute("CREATE UNIQUE INDEX uq_places_name_city ON location.places (lower(name), city_id)")
    op.execute("CREATE UNIQUE INDEX uq_places_home ON location.places (kind) WHERE kind = 'home'")

    # 2. The everyday role.
    op.create_table(
        "everyday_places",
        sa.Column("place_id", sa.Integer(), sa.ForeignKey("location.places.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="organizer",
    )

    # 3. Locations become places; the map is exact because names are unique (and checked above) in the home city.
    if city_id is not None:
        op.execute(
            f"INSERT INTO location.places (city_id, {_LOCATION_COLUMNS}) "
            f"SELECT {int(city_id)}, {_LOCATION_COLUMNS} FROM organizer.locations ORDER BY id"
        )
    op.execute(
        "CREATE TEMP TABLE location_place_map ON COMMIT DROP AS "
        "SELECT l.id AS location_id, p.id AS place_id FROM organizer.locations l "
        "JOIN location.places p ON lower(p.name) = lower(l.name) AND p.city_id = "
        f"{int(city_id) if city_id is not None else 'NULL'}"
    )
    op.execute(
        "INSERT INTO organizer.everyday_places (place_id, created_at) SELECT m.place_id, l.created_at "
        "FROM location_place_map m JOIN organizer.locations l ON l.id = m.location_id WHERE l.kind <> 'home'"
    )

    # 4. What pointed at locations points at places.
    op.create_table(
        "places_shopping_categories",
        sa.Column("place_id", sa.Integer(), sa.ForeignKey("location.places.id", ondelete="CASCADE"), primary_key=True),
        sa.Column(
            "category_id", sa.Integer(), sa.ForeignKey("organizer.shopping_categories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        schema="organizer",
    )
    op.create_index(
        "ix_organizer_places_shopping_categories_category_id", "places_shopping_categories", ["category_id"],
        schema="organizer",
    )
    op.execute(
        "INSERT INTO organizer.places_shopping_categories (place_id, category_id) SELECT m.place_id, c.category_id "
        "FROM organizer.locations_shopping_categories c JOIN location_place_map m ON m.location_id = c.location_id"
    )
    op.drop_table("locations_shopping_categories", schema="organizer")

    _create_travel_times()
    op.execute(
        "INSERT INTO organizer.travel_times (origin_place_id, destination_place_id, mode, minutes, created_at, updated_at) "
        "SELECT o.place_id, d.place_id, t.mode, t.minutes, t.created_at, t.updated_at "
        "FROM organizer.location_travel_times t "
        "JOIN location_place_map o ON o.location_id = t.origin_id "
        "JOIN location_place_map d ON d.location_id = t.destination_id ORDER BY t.id"
    )
    op.drop_table("location_travel_times", schema="organizer")

    op.add_column(
        "calendar_events",
        sa.Column(
            "place_id", sa.Integer(),
            sa.ForeignKey("location.places.id", ondelete="SET NULL", name="fk_calendar_events_place_id"), nullable=True,
        ),
        schema="organizer",
    )
    op.create_index("ix_calendar_events_place_id", "calendar_events", ["place_id"], schema="organizer")
    op.execute(
        "UPDATE organizer.calendar_events e SET place_id = m.place_id FROM location_place_map m "
        "WHERE m.location_id = e.location_id"
    )
    op.drop_column("calendar_events", "location_id", schema="organizer")

    op.execute(
        "UPDATE core.settings s SET key = 'weather.place_id', value = COALESCE("
        "(SELECT m.place_id::text FROM location_place_map m WHERE m.location_id::text = s.value), '') "
        "WHERE s.key = 'weather.location_id'"
    )

    # 5. The old table goes.
    op.drop_table("locations", schema="organizer")
    op.execute("DROP TABLE location_place_map")


def _create_travel_times() -> None:
    op.create_table(
        "travel_times",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "origin_place_id", sa.Integer(), sa.ForeignKey("location.places.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "destination_place_id", sa.Integer(), sa.ForeignKey("location.places.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("mode", sa.String(40), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("origin_place_id <> destination_place_id", name="ck_travel_times_distinct"),
        sa.CheckConstraint("minutes BETWEEN 1 AND 600", name="ck_travel_times_minutes"),
        sa.UniqueConstraint("origin_place_id", "destination_place_id", "mode", name="uq_travel_times_route"),
        schema="organizer",
    )
    op.create_index("ix_organizer_travel_times_id", "travel_times", ["id"], schema="organizer")
    op.create_index("ix_organizer_travel_times_origin_place_id", "travel_times", ["origin_place_id"], schema="organizer")
    op.create_index(
        "ix_organizer_travel_times_destination_place_id", "travel_times", ["destination_place_id"], schema="organizer"
    )


_EVERYDAY = "(p.kind = 'home' OR p.id IN (SELECT place_id FROM organizer.everyday_places))"


def _names(sql: str, problem: str) -> list[str]:
    return [f"{name!r} (id {pid}) {problem}" for pid, name in _rows(sql)]


def _downgrade_checks() -> None:
    held = " OR ".join(
        f"p.id IN (SELECT place_id FROM travel.{table} WHERE place_id IS NOT NULL)"
        for table in ("visits", "stays", "places_tags", "links")
    )
    problems = _names(
        f"SELECT p.id, p.name FROM location.places p WHERE {_EVERYDAY} AND ({held}) ORDER BY p.id",
        "is an everyday place with visits, stays, tags or links",
    )
    problems += _names(
        f"SELECT p.id, p.name FROM location.places p WHERE {_EVERYDAY} AND (NOT {_in('p.kind', LOCATION_KINDS)} OR length(p.name) > 100) "
        "ORDER BY p.id",
        "is an everyday place with a kind or a name too long for organizer.locations",
    )
    everyday_only = " OR ".join((
        "p.opening_hours IS NOT NULL",
        "NOT p.active",
        "NOT " + _in("p.kind", TRAVEL_KINDS),
        "p.id IN (SELECT origin_place_id FROM organizer.travel_times)",
        "p.id IN (SELECT destination_place_id FROM organizer.travel_times)",
        "p.id IN (SELECT place_id FROM organizer.places_shopping_categories)",
        "p.id IN (SELECT place_id FROM organizer.calendar_events WHERE place_id IS NOT NULL)",
    ))
    problems += _names(
        f"SELECT p.id, p.name FROM location.places p WHERE NOT {_EVERYDAY} AND ({everyday_only}) ORDER BY p.id",
        "is not an everyday place but has hours, travel times, categories, events, an archived flag or a non-travel kind",
    )
    problems += _names(
        f"SELECT min(p.id), min(p.name) FROM location.places p WHERE {_EVERYDAY} GROUP BY lower(p.name) "
        "HAVING count(*) > 1",
        "shares its name with another everyday place",
    )
    _abort_if(problems, "downgrade cannot split the places back")


def downgrade() -> None:
    _downgrade_checks()

    op.create_table(
        "locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("maps_url", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("opening_hours", JSONB(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(_in("kind", LOCATION_KINDS), name="ck_locations_kind"),
        sa.CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name="ck_locations_coordinates"),
        schema="organizer",
    )
    op.create_index("ix_locations_id", "locations", ["id"], schema="organizer")
    op.execute("CREATE UNIQUE INDEX uq_locations_name ON organizer.locations (lower(name))")
    op.execute("CREATE UNIQUE INDEX uq_locations_home ON organizer.locations (kind) WHERE kind = 'home'")
    op.execute(
        f"INSERT INTO organizer.locations ({_LOCATION_COLUMNS}) SELECT p.name, p.kind, p.address, p.maps_url, "
        "p.latitude, p.longitude, p.opening_hours, p.notes, p.active, p.created_at, p.updated_at "
        f"FROM location.places p WHERE {_EVERYDAY} ORDER BY p.id"
    )
    op.execute(
        "CREATE TEMP TABLE location_place_map ON COMMIT DROP AS SELECT l.id AS location_id, p.id AS place_id "
        f"FROM organizer.locations l JOIN location.places p ON lower(p.name) = lower(l.name) AND {_EVERYDAY}"
    )

    op.create_table(
        "locations_shopping_categories",
        sa.Column(
            "location_id", sa.Integer(), sa.ForeignKey("organizer.locations.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "category_id", sa.Integer(), sa.ForeignKey("organizer.shopping_categories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        schema="organizer",
    )
    op.create_index(
        "ix_locations_shopping_categories_category_id", "locations_shopping_categories", ["category_id"],
        schema="organizer",
    )
    op.execute(
        "INSERT INTO organizer.locations_shopping_categories (location_id, category_id) "
        "SELECT m.location_id, c.category_id FROM organizer.places_shopping_categories c "
        "JOIN location_place_map m ON m.place_id = c.place_id"
    )
    op.drop_table("places_shopping_categories", schema="organizer")

    op.create_table(
        "location_travel_times",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("origin_id", sa.Integer(), sa.ForeignKey("organizer.locations.id", ondelete="RESTRICT"), nullable=False),
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
    op.execute(
        "INSERT INTO organizer.location_travel_times (origin_id, destination_id, mode, minutes, created_at, updated_at) "
        "SELECT o.location_id, d.location_id, t.mode, t.minutes, t.created_at, t.updated_at FROM organizer.travel_times t "
        "JOIN location_place_map o ON o.place_id = t.origin_place_id "
        "JOIN location_place_map d ON d.place_id = t.destination_place_id ORDER BY t.id"
    )
    op.drop_table("travel_times", schema="organizer")

    op.add_column(
        "calendar_events",
        sa.Column(
            "location_id", sa.Integer(),
            sa.ForeignKey("organizer.locations.id", ondelete="SET NULL", name="fk_calendar_events_location_id"),
            nullable=True,
        ),
        schema="organizer",
    )
    op.create_index("ix_calendar_events_location_id", "calendar_events", ["location_id"], schema="organizer")
    op.execute(
        "UPDATE organizer.calendar_events e SET location_id = m.location_id FROM location_place_map m "
        "WHERE m.place_id = e.place_id"
    )
    op.drop_column("calendar_events", "place_id", schema="organizer")

    op.execute(
        "UPDATE core.settings s SET key = 'weather.location_id', value = COALESCE("
        "(SELECT m.location_id::text FROM location_place_map m WHERE m.place_id::text = s.value), '') "
        "WHERE s.key = 'weather.place_id'"
    )

    # Everyday places and Home now live in organizer.locations; everything else goes back to travel.places.
    op.execute(f"DELETE FROM location.places p WHERE {_EVERYDAY}")
    op.drop_table("everyday_places", schema="organizer")

    op.execute("DROP INDEX location.uq_places_home")
    op.execute("DROP INDEX location.uq_places_name_city")
    op.drop_constraint("ck_places_coordinates", "places", schema="location")
    op.drop_constraint("ck_places_kind", "places", schema="location")
    op.drop_column("places", "active", schema="location")
    op.drop_column("places", "opening_hours", schema="location")
    op.alter_column("places", "kind", type_=sa.String(16), schema="location")
    for column in ("latitude", "longitude"):
        op.execute(f"ALTER TABLE location.places ALTER COLUMN {column} TYPE DOUBLE PRECISION")
    op.alter_column("places", "latitude", new_column_name="lat", schema="location")
    op.alter_column("places", "longitude", new_column_name="lng", schema="location")
    op.create_check_constraint("ck_travel_places_kind", "places", _in("kind", TRAVEL_KINDS), schema="location")
    op.create_check_constraint(
        "ck_travel_places_coordinates", "places",
        "(lat IS NULL OR lat BETWEEN -90 AND 90) AND (lng IS NULL OR lng BETWEEN -180 AND 180)", schema="location",
    )
    op.execute("ALTER INDEX location.ix_location_places_id RENAME TO ix_travel_places_id")
    op.execute("ALTER INDEX location.ix_location_places_city_id RENAME TO ix_travel_places_city_id")
    op.execute("DROP TABLE location_place_map")
    op.execute("ALTER TABLE location.places SET SCHEMA travel")
