# Locations (frequent places)

The user's everyday places: home, the office, school, the gym and the shops they use. Each one has an address, a Maps link, opening hours and the shopping categories it sells. They anchor the day plan: where the user is, and which open shop sells what is on the list. Trip sights are a different thing (`travel.places`, see [travel.md](travel.md)); the two are not merged, so a supermarket needs no city and the office needs no grade.

Code: `backend/app/features/organizer/locations/`. Portal: `/locations`. Command: `location`, MCP `alfred_location`. API: `/organizer/locations`.

## Table

`organizer.locations` (migration 094): `name` (unique case-insensitively, archived rows included), `kind` (free text, trimmed and lowercase), `address`, `maps_url`, `opening_hours` (JSONB, null = unknown), `notes`, `active` (false = archived), `created_at`, `updated_at`.

- **Kind** is free text. The portal suggests home, work, school, gym, supermarket, pharmacy, bakery, market and other; the default is `other`. Only `home` has a meaning in code: at most one location is home (partial unique index `uq_locations_home`, checked first in the service, 409).
- **Home** holds the home address that trips start from (migration 095 created it from the old `organizer.home_address` travel setting, which is gone). Travel reads it; `PUT /travel/settings` refuses `home_address`. Before Home's address changes (edited, cleared, Home turned into another kind or deleted), the old address is copied into trips that have already started and have no home address of their own, so past trips keep the home they were planned with ([travel.md](travel.md#home)). After the address changes, the portal shows a "Home moved" note: travel times from Home are not updated automatically.
- **What a shop sells** is its shopping categories (`organizer.locations_shopping_categories`, both FKs CASCADE): deleting a category removes it from the locations that sold it. A location that sells nothing is a place you go to (home, office, school), not a shop.
- Deleting a location is a hard delete for now. Archive (`active = false`) hides it from the active list and keeps it.

## Opening hours

Stored per weekday plus `hol` for public holidays: `{"mon": [["08:00", "20:00"]], "sat": [["09:00", "13:00"], ["15:00", "19:00"]], "sun": [], "hol": []}`. A missing key is unknown, an empty list is closed, several ranges allow a lunch break. Overnight ranges are not supported; `24:00` is a valid end.

Everyone writes them as text, parsed by one pure module (`locations/hours.py`, on top of the weekday and HH:MM helpers in `app/shared/utils/time_text.py`):

```
mon-fri 08:00-20:00; sat 09:00-13:00, 15:00-19:00; sun closed; holidays closed
```

Segments are separated by `;` or new lines. Days are names (`mon`, `monday`), ranges (`mon-fri`, `fri-mon` wraps), lists (`mon,wed`), `daily` or `holidays`. Times are `H`, `H:MM` or `HH:MM`. A day given twice, overlapping ranges or an end before the start are refused with a message that names the part (422 with a plain-text `detail`, which the portal shows as is). The API also accepts the JSON object. Responses carry both forms: `opening_hours` and `opening_hours_text` (canonical text: consecutive days with the same hours are grouped).

## Travel times

`organizer.location_travel_times` (migration 096): door-to-door minutes from one location to another by one `mode` (free text, lowercase: foot, metro, car...), 1-600, unique per (origin, destination, mode), `origin <> destination`. A route counts both ways unless the reverse is saved too. Both FKs are RESTRICT: deleting a location that has travel times is a 409 naming them (delete them first, or archive the location). At most 60 in total. Alfred never estimates them: they are typed by the user (portal, command, `/plan`) or by Claude after asking.

- `GET /organizer/locations/{id}/travel-times` lists the routes that start or end there; `PUT` the same path with `{destination_id, mode, minutes}` saves a route from that location (the same route again updates the minutes); `DELETE /organizer/locations/travel-times/{id}`.
- The planning settings still read and write them as `travel_times` (`LocationTravelTimeService.as_preferences` / `replace_from_preferences`): see [planning.md](planning.md). Migration 096 turned the old `planning.travel_times` setting into rows, creating a location for each name that was not one (office as `work`, school, gym, else `other`); its downgrade writes the setting back.
- Portal: a Travel times card on each location (5 rows, "See all N" opens `/locations/{id}/travel-times`) with a form to add or update a route from that location, and delete buttons.
- Command: `location add/update ... --from home:metro=20,foot=35;office:car=10` saves routes from existing locations to this one; `location show` lists its travel times.

