# Places (everyday and trip places)

Every place the user knows lives in one table, `location.places`: home, the office, school, the gym and the shops they use, and the hotels, restaurants and sights of trips. What a place **is** belongs to the `location` domain; how it is **used** belongs to the domain that uses it (class-table inheritance, migration 101):

- **Everyday role** (`organizer`): `organizer.everyday_places` marks a place as one of the user's everyday places (the "Locations" list, the day plan, `--sells`, the event *At* picker). What it sells and the travel times between places hang off the place id in organizer. The Home place is always everyday and has no row.
- **Trip role** (`travel`): visits, stays, travel tags and links point at the place id; the grade is derived from them. See [travel.md](travel.md).

`location` never imports organizer or travel: each role tells it what it holds through `PlaceHooks` (`features/location/hooks.py`; organizer's `OrganizerPlaceHooks`, travel's `TravelPlaceHooks`, wired in `dependencies.py`).

Code: `backend/app/features/location/places/` (base), `features/organizer/everyday_places/`, `features/organizer/travel_times/`, `features/travel/places/` (travel's view). Portal: `/locations` (everyday places), `/travel/places` (trip places). Command: `place`, MCP `alfred_place` (every place, both roles). API: `/location/places` (the place itself), `/organizer/places` (everyday view), `/travel/places` (travel view).

## Table

`location.places` (migration 101, from `travel.places`, whose ids are kept, plus every old `organizer.locations` row): `name`, `kind` (one of `PLACE_KINDS`, CHECK `ck_places_kind`), `city_id` (required, RESTRICT), `address`, `maps_url`, `latitude` and `longitude` (`Numeric(9, 6)`, both or neither, CHECK `ck_places_coordinates`), `opening_hours` (JSONB, null = unknown), `notes`, `active` (false = archived), `created_at`, `updated_at`.

- **City** is required. Left out (`POST /location/places`, `POST /organizer/places`, the `place` command), it is the Home place's city; with no Home place that is a 422. Migration 101 gave every old location the `travel.home_city_id` setting's city (a database with locations and no home city, such as a fresh install, gets a placeholder "Home city" in "Unknown", made the home city).
- **Names** are unique per city ignoring case (`uq_places_name_city`, archived places included; the service checks first and answers 409): two "Starbucks" in different cities are fine. Name lookups (`place show gym`, `event --at school`, visits and stays) try the everyday places first, then the places in the home city, then any city; several matches elsewhere are a 409 listing them.
- **Kind** is one of a fixed set defined once in `app/features/location/places/constants.py` (`PLACE_KINDS`): home, work (the office or workplace), school (also classes and courses), gym, sports (pool, pitch, club), supermarket, pharmacy, bakery, market, mall (shopping centre), variety_store (a bazaar-style shop with household goods, tools and gear), hardware_store, shop, restaurant, cafe, health (doctor, dentist, clinic), park, playground (also indoor play centres), venue (concerts, theatre, cinema), hotel (any stay), activity, museum, attraction (a sight) and other, the default. It feeds the schema `Literal`, the CHECK constraint, the command details and the extraction schema; the portal copies the everyday ones in `web/app/shared/location_kinds.py` with one Tabler icon per kind (`location_icon` filter, the pin for an unknown kind). Input is trimmed and lowercased; any other value is a 422 (400 from a command), also as a `?kind=` filter. Clients find places by kind rather than by name: the office is `list --kind work`. Only `home` has a meaning in code: at most one place is home (partial unique index `uq_places_home`, checked first in the service, 409).
- **Home** is the single source of the home address **and the home city** that trips start from (migration 095 created it from the old `organizer.home_address` travel setting; migration 102 removed the `travel.home_city_id` setting, after making sure Home was in that city). Travel reads both from it (`GET /travel/settings`, travel's "is the home city" on city pages and the city-delete check); `PUT /travel/settings` refuses `home`, `home_address` and `home_city_id`. Before Home's address or city changes (edited, cleared, Home turned into another kind or deleted), the old values are copied into trips that have already started and have none of their own, so past trips keep the home they were planned with (`PlaceService` gets a `HomeSnapshot` callable with a `HomeValues(address, city_id)` of what changed; [travel.md](travel.md#home)). The portal's edit form has a City picker (the new-location form has none: it takes Home's city) and `/locations/home` redirects to the Home place's page. After the address or city changes, the portal shows a "Home moved" note: travel times from Home are not updated automatically.
- **Coordinates** are where the weather is looked up (Home's are the default weather place, see [configuration.md](../configuration.md#2-settings-you-change-at-runtime), *Weather*). Clients send `coordinates`: text as Google Maps copies it (`"41.1579, -8.6291"`, latitude first) or `[lat, lon]`; blank or null clears them; out of range is a 422. When a place has none, they are read from its Maps link if the link carries any (`!3dLAT!4dLON`, the place's pin, wins over `?q=LAT,LON` and `@LAT,LON`, the map's centre; a short `maps.app.goo.gl` link carries none): on create, when coordinates are cleared, and when a new link is saved on a place without them. Pure parser: `location/places/coordinates.py`. No geocoding of addresses. Responses carry `latitude` and `longitude` (travel's old `lat`/`lng` were renamed in migration 101); the portal forms have a Coordinates field and the `place` command `--coords`.
- **What a shop sells** is its shopping categories (`organizer.places_shopping_categories`, both FKs CASCADE): deleting a category removes it from the places that sold it. A place that sells nothing is a place you go to (home, office, school), not a shop.
- **Deleting** a place (`DELETE /location/places/{id}`) asks each role first: travel times (organizer) and visits or stays (travel) hold it, and the 409 names them ("archive it instead"). Its everyday row, categories, travel tags and links go with it (CASCADE, the links' note embeddings are dropped after the commit) and calendar events let go of it (SET NULL). Archive (`active = false`) hides it from the active lists and keeps it.

## API

- `/location/places`: `GET` (filters `kind`, `city_id`, `country_id`, `active`, `q` over name, address, city and country), `POST`, `GET/PATCH/DELETE /{id}`. Returns the base place only: `city` (with its country), `today`, `opening_hours_text`, `maps_link`.
- `/organizer/places`: `GET` lists the everyday places (members plus Home; filters `kind`, `active`, `category_id`, `q`), `POST` creates a place that is everyday from the start (with `category_ids`), `GET /{id}` is any place as the everyday role sees it (`everyday`, `categories`), `PUT /{id}` adds an existing place to the everyday list (idempotent), `DELETE /{id}` takes it off (the place stays; Home is a 409). `GET/PUT /{id}/categories`, `GET/PUT /{id}/travel-times`, `DELETE /organizer/travel-times/{id}`.
- `/travel/places`: travel's view (tags, derived grade, visits and stays), plus `POST` and `PATCH` that create or edit a place with its tags and its city by name in one call. There is no `DELETE` there.

## Opening hours

Stored per weekday plus `hol` for public holidays: `{"mon": [["08:00", "20:00"]], "sat": [["09:00", "13:00"], ["15:00", "19:00"]], "sun": [], "hol": []}`. A missing key is unknown, an empty list is closed, several ranges allow a lunch break. Overnight ranges are not supported; `24:00` is a valid end.

Everyone writes them as text, parsed by one pure module (`locations/hours.py`, on top of the weekday and HH:MM helpers in `app/shared/utils/time_text.py`):

```
mon-fri 08:00-20:00; sat 09:00-13:00, 15:00-19:00; sun closed; holidays closed
```

Segments are separated by `;` or new lines. Days are names (`mon`, `monday`), ranges (`mon-fri`, `fri-mon` wraps), lists (`mon,wed`), `daily` or `holidays`. Times are `H`, `H:MM` or `HH:MM`. A day given twice, overlapping ranges or an end before the start are refused with a message that names the part (422 with a plain-text `detail`, which the portal shows as is). The API also accepts the JSON object. Responses carry both forms: `opening_hours` and `opening_hours_text` (canonical text: consecutive days with the same hours are grouped).

## Travel times

`organizer.travel_times` (migration 096 as `location_travel_times`, keyed by place ids since migration 101): door-to-door minutes from one place to another by one `mode` (free text, lowercase: foot, metro, car...), 1-600, unique per (origin, destination, mode), `origin <> destination`. A route counts both ways unless the reverse is saved too. Both FKs are RESTRICT: deleting a location that has travel times is a 409 naming them (delete them first, or archive the location). At most 60 in total. Alfred never estimates them: they are typed by the user (portal, command, `/plan`) or by Claude after asking.

- `GET /organizer/places/{id}/travel-times` lists the routes that start or end there; `PUT` the same path with `{destination_id, mode, minutes}` saves a route from that place (the same route again updates the minutes); `DELETE /organizer/travel-times/{id}`.
- The planning settings still read and write them as `travel_times` (`TravelTimeService.as_preferences` / `replace_from_preferences`): see [planning.md](planning.md). A name is Home, an everyday place, then a place in the home city; one that is none becomes a new everyday place (office as `work`, school, gym, else `other`). Migration 096 turned the old `planning.travel_times` setting into rows; its downgrade writes the setting back.
- Portal: a Travel times card on each location (5 rows, "See all N" opens `/locations/{id}/travel-times`) with a form to add or update a route from that location, and delete buttons.
- Command: `place add/update ... --from home:metro=20,foot=35;office:car=10` saves routes from existing places to this one (everyday places only); `place show` lists its travel times.

## Events at a place

`organizer.calendar_events.place_id` (migration 097 as `location_id`, renamed and pointed at `location.places` in migration 101, FK `ON DELETE SET NULL`, null) says where an event happens. It is Alfred-only: stripped before every Google call and never written by sync.

- **Calendar text follows the link.** The event's free-text `location` is only for Google Calendar (a Maps link there). When an event is created or linked and that text is empty, or still holds the previously linked location's address or name, Alfred writes the location's address on one line (else its name) into it, so that update does go to Google. It never replaces text the user typed or edited in the same update, never touches events with invitees (someone else's meeting would change for everyone), and without Google authorization the link is saved alone. Nothing is backfilled and sync never sets the link. A link change that leaves the text alone (typed text, invitees, unlinking) skips Google. On a recurring series it is on the master row, so every occurrence (moved ones too) is there. Deleting a place sets its events' `place_id` to null (no 409). An unknown id is a 422.

- **Frequent places only.** A one-off appointment keeps a number on the event (`travel_minutes`) or nothing; a place the user goes to often becomes a location with its travel times, and its events link to it.
- **Day plan:** events carry `location` (the location's name, never the calendar text) and `place_id`, and get no travel blocks: the client routes the day from the travel times in `preferences` ([planning.md](planning.md#travel)).
- **API:** `place_id` on `POST/PATCH /organizer/calendar-events`, and `GET /organizer/calendar-events?place_id=` lists the events at a place.
- **Portal:** the event form has an *At* picker (active locations, then archived ones, then *+ New location…*: name, kind and minutes from Home per mode, `metro=20, foot=35`; it needs a Home location when minutes are given). When an event without a location has a calendar location text equal to an active location's name or address (case and spaces ignored), the day view pre-selects it; nothing is linked automatically, not even on sync. Each location's page lists its events of the next 60 days (5, then "See all N" opens `/locations/{id}/events`).
- **Command:** `event add/update ... --at <location id or name>` (empty clears it). `--location` stays the calendar's free-text location, which is sent to Google.
- **Archived locations** keep their travel times in the planning `travel_times` list: the `/plan` form replaces the whole list, so hiding them there would delete them on the next save.

## Today and holidays

Every place response from `/location/places` and `/organizer/places` has `today`: the local date, today's `hours` ("08:00-20:00", "closed" or null when unknown), `holiday` (names), a `note` and `open_now` (null when unknown).

Holidays come from the **first calendar in `HOLIDAY_CALENDARS`** (PT by default), the planning holiday calendar (`get_planning_holiday_provider` in `dependencies.py`, also the source of the day plan's `holidays`). The other calendars (BR) still show on the dashboard and in the briefing, but do not close shops. On a holiday a location uses its `hol` hours; when those are unknown it shows the weekday hours with the note "holiday, hours unknown" and `open_now` is null. The holiday lookup runs once per request, only when some listed location has hours, and a failing provider counts as no holiday.

## Portal

`/locations` lists cards in three groups: Places (home first, then the other locations that sell nothing), Shops, Archived. Each card shows "Open now"/"Closed", today's hours and up to 5 categories. `/locations/{id}` shows the week's hours with today highlighted, the address with an "Open in Maps" link (the saved link, else a Maps search for the address; never an API call), what it sells and notes, plus Edit, Archive/Restore and Delete. The form takes the hours as text, one segment per line.

## Command and chat

`place` add / list / show / update / grade / archive / unarchive / delete (`/placeadd`, `/places`, `/place`, `/placeupdate`, `/placegrade`, `/placearchive`, `/placeunarchive`, `/placedelete`; MCP `alfred_place`); not in the Telegram menu. It replaced `location` and `travel place` (handler `app/assistant/commands/handlers/place.py`, which composes the three domains' services). Every action but `add` takes an id or a name (see *Names*; `--city`/`--country` narrow the lookup, except on `update` where `--city` moves the place).

- **add**: `--kind` (default other), `--city` (id or name, default the home city; a new city needs `--country` and is created), `--everyday`, `--address`, `--maps`, `--coords`, `--hours`, `--notes`, `--tags` (travel tags), `--sells`, `--from`. `--everyday` defaults to true for home, work, school, gym, sports, supermarket, pharmacy, bakery, market, mall, variety_store, hardware_store, health and playground, to false for hotel, activity, museum and attraction (`organizer/everyday_places/constants.py`), and must be given for the rest: the command answers 400 so the client asks the user. Home can't be `--everyday false`. Everything is validated (categories, `--from` origins, the city) before the first write.
- **list**: `--view everyday` (default: the everyday places and Home, today's hours, what they sell; filters `--kind`, `--sells`, the search argument), `visited` (places with a visit of any status or a stay: grade, grade count, tags; `GET /travel/places?has_visits=true`) or `all`. `--city`, `--country`, `--tag`, `--min-grade` and `--ungraded` filter the visited and all views (on the everyday view they are a 400). Archived places are left out unless `--all true`.
- **show**: the base place plus `everyday`, `sells`, `travel_times`, and when it has any travel data `grade`, `tags`, `visits`, `stays`, `lifetime_cost`.
- **update**: the same fields plus `--name`; `--sells` and `--tags` replace their lists; `--everyday true/false` adds the place to the everyday list or takes it off (the place stays); `--active false` archives.
- **grade**: `place grade Cafe Example 4` (or `--grade`), optional `--date` (default today) and `--notes`: a visited visit with no trip, so a restaurant in the home town can be graded. For a visit during a trip use `travel_visit`.
- **delete**: refused (409) while the place has travel times, visits or stays; archive it instead.

`--sells` takes shopping category names (unknown names are a 422) and, like `--from`, is for everyday places only (400 otherwise).

The command details tell Claude it may search the web for a shop's opening hours, show what it found with the source and save them only after the user confirms (Alfred itself never searches), and never to estimate travel minutes from addresses. Intents: `place.add` ("add the pharmacy near school", with extraction of name, kind, everyday, address, hours and categories), `place.list` and `place.grade` ("give Cafe Example a 4", with the place, grade, date and notes).

**No maps provider.** Alfred never computes distances or fetches opening hours; address and Maps link are for the user. Restart the MCP container after a deploy that changes the command.

## Planned

Phase 5 of the locations plan: the day plan proposes concrete shopping stops.
