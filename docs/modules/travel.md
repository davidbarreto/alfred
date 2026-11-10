# Travel module

Remember past travels and run an upcoming trip (`travel` schema). Design and phases: `docs/plans/travel.md` (gitignored). No AI and no external API: maps links are plain URLs, coordinates are optional and user-supplied.

## Data model

- **Trips** (`travel.trips`): `name`, `start_date`/`end_date`, `travelers`, `preferences`, `notes`, `checklist_note_id` (organizer note, SET NULL), `default_tag_names` (comma-separated *finance* tag names). **Status** (`upcoming` / `ongoing` / `past`) is derived from `local_today()`, never stored.
- **Legs** (`travel.legs`): flights, trains, buses, ferries, cars. Belong to a trip (CASCADE). `departs_at`/`arrives_at` are UTC instants stored with the IANA zone of each end (`departs_tz`/`arrives_tz`); the read model adds `departs_local`/`arrives_local`. A flight with carrier + number gets a `check_flight_url` (a plain web search, no status API).
- **Stays** (`travel.stays`): lodging periods, with a `place_id` (RESTRICT), an optional `trip_id` (SET NULL, so a trip's deletion keeps notes and grades), `timezone` of the lodging, `grade` 1-5.
- **Places** (`travel.places`): independent of trips. `kind` in `PLACE_KINDS`, optional `maps_url`/`lat`/`lng`/`address`. `maps_link` is the user's URL, else pasted coordinates, else a name + city search.
- **Visits** (`travel.visits`): one occurrence of going to a place (a dinner, a museum day), `planned` / `visited` / `missed`, optional `trip_id` (SET NULL) and `visit_date` / `visit_time`, `notes`, `grade` 1-5 (only a visited visit can carry one; moving it back to planned/missed clears it). Hotels use stays. A planned visit with no trip is the wishlist.
- **Tags** (`travel.tags` + `trips_tags` / `places_tags`, ORM class `TravelTag`): describe the trip or place (Family, Would return). Not the same as `default_tag_names`.
- **Derived grade**: a place's `grade` is the average over its graded visits and stays, with `grade_count`; never stored.
- Enum sets (`PLACE_KINDS`, `LEG_MODES`, `VISIT_STATUSES`) live in `features/travel/constants.py` and feed Pydantic, CHECK constraints and MCP descriptions.

## Times

Create bodies accept naive wall times (read in the matching `*_tz`) or values with an offset; both are stored as UTC. On update a naive value is read in the zone sent with it, else the stored zone. `arrives_at >= departs_at` and `check_out_at >= check_in_at` are enforced in the service and by CHECK constraints.

## Timeline and warnings

`GET /travel/trips/{id}` returns the trip with its legs, stays, a chronological `timeline` (leg departures, check-ins, check-outs, each with maps links: transit directions, cafes near the hotel, luggage storage) and `warnings`, computed in `features/travel/trips/timeline.py` only from data that exists:

- `long_wait_before_check_in`: a leg arrives in the stay's city more than 4 h (and less than 24 h) before check-in.
- `tight_connection`: consecutive legs through the same place with under 90 min between them.
- `arrives_after_check_out`: a leg to the stay's city departs before check-out and arrives after it.
- `overlapping_legs`: a leg departs before the previous one arrives.

City matching is a case-insensitive containment between a leg's `destination` and the stay place's `city`.

## Itinerary and hiding

A trip's itinerary is its visits, sorted by day then time; undated visits and those without a time come last, in creation order. Once the trip has ended, planned and missed visits are hidden (`hidden_visit_count` says how many); `GET /travel/trips/{id}?all_visits=true` returns them all.

## Leave-home time and reminders

If a trip's first leg is a flight, the trip detail has `leave_home_at` (departure minus `travel.airport_buffer_min` minus `travel.home_to_airport_min`, both runtime settings in `core.settings`) and a `leave_home` timeline item. Reminders (trip starts, online check-in, time to leave, check-out day) are described in [reminders-overload.md](reminders-overload.md#travel-reminders).

## API

`/travel/trips` (list filters: `status` = current (default) / upcoming / ongoing / past / all, repeated `tag`, `q`, `date_from`, `date_to`, `limit`, `offset`), `/travel/legs`, `/travel/stays`, `/travel/visits` (filters `trip_id`, `place_id`, `status`, `date_from`, `date_to`, `no_trip`), `/travel/places` (filters `q`, `kind`, `city`, `country`, repeated `tag`, `min_grade`, `status` = has a visit with it, `no_trip` = no visit or stay belongs to a trip; `GET /{id}` returns the history; deleting a place with visits or stays is a 409), `/travel/settings` (GET/PUT), `/travel/tags` (usage counts, rename, delete removes only link rows). Postman: `postman/travel.collection.json`.

## Portal

`/travel`: reminder settings form and a trips list with status, text, date-range and tag filters (HTMX partial `/travel/list`, `limit + 1` pagination). `/travel/{id}`: header with inline edit, warnings, day-grouped timeline, the itinerary (visits by day, mark visited/missed, add/edit/delete, a toggle for hidden ones), legs and stays with add/edit/delete dialogs; `/travel/places` (filterable list) and `/travel/places/{id}` (edit, tags, derived grade, visit and stay history, plan a visit); a new hotel can be created inline in the stay dialog. Writes proxy through `/travel/{trips,legs,stays,places,visits}`.