## Events at a location

`organizer.calendar_events.location_id` (migration 097, FK `ON DELETE SET NULL`, null) says where an event happens. It is Alfred-only: stripped before every Google call, never written by sync, and an update that only changes it skips Google. On a recurring series it is on the master row, so every occurrence (moved ones too) is there. Deleting a location sets its events' `location_id` to null (no 409). An unknown id is a 422.

- **Frequent places only.** A one-off appointment keeps a number on the event (`travel_minutes`) or nothing; a place the user goes to often becomes a location with its travel times, and its events link to it.
- **Day plan:** events carry `location` (the location's name) and `location_id`, and travel blocks between locations are derived from the travel times ([planning.md](planning.md#derived-travel)).
- **API:** `location_id` on `POST/PATCH /organizer/calendar-events`, and `GET /organizer/calendar-events?location_id=` lists the events at a location.
- **Portal:** the event form has an *At* picker (active locations, then archived ones, then *+ New location…*: name, kind and minutes from Home per mode, `metro=20, foot=35`; it needs a Home location when minutes are given). When an event without a location has a calendar location text equal to an active location's name or address (case and spaces ignored), the day view pre-selects it; nothing is linked automatically, not even on sync. Each location's page lists its events of the next 60 days (5, then "See all N" opens `/locations/{id}/events`).
- **Command:** `event add/update ... --at <location id or name>` (empty clears it). `--location` stays the calendar's free-text location, which is sent to Google.
- **Archived locations** keep their travel times in the planning `travel_times` list: the `/plan` form replaces the whole list, so hiding them there would delete them on the next save.

## Today and holidays

Every location response has `today`: the local date, today's `hours` ("08:00-20:00", "closed" or null when unknown), `holiday` (names), a `note` and `open_now` (null when unknown).

Holidays come from the **first calendar in `HOLIDAY_CALENDARS`** (PT by default), the planning holiday calendar (`get_planning_holiday_provider` in `dependencies.py`, also the source of the day plan's `holidays`). The other calendars (BR) still show on the dashboard and in the briefing, but do not close shops. On a holiday a location uses its `hol` hours; when those are unknown it shows the weekday hours with the note "holiday, hours unknown" and `open_now` is null. The holiday lookup runs once per request, only when some listed location has hours, and a failing provider counts as no holiday.

## Portal

`/locations` lists cards in three groups: Places (home first, then the other locations that sell nothing), Shops, Archived. Each card shows "Open now"/"Closed", today's hours and up to 5 categories. `/locations/{id}` shows the week's hours with today highlighted, the address with an "Open in Maps" link (the saved link, else a Maps search for the address; never an API call), what it sells and notes, plus Edit, Archive/Restore and Delete. The form takes the hours as text, one segment per line.

## Command and chat

`location` add / list / show / update / delete (`/locationadd`, `/locations`, `/location`, `/locationupdate`, `/locationdelete`); not in the Telegram menu. `show`, `update` and `delete` take an id or a name. `--sells` takes shopping category names (unknown names are a 422); on `update` it replaces the list. `list` shows active locations unless `--all`.

The command details tell Claude it may search the web for a shop's opening hours, show what it found with the source and save them only after the user confirms (Alfred itself never searches), and never to estimate travel minutes from addresses. Intents: `location.add` ("add the pharmacy near school", with extraction of name, kind, address, hours and categories) and `location.list`.

**No maps provider.** Alfred never computes distances or fetches opening hours; address and Maps link are for the user. Restart the MCP container after a deploy that changes the command.

## Planned

Phase 5 of the locations plan: the day plan proposes concrete shopping stops.
