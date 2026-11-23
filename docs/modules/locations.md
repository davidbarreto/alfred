# Locations (frequent places)

The user's everyday places: home, the office, school, the gym and the shops they use. Each one has an address, a Maps link, opening hours and the shopping categories it sells. They anchor the day plan: where the user is, and which open shop sells what is on the list. Trip sights are a different thing (`travel.places`, see [travel.md](travel.md)); the two are not merged, so a supermarket needs no city and the office needs no grade.

Code: `backend/app/features/organizer/locations/`. Portal: `/locations`. Command: `location`, MCP `alfred_location`. API: `/organizer/locations`.

## Table

`organizer.locations` (migration 094): `name` (unique case-insensitively, archived rows included), `kind` (free text, trimmed and lowercase), `address`, `maps_url`, `opening_hours` (JSONB, null = unknown), `notes`, `active` (false = archived), `created_at`, `updated_at`.

- **Kind** is free text. The portal suggests home, work, school, gym, supermarket, pharmacy, bakery, market and other; the default is `other`. Only `home` has a meaning in code: at most one location is home (partial unique index `uq_locations_home`, checked first in the service, 409).
- **What a shop sells** is its shopping categories (`organizer.locations_shopping_categories`, both FKs CASCADE): deleting a category removes it from the locations that sold it. A location that sells nothing is a place you go to (home, office, school), not a shop.
- Deleting a location is a hard delete for now. Archive (`active = false`) hides it from the active list and keeps it.

## Opening hours

Stored per weekday plus `hol` for public holidays: `{"mon": [["08:00", "20:00"]], "sat": [["09:00", "13:00"], ["15:00", "19:00"]], "sun": [], "hol": []}`. A missing key is unknown, an empty list is closed, several ranges allow a lunch break. Overnight ranges are not supported; `24:00` is a valid end.

Everyone writes them as text, parsed by one pure module (`locations/hours.py`, on top of the weekday and HH:MM helpers in `app/shared/utils/time_text.py`):

```
mon-fri 08:00-20:00; sat 09:00-13:00, 15:00-19:00; sun closed; holidays closed
```

Segments are separated by `;` or new lines. Days are names (`mon`, `monday`), ranges (`mon-fri`, `fri-mon` wraps), lists (`mon,wed`), `daily` or `holidays`. Times are `H`, `H:MM` or `HH:MM`. A day given twice, overlapping ranges or an end before the start are refused with a message that names the part (422 with a plain-text `detail`, which the portal shows as is). The API also accepts the JSON object. Responses carry both forms: `opening_hours` and `opening_hours_text` (canonical text: consecutive days with the same hours are grouped).

## Today and holidays

Every location response has `today`: the local date, today's `hours` ("08:00-20:00", "closed" or null when unknown), `holiday` (names), a `note` and `open_now` (null when unknown).

Holidays come from the **first calendar in `HOLIDAY_CALENDARS`** (PT by default), the planning holiday calendar (`get_planning_holiday_provider` in `dependencies.py`). The other calendars (BR) still show on the dashboard and in the briefing, but do not close shops. On a holiday a location uses its `hol` hours; when those are unknown it shows the weekday hours with the note "holiday, hours unknown" and `open_now` is null. The holiday lookup runs once per request, only when some listed location has hours, and a failing provider counts as no holiday.

## Portal

`/locations` lists cards in three groups: Places (home first, then the other locations that sell nothing), Shops, Archived. Each card shows "Open now"/"Closed", today's hours and up to 5 categories. `/locations/{id}` shows the week's hours with today highlighted, the address with an "Open in Maps" link (the saved link, else a Maps search for the address; never an API call), what it sells and notes, plus Edit, Archive/Restore and Delete. The form takes the hours as text, one segment per line.

## Command and chat

`location` add / list / show / update / delete (`/locationadd`, `/locations`, `/location`, `/locationupdate`, `/locationdelete`); not in the Telegram menu. `show`, `update` and `delete` take an id or a name. `--sells` takes shopping category names (unknown names are a 422); on `update` it replaces the list. `list` shows active locations unless `--all`.

The command details tell Claude it may search the web for a shop's opening hours, show what it found with the source and save them only after the user confirms (Alfred itself never searches), and never to estimate travel minutes from addresses. Intents: `location.add` ("add the pharmacy near school", with extraction of name, kind, address, hours and categories) and `location.list`.

**No maps provider.** Alfred never computes distances or fetches opening hours; address and Maps link are for the user. Restart the MCP container after a deploy that changes the command.

## Planned

Phases 2-5 of the locations plan: the home address moves from the travel settings to the Home location, `planning.travel_times` becomes rows between locations, events get a location (derived travel blocks), and the day plan proposes concrete shopping stops.
