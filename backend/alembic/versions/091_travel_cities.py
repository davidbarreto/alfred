"""Cities and countries as data

Places, leg ends and the weather rows point at a city, and a city at a country, instead of repeating their names
as text. The text columns `places.city` / `places.country` and `trip_weather.city_key` / `city` are replaced by
`city_id`. A leg end's city is nullable (a station or an address can't always be matched), and its terminal text
stays.

The backfill is plain SQL: countries and cities from the places (the earliest-created place's spelling wins), the
places pointed at them, and each leg end or weather row pointed at the one city of that name when exactly one
exists. Weather rows that map to no city are deleted: they are fetched again on the next request.

Revision ID: 091
Revises: 090
Create Date: 2026-11-15
"""
from alembic import op
import sqlalchemy as sa

revision = "091"
down_revision = "090"
branch_labels = None
depends_on = None

# The cities whose name is unique across countries: a text can only be matched to one of those.
_UNIQUE_CITIES = (
    "(SELECT lower(name) AS key, min(id) AS id FROM travel.cities GROUP BY lower(name) HAVING count(*) = 1)"
)


def upgrade() -> None:
    bind = op.get_bind()
    missing = bind.execute(sa.text(
        "SELECT id FROM travel.places WHERE coalesce(trim(city), '') = '' OR coalesce(trim(country), '') = '' ORDER BY id"
    )).scalars().all()
    if missing:
        raise RuntimeError(f"Places without a city or a country, fix them before migrating: ids {list(missing)}")

    op.create_table(
        "countries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("code", sa.String(2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="travel",
    )
    op.create_index("ix_travel_countries_id", "countries", ["id"], schema="travel")
    op.create_index("uq_travel_countries_name", "countries", [sa.text("lower(name)")], unique=True, schema="travel")
    op.create_index(
        "uq_travel_countries_code", "countries", ["code"], unique=True, schema="travel",
        postgresql_where=sa.text("code IS NOT NULL"),
    )
    op.create_table(
        "cities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("country_id", sa.Integer(), sa.ForeignKey("travel.countries.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="travel",
    )
    op.create_index("ix_travel_cities_id", "cities", ["id"], schema="travel")
    op.create_index(
        "uq_travel_cities_name_country", "cities", [sa.text("lower(name)"), "country_id"], unique=True, schema="travel"
    )

    # Countries and cities, in the spelling of the earliest-created place that uses them. No ISO code is known yet.
    op.execute("""
        INSERT INTO travel.countries (name)
        SELECT DISTINCT ON (lower(trim(country))) trim(country)
        FROM travel.places ORDER BY lower(trim(country)), created_at, id
    """)
    op.execute("""
        INSERT INTO travel.cities (name, country_id)
        SELECT DISTINCT ON (lower(trim(p.city)), co.id) trim(p.city), co.id
        FROM travel.places p JOIN travel.countries co ON lower(co.name) = lower(trim(p.country))
        ORDER BY lower(trim(p.city)), co.id, p.created_at, p.id
    """)

    # Places
    op.add_column("places", sa.Column(
        "city_id", sa.Integer(), sa.ForeignKey("travel.cities.id", ondelete="RESTRICT"), nullable=True
    ), schema="travel")
    op.execute("""
        UPDATE travel.places p SET city_id = ci.id
        FROM travel.cities ci JOIN travel.countries co ON co.id = ci.country_id
        WHERE lower(ci.name) = lower(trim(p.city)) AND lower(co.name) = lower(trim(p.country))
    """)
    op.alter_column("places", "city_id", nullable=False, schema="travel")
    op.create_index("ix_travel_places_city_id", "places", ["city_id"], schema="travel")
    op.drop_column("places", "city", schema="travel")
    op.drop_column("places", "country", schema="travel")

    # Leg ends: the city is the only one with that name, else none.
    for end in ("origin", "destination"):
        op.add_column("legs", sa.Column(
            f"{end}_city_id", sa.Integer(), sa.ForeignKey("travel.cities.id", ondelete="RESTRICT"), nullable=True
        ), schema="travel")
        op.create_index(f"ix_travel_legs_{end}_city_id", "legs", [f"{end}_city_id"], schema="travel")
        op.execute(f"""
            UPDATE travel.legs l SET {end}_city_id = m.id
            FROM {_UNIQUE_CITIES} m WHERE m.key = lower(trim(l.{end}))
        """)

    # Weather
    op.add_column("trip_weather", sa.Column(
        "city_id", sa.Integer(), sa.ForeignKey("travel.cities.id", ondelete="CASCADE"), nullable=True
    ), schema="travel")
    op.execute(f"UPDATE travel.trip_weather w SET city_id = m.id FROM {_UNIQUE_CITIES} m WHERE m.key = w.city_key")
    op.execute("DELETE FROM travel.trip_weather WHERE city_id IS NULL")
    op.alter_column("trip_weather", "city_id", nullable=False, schema="travel")
    op.drop_constraint("uq_travel_trip_weather_day", "trip_weather", schema="travel", type_="unique")
    op.drop_column("trip_weather", "city_key", schema="travel")
    op.drop_column("trip_weather", "city", schema="travel")
    op.create_unique_constraint("uq_travel_trip_weather_day", "trip_weather", ["trip_id", "city_id", "day"], schema="travel")


def downgrade() -> None:
    # Weather: the city text comes back from the join. Cities that differ only by country share a key, so keep one.
    op.add_column("trip_weather", sa.Column("city_key", sa.String(200), nullable=True), schema="travel")
    op.add_column("trip_weather", sa.Column("city", sa.String(200), nullable=True), schema="travel")
    op.execute("""
        UPDATE travel.trip_weather w SET city_key = lower(c.name), city = c.name
        FROM travel.cities c WHERE c.id = w.city_id
    """)
    op.execute("""
        DELETE FROM travel.trip_weather w USING travel.trip_weather o
        WHERE w.trip_id = o.trip_id AND w.city_key = o.city_key AND w.day = o.day AND w.id > o.id
    """)
    op.alter_column("trip_weather", "city_key", nullable=False, schema="travel")
    op.alter_column("trip_weather", "city", nullable=False, schema="travel")
    op.drop_constraint("uq_travel_trip_weather_day", "trip_weather", schema="travel", type_="unique")
    op.drop_column("trip_weather", "city_id", schema="travel")
    op.create_unique_constraint("uq_travel_trip_weather_day", "trip_weather", ["trip_id", "city_key", "day"], schema="travel")

    for end in ("destination", "origin"):
        op.drop_index(f"ix_travel_legs_{end}_city_id", table_name="legs", schema="travel")
        op.drop_column("legs", f"{end}_city_id", schema="travel")

    op.add_column("places", sa.Column("city", sa.String(100), nullable=True), schema="travel")
    op.add_column("places", sa.Column("country", sa.String(100), nullable=True), schema="travel")
    op.execute("""
        UPDATE travel.places p SET city = ci.name, country = co.name
        FROM travel.cities ci JOIN travel.countries co ON co.id = ci.country_id WHERE ci.id = p.city_id
    """)
    op.drop_index("ix_travel_places_city_id", table_name="places", schema="travel")
    op.drop_column("places", "city_id", schema="travel")

    op.drop_table("cities", schema="travel")
    op.drop_table("countries", schema="travel")
