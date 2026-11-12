# Travel module

Remember past travels and run an upcoming trip (`travel` schema). Design and phases: `docs/plans/travel.md` (gitignored). No AI and no external API: maps links are plain URLs, coordinates are optional and user-supplied.

## Data model

- **Trips** (`travel.trips`): `name`, `start_date`/`end_date`, `travelers` (free text, one line per person: age, relation), `preferences`, `notes`, `checklist_note_id` (organizer note, SET NULL), `default_tag_names` (comma-separated *finance* tag names). **Status** (`upcoming` / `ongoing` / `past`) is derived from `local_today()`, never stored.
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

`GET /travel/trips/{id}` returns the trip with its legs, stays, a chronological `timeline` (leg departures, check-ins, check-outs, each with maps links: transit directions, cafes and restaurants near the hotel and at flight airports, luggage storage; a flight arrival maps the airport and links transit to the hotel even when check-in is days later) and `warnings`, computed in `features/travel/trips/timeline.py` only from data that exists:

- `long_wait_before_check_in`: a leg arrives in the stay's city more than 4 h (and less than 24 h) before check-in.
- `tight_connection`: consecutive legs through the same place with under 90 min between them.
- `arrives_after_check_out`: a leg to the stay's city departs before check-out and arrives after it.
- `overlapping_legs`: a leg departs before the previous one arrives.
- `uncovered_night`: nights between the first arrival and the last departure that no stay covers (one warning listing the dates; a night spent on an overnight leg does not count). `no_return_leg`: the last leg ends somewhere other than where the first began (the home city is not consulted, only the legs).
- Visit checks (planned and visited, missed ones ignored; undated visits skipped, the time checks also need a time; a timed visit is read in the zone of the stay covering that day, else of the latest arrival): `visit_before_arrival`, `visit_after_departure`, `visit_overlaps_leg`, `visit_without_stay` (a stay exists on the trip but none in the place's city covers the day) and `too_many_visits` (more than `travel.max_visits_per_day`, default 4, in `/travel/settings`). Computed in `trips/coverage_warnings.py`; these have `visit_id` and no timeline row.

**Home offset (27)**: each timeline item carries `home_offset` (`+1h`, `-3h`, `+5.5h` against the configured `TIMEZONE` at that instant; null when equal) and arrival rows with a difference of 3 h or more carry a one-line `sleep_hint`.

**Ideas (9)**: `TripDetail.ideas` lists planned visits with no day (the trip's own, plus wishlist visits, i.e. planned with no trip, at places in a city the trip has a stay in), grouped by stay city (`trips/ideas.py`); empty once the trip is over. The portal's *Ideas to plan* card sets `trip_id` and `visit_date` in one PATCH.

**Airport transfers**: for a flight leg the timeline offers Maps links (transit, taxi / car, walking; plain URLs, no integration) for the way *to* the departure airport (from the stay in the origin city that the traveler is leaving, else from `organizer.home_address` on the trip's first leg; none if neither is known) and, on the arrival row, for the way *from* the arrival airport to the stay in the destination city (first check-in within 24 h after landing). Airports are searched as `<IATA> airport`. Non-flight legs keep origin → destination directions.

**Warning highlight**: every timeline item carries `warnings` (the messages of the trip warnings that point at it: the arrival and check-in rows for `long_wait_before_check_in`, the arrival and check-out rows for `arrives_after_check_out`, the departing leg for `tight_connection` / `overlapping_legs`); the portal tints those rows and prints the message under the title.

**Airport picker (portal)**: in the leg form, when the mode is `flight`, From/To are a typeahead over `web/app/static/js/airports.json` (about 8k airports with an IATA code, rows of `[iata, city, name, country, tz]`, from the `airportsdata` package, MIT). Picking a row fills the city, the IATA code and the departure/arrival time zone; all stay editable, and typing without picking saves free text. Other modes are plain text. It is portal-only: there is no airports table or API, and the backend still stores `origin`/`destination` plus nullable `origin_code`/`destination_code`. Logic in `web/app/static/js/airport-input.js`.

**City picker (portal)**: the City field of the new-place forms (stay, visit) and of the place edit form is a typeahead over the distinct cities in the same airports file; picking one fills Country with the English country name (`Intl.DisplayNames` from the file's ISO code). Both stay editable, and free text still saves. Cities without an airport are typed by hand. Logic in `airport-input.js` (`initCityInput`).

City matching is a case-insensitive containment between a leg's `destination` and the stay place's `city`.

## Map pins

`GET /travel/trips/{id}/map?scope=all|planned|visited|missed` returns the trip's pins (`features/travel/trips/map_points.py`): one per place (stays, visits, and the airports of flight legs, `<IATA> airport`; a place used several times lists each use in its description). `address` is what a map importer geocodes: `lat,lng` when the place has coordinates, else name + address/city. Each pin has a `status` (`planned` / `visited` / `missed`; visited beats planned beats missed). Scopes: `planned` = still ahead (planned visits, stays not begun, flights not taken), the map to use during the trip; `visited` = visited visits, stays begun, flights taken; `missed` = visits marked missed (the last two for a history map after the trip); `all` (default) = everything, missed included, with the status in each pin. There is no Google integration: the portal's **Map pins** menu on a trip downloads `/travel/{id}/map.csv?scope=...` (columns Name, Address, Category, Status, Description), which Google My Maps imports (Create a new map, Import, position by *Address*, title by *Name*) into a saved map you can keep and share.

## Itinerary and hiding

A trip's itinerary is its visits, sorted by day then time; undated visits and those without a time come last, in creation order. Once the trip has ended, planned and missed visits are hidden (`hidden_visit_count` says how many); `GET /travel/trips/{id}?all_visits=true` returns them all.

## Transactions and cost

- **Links**: a charge is linked to the thing it paid for. Tickets and fees go on a **leg** (`travel.legs_transactions`), a hotel payment on a **stay** (`stays_transactions`), a meal or entry on a **visit** (`visits_transactions`). A place has no link of its own: three dinners at one restaurant are three visits. One transaction may be linked to several items; deleting either side removes only the link row. Transfers can't be linked. `GET/POST /travel/{legs|stays|visits}/{id}/transactions`, `DELETE .../{transaction_id}` (linking twice keeps one link).
- **Cost is derived**: expenses add, refunds (income) subtract, in `amount_eur`. A linked transaction without an EUR amount is reported as `unconverted_count` and never counted as zero. `GET /travel/trips/{id}/costs` returns the trip total (each distinct transaction once, however many items it is linked to), a breakdown by kind (legs by `mode`, stays as `lodging`, visits by the place's `kind`; a charge linked under two kinds appears under both) and the cost per leg / stay / visit. `GET /travel/places/{id}/costs` is a place's lifetime cost (its visits plus its stays).
- **Default tags** (`trips.default_tag_names`, used for finance transactions and, later, calendar events): an **expense** dated within a trip's dates picks the trip's tags up when it is created manually (`TransactionService.create`) or imported (both statement-commit paths in `ImportService`); overlapping trips merge their tags. Income, transfers and recurring-generated rows are not stamped. Editing a trip's dates never retags anything by itself: `POST /travel/trips/{id}/apply-default-tags` (the portal's *Apply default tags* button, offered after a date change) tags the expenses already in the range, skipping those that carry the tags.
- **Unlinked charges (36)**: `GET /travel/trips/{id}/unlinked-transactions` lists the expenses dated within the trip or carrying one of its default tags, plus income carrying one, that are linked to no leg, stay or visit (transfers never). No matching suggestions; the portal card has a target select and a *Link* button per charge.
- **Import from calendar** (migration 086 adds the unique `calendar_event_id` to legs and stays): `GET /travel/trips/{id}/calendar-events` lists the non-recurring events of Alfred's local calendar copy whose start falls in the trip's dates (no Google call: sync the calendar first), with times shown in the event's own zone and `imported_as` / `imported_id` when already used. The portal prefills the leg or stay dialog from the event; the user picks the type and corrects the details. Creating a leg or stay with an already imported `calendar_event_id` is a 409.

## Pre-trip checklist

A template of tasks to create for a trip, stored in `core.settings` as `travel.checklist.<anchor>.<name>` where `<anchor>` is `start` or `end` (the trip date the offset counts from) and the value is a **signed** integer of days: negative = before the anchor, `0` = the anchor day, positive = after it. The task title is the name with `-` / `_` as spaces. Anchoring in the key lets a post-trip task (`end.send-photos` = `3`) ignore the trip's length. A key with an unknown anchor or no name, or a value that is not an integer, is ignored with a WARNING. Names are lowercase letters, digits, `-` and `_` and unique across both anchors (a duplicate is a 409).

- **Defaults** are written the first time the template is read (marker row `travel.checklist_seeded`, so deleting every item does not bring them back): `start.passport-validity` -60, `start.travel-insurance` -30, `start.currency` -14, `start.sim-or-esim` -7, `start.plug-adapter` -7, `start.online-check-in` -1, `end.link-trip-charges` 2, `end.unpack-and-laundry` 1.
- **API**: `GET /travel/checklist-template`, `PUT /travel/checklist-template/{anchor}/{name}` (`offset_days`), `DELETE` the same path. `POST /travel/trips/{id}/checklist` creates one normal task per item titled `"<title> (<trip name>)"`, due the day of `anchor date + offset` at 23:59 (moved to today if already past); an item whose task (same title) exists is skipped, so pressing it twice is safe. Tasks go through `TaskService` (Notion sync, overload and the normal reminder rules apply: a task reminds from its due day on).
- **Portal**: a *Pre-trip checklist* card on `/travel` (items grouped *Around departure* / *After the trip*, inline offset edit, delete, add row) and a *Generate checklist* button on the trip page.

## Calendar events for visits

A **planned** visit of a trip with a day **and** a time gets a calendar event (`visits/calendar_sync.py`, through `CalendarEventService`, so it reaches Google). The id is kept in `visits.calendar_event_id` (migration 087; unique, and an event belongs to one leg, stay or visit, else 409; a deleted event just unlinks).

- **Event**: title = place name, location = place address (else name + city), description = Maps link + visit notes, length = `travel.visit_duration_min` (default 90, in `/travel/settings`), profile `normal`, organizer tags = the trip's default tags (looked up case-insensitively, created if missing), time zone = the stay covering that day, else the local zone.
- **Edits**: changing a visit's day, time, place or trip moves the linked event's **start/end** (length kept) and **location** only, never title or description. A recurring, guest-invited or all-day event is left alone. Giving a time to an unlinked planned visit creates the event; clearing the time or day leaves the event untouched.
- **Failures** (Google not authorised, API down) are logged at WARNING and never fail the visit write.
- **Delete**: `DELETE /travel/visits/{id}?delete_event=true|false` (default false). The portal asks whether to delete the event too.
- **Link / unlink** (`travel/event_links.py`): `calendar_event_id` on `POST`/`PATCH` of visits, and on `PATCH` of legs and stays (null unlinks; the event is kept). The event must exist (404) and belong to at most one leg, stay or visit (409). Linking does not rewrite the event. Alfred does not distinguish events it created from events you linked.
- **Warnings** (visits only, from Alfred's local calendar copy, so Google edits show after the next calendar sync; legs and stays are never compared): `no_calendar_event` (a planned visit dated today or later, with a time, has no event: never created, deleted or unlinked), `linked_event_mismatch` (the event starts on another day or time, compared in the event's own zone) and `linked_event_not_updated` (a mismatch on a recurring, guest-invited or all-day event, which Alfred never rewrites).
- **Repair**: `POST /travel/visits/{id}/event` with `action` = `create` (make the event), `update_event` (push the visit's day, time and place to the event) or `update_visit` (take the event's day and time); 422 with the reason when nothing changed. The portal offers these on the visit row next to *Link event* / *Unlink event* (also on legs and stays).

## During the trip: today

`GET /travel/trips/{id}/today` (`trips/today.py`) returns the traveler's calendar day (in the zone of the stay covering now, else the home zone), the next timeline step with `minutes_until_next`, today's visits and how many are still unmarked (`to_mark`). Portal: `/travel/{id}/today` (mobile-friendly card; linked from an ongoing trip) with one-tap Visited / Missed, an optional grade and a quick note appended through `PATCH /travel/visits/{id}`. Command: `travel_trip today` / `/today` (the ongoing trip when no trip is given); not in the Telegram menu.

## Around the trip: other events, weather, while away, print

- **Unlinked charges**: the card shows the first 5 and a *See all N* link to `/travel/{id}/unlinked`, which lists every charge with the same link controls.
- **Warnings page**: the trip page shows the first 5 warnings of each kind and the first 5 other calendar events, each with a *See all* link to `/travel/{id}/warnings`, which lists every group (warning kinds plus other events) in foldable sections with a fold/unfold-all toggle.
- **Other calendar events and snoozing (25, S)**: a *trip event* is a calendar event linked to a leg, stay or visit, or carrying an organizer tag that matches one of the trip's default tags (case-insensitive); a trip with no default tags relies on links alone. `GET /travel/trips/{id}/other-events` lists the others inside the trip dates (recurring ones expanded per day) with `snoozed`; the portal shows them as a warning card. With `travel.snooze_other_events` on (`/travel/settings`, default off, a switch on `/travel`), `CalendarNotificationService.build_due_digest` skips the reminders of those occurrences (`other_events.py`, loaded once per run). It fails open: any error while evaluating means everything is reminded. Only reminders change; the events stay in the calendar.
- **Weather (8)**: `GET /travel/trips/{id}/forecast` gives daily min/max and precipitation per stay city, only for the days a stay in that city covers (check-in to check-out date; two separate stays skip the days between) (`trips/forecast*.py`, Open-Meteo): the forecast when the trip starts within 14 days (or is ongoing), else last year's same dates from the archive, nothing for a finished trip. Cities use the place's coordinates, else are geocoded by name; results are cached in memory for an hour; if Open-Meteo fails the response is `available: false` with a message and nothing else breaks. A day is `rain` from 2 mm.
- **While away (26)**: `GET /travel/trips/{id}/while-away` lists contact birthdays, active tasks with a deadline, and the recurring expenses that will be created inside the trip dates (`trips/while_away*.py`).
- **Stay essentials (31)**: stay rows in the timeline link pharmacy, supermarket and ATM searches near the stay, like the cafe and restaurant links.
- **Print (10)**: portal-only `/travel/{id}/print`, a day-by-day page (legs with flight numbers and booking refs, stays with addresses and booking refs, visits with times and Maps links; missed visits left out) with a print stylesheet for "Save as PDF".

## During the trip: moving visits and notes

- **Move visits (16)**: `POST /travel/trips/{id}/visits/move` (`from_date`, `to_date`, optional `visit_ids`, optional `only_tag`) moves the planned visits of one day to another through the normal visit update, so linked calendar events move in place; a visit that fails is returned in `failed` and the rest still move. Travel tags are free-form: `Outdoor` / `Indoor` are a convention (tag the place), not seeded. The portal offers *Move visits* on a rainy forecast day that has planned visits.
- **Quick note (17)**: `travel_visit note` / `/tnote <text>` appends `[YYYY-MM-DD HH:MM] text` (in the trip's current zone) to the latest visit of the ongoing trip whose day and time have already passed (a visit with no time counts from the start of its day; missed ones never); it re-embeds the notes. If no visit has started yet it replies with a hint and writes nothing. Not in the Telegram menu.
- **Place history (23)**: the visit and stay dialogs show, under the place picker, the place's derived grade, its tags (such as *Would return*) and a link to its history.
- **Empty days (9)**: the itinerary lists upcoming days with no visit.

## Briefings and nudges

- **Briefings (15)**: while a trip is ongoing, the morning briefing context gets a trip block (day N of M, today's legs, check-ins/outs and visits in time order, the leave-home time on the first flight's day, spend so far from linked costs) and the evening digest says how many of today's visits are still to be marked visited or missed (`features/travel/briefing.py`). A failing trip block is logged and left out; it never fails the briefing.
- **Grade nudge (39)**: `TravelReminderService` adds `travel_grade_nudge` one and seven days after `end_date` when the recap still has visited visits or stays without a grade or notes: one reminder per day, linking `/travel/{id}/recap`. Trips that ended up to 7 days ago are loaded for it.

## After the trip: recap and search

`GET /travel/trips/{id}/recap` (portal `/travel/{id}/recap`, command `travel_trip recap`) builds the recap from the trip with **all** its visits (hidden ones included) and its costs, in `features/travel/recap/builder.py`:

- **Numbers**: days, legs, stays, visits visited / missed / never done, spend (total, by kind, with the unconverted count), the cities and countries of its stays and of visits that actually happened.
- **To complete**: every visited visit and every stay still lacking a grade and/or notes (blank notes count as missing), by date. Planned and missed visits are never asked for a grade.
- **Highlights**: visits and stays graded 4 or 5, best first.

**Fixing the gaps**: each *Still to write down* row has an *Edit* link to `/travel/{trip}?all_visits=1&edit=visit-<id>` (or `stay-<id>`), which opens that visit's or stay's edit dialog on the trip page.

Search and filters: trips by `city` / `country` (a stay or visit in a place there), as well as status, tag, name and date range; places by kind, city, country, tag, minimum grade, `ungraded` (no grade from any visit or stay), visit status and `no_trip`.

## Leave-home time and reminders

If a trip's first leg is a flight, the trip detail has `leave_home_at` (departure minus `travel.airport_buffer_min` minus `travel.home_to_airport_min`, both runtime settings in `core.settings`) and a `leave_home` timeline item. Reminders (trip starts, online check-in, time to leave, check-out day) are described in [reminders-overload.md](reminders-overload.md#travel-reminders).

## API

`/travel/trips` (list filters: `status` = current (default) / upcoming / ongoing / past / all, repeated `tag`, `q`, `city`, `country`, `date_from`, `date_to`, `limit`, `offset`), `/travel/legs`, `/travel/stays`, `/travel/visits` (filters `trip_id`, `place_id`, `status`, `date_from`, `date_to`, `no_trip`), `/travel/places` (filters `q`, `kind`, `city`, `country`, repeated `tag`, `min_grade`, `ungraded`, `status` = has a visit with it, `no_trip` = no visit or stay belongs to a trip; `GET /{id}` returns the history; deleting a place with visits or stays is a 409), `/travel/settings` (GET/PUT), `/travel/trips/{id}/costs`, `/travel/trips/{id}/recap`, `/travel/trips/{id}/map`, `/travel/trips/{id}/calendar-events`, `/travel/{kind}/{id}/transactions`, `/travel/tags` (usage counts, rename, delete removes only link rows). Postman: `postman/travel.collection.json`.

## Portal

`/travel`: reminder settings form, the pre-trip checklist card and a trips list with status, text, date-range and tag filters (HTMX partial `/travel/list`, `limit + 1` pagination). `/travel/{id}`: header with inline edit, warnings, then (side by side from the `lg` breakpoint, stacked on mobile) the day-grouped timeline, cut to its first 8 steps with a *See all N steps* link to `/travel/{id}/timeline` (the full timeline on its own page), and the itinerary (visits by day, mark visited/missed, add/edit/delete, a toggle for hidden ones), legs and stays with add/edit/delete dialogs, a cost card and per-item cost chips, a linked-transactions dialog on every leg, stay and visit, *Import from calendar*, *Apply default tags* and a *Recap* link; `/travel/places` (filterable list) and `/travel/places/{id}` (edit, tags, derived grade, visit and stay history, plan a visit); a new hotel can be created inline in the stay dialog. Writes proxy through `/travel/{trips,legs,stays,places,visits}`, `/travel/links/{kind}/{id}` and `/travel/transactions/search`.

## Assistant layer

- **Commands** (handler `app/assistant/commands/handlers/travel.py`, one MCP tool per group): `travel_trip` (list, get, add, update, delete, costs, recap, apply_tags), `travel_leg` / `travel_stay` / `travel_visit` (add, update, delete, link, unlink; visits also `visited` / `missed` and `list`), `travel_place` (add, list, get, update, delete). Telegram aliases follow the pattern `/trips`, `/trip`, `/tripadd`, `/legadd`, `/stayadd`, `/placeadd`, `/places`, `/place`, `/visitadd`, `/visits`, `/visited`, `/missed`, `/leglink`, ...; only `/trips`, `/trip` and `/visited` are in the Telegram menu, the rest are typed.
- **References by name**: `trip get` takes an id, a name fragment (a current trip first, then the latest past one) or `next` (the soonest upcoming or ongoing trip); `place get` needs an id or an exact name. `visit add` takes a place id or name: a name reuses the place with that exact name (narrowed by `--city`) or creates one of `--kind` (default `other`). `stay add --hotel` does the same with kind `hotel`.
- **Times**: legs need both zones (`--departs-tz`, `--arrives-tz`); a missing zone is a 400 that names the field. An empty value on an update clears the field.
- **Natural language**: intents `travel_trip.list` and `travel_trip.get` (extraction schema `TravelTripGetArgs`, field `trip`, or `next`); both are reads. Writes are slash/MCP only.
- **Recall**: the `notes` columns of trips, legs, stays, visits and places are embedded (`trip_note`, `leg_note`, `stay_note`, `visit_note`, `place_note`; `app/features/travel/notes_index.py`) with a label prefix such as `Stay at Hotel Example: ...`, and `recall` searches them. The index follows create / edit / clear / delete; deleting a trip also drops its legs' embeddings.
