---
name: alfred-day-planning
description: Plan or replan a day or a week with Alfred's day_plan tool. Use when the user asks to plan their week or day, or to replan after a change (new event, exception, missed items).
---

# Day and week planning with Alfred

Alfred only gathers facts and stores what was agreed; you do the scheduling. Mechanics and field semantics: `docs/modules/planning.md`. The user's own routines, people and habits are **not** in this file: they come from the `preferences` of every `day_plan get` (wake/sleep, work target, office goal, `travel_times`, `conventions`) and from memory. If a rule you need is missing, ask once and offer to store it in `planning.conventions`.

Fixed commitments (pickups, classes, appointments), recurring tasks and activity targets are Alfred data and come back from `get`; don't ask the user to repeat them and don't hard-code them here.

Always look at the whole week, even when asked about one day, to check constraints and spread tasks.

## Flow (one round when possible)

0. **Weekly planning only: ask about work meetings first.** Ask whether all of the week's work meetings are in Alfred's calendar (they are easy to forget, and a plan without them is wrong) and wait for the answer, unless the user already said so or asked you to plan without asking; then say in the summary that meetings may be missing.
1. **One call for the data:** `alfred_day_plan get` with `date` = first day and `days` = days left through Sunday (max 7). The result already includes `saved_plan`; don't call `get_saved` for the same range. Read `preferences` and `warnings`.
2. **Weekly planning only:** load last week once (`get_saved`, or `review` for per-item planned/done/missed counts). Look for patterns (time of day, kind of item), not single misses. Skip when replanning mid-week.
3. **Holidays and trips:** `holidays` lists a day's public holidays as "Name (PT)", from the planning calendar only (the first `HOLIDAY_CALENDARS` entry); whether they are days off comes from `conventions` (ask once and offer to store it if missing). `trips` marks days the user is away or travelling: plan only around the trip's `agenda`, nothing at home, and finish before `leave_home_at` on the departure day. List recurring events on trip days and offer to `skip` them.
4. **Find conflicts before planning:** check every `cant_miss` and `important` event against its travel blocks and fixed commitments. Overlaps are reported in `warnings`, never resolved. Meetings can shift an hour in UTC around US/EU daylight-saving changes (late Oct / early Nov, March).
4a. **Where the user is and how they travel:** an event's `location` (with `location_id`) is one of the user's frequent places. Travel blocks are derived from them: Home → first place → next place → Home, none between two events at the same place, none for remote, free or all-day events. A block between two places carries `options` (every saved mode with its minutes); its length follows the fastest public transport, or walking when it is at most `walk_tolerance_minutes` longer. When a car option is much faster (about 15 min or more) than the chosen mode, ask "can you take the car for this one?". A block with `assumed: true` (and its `warnings` line) is a guess of `default_travel_minutes`, not a fact: ask for the real minutes and offer to save them (`alfred_location update <place> --from <origin>:<mode>=<minutes>`), to set the event's `travel_minutes`, or to mark the event remote or free. Don't add `transport` blocks for legs that already have a travel block.
5. **Ask only about real conflicts** you can't solve from `preferences`: at most 3 questions, together with the proposal. Beyond that, protect `cant_miss` items and say what you chose. If the request is clear, plan and save without asking.
6. **Suggest meeting moves:** plan around meetings as they are, then look for moves that would save time or make a day easier: a meeting that forces a home day on an office day (or a commute for one call), one outside the hours in `conventions`, one that squeezes travel to a `cant_miss` commitment, a short gap between meetings that wastes a focus block, scattered meetings that could be clustered, or one on top of a habit when a free slot is nearby. Suggest at most 3, each with the new slot and the gain. Suggest only: others are in the meeting and `reschedule` writes through to Google, so move one with `alfred_event` `reschedule` only after the user confirms it moved (or owns it and asks), then replan the affected days.
7. **Errands:** collect what needs doing outside: the `shopping` section of `get` (pending and due counts, a suggested run, counts `by_category`), tasks with `context` "out", and anything running out. Use the category counts and the category-to-shop rules in `conventions` to decide which places are needed (supermarket, pharmacy, other shop); call `alfred_shopping` list only when you place a stop and need the item names for its title. Place each stop next to where the user already is (on the way back from a fixed commitment, near the office on an office day, after the gym), never before a fixed appointment. Prefer a short stop at a close shop for a few urgent items and one bigger run for the rest; don't plan a dedicated trip for one or two items that can wait. Use `travel_times` for the shop; if the place is missing, ask once and offer to store it. Save a stop as an `other` block named after the place and its purpose, with a `transport` leg if it isn't on an existing route.
8. **Calendar changes:** don't change a recurring series for a one-off exception; use `alfred_event` `skip` / `reschedule` on the occurrence, or put the exception in the plan and its day notes. Create or delete events only when the office/work counts need them. An event you create at one of the user's places (an office day at the office) gets `location_id` (the location's id or name, e.g. `location_id: "Office"` on `alfred_event add`) instead of `travel_minutes`; leave the free-text `location` alone (it goes to Google). Check the next `get`: the event carries `location_id` and travel blocks such as "Home → Office (metro, 50)" surround it. An "Unknown location" error means the name is wrong: `alfred_location list`. Link an existing event the same way with `alfred_event update` (`id` + `location_id`; on a series it covers every occurrence). No `location_id` parameter on `alfred_event` means the tool schema is stale: restart the mcp container. Locations are for frequent places only: a one-off appointment gets `travel_minutes` (ask) or nothing. When unlocated events with the same calendar location (or title) keep coming back with travel minutes, propose making that place a location with its travel times and linking the events.
9. **Save only the days that changed.** `save` takes `days` as a JSON string `[{"date","items","notes"}]`. Every item needs a UTC offset and must start on its date (local). Notes are short and explain the shape of the day. For a small change to a saved day, `edit` (replace blocks in `[replace_from, replace_to)`) keeps the other blocks and their flags.
10. **Reply briefly:** what changed and why, deadline/data problems (wrong deadline, task open after its deadline), meeting moves worth asking for (step 6), the errands you placed and where, and one next step if there is a real one. Don't restate the plan.

## Planning principles

- Deadline and overdue work tasks get the first slot of the morning.
- Anchor habits to things that already happen (meals, a commute, shutdown). Don't plan them as floating items.
- Give habits a sensible minimum length and a realistic weekly target; check `review` before inflating one.
- Batch errands next to wherever the user is already going, and after a fixed appointment, not before (step 7).
- Don't overload weekends. Keep late evenings free: items planned after the user's usual shutdown are the ones that get missed.
- Tasks with no estimate default to 30 min and are listed in `warnings`. For known long ones assume more, say so in the item note, and write the answer back with the task `update` action.
- Overlapping items are fine when one is passive (a podcast during a commute).
- Work target is per workday (`workdays` preference); weekends have none unless `work_minutes` is passed.

## Block kinds

- With `ref_id`: `event`, `task`, `study_item`, `activity`, `routine_step`, `routine_block`.
- Free-form, no `ref_id`: `work` (focused work that isn't a task; counts toward committed work), `transport` (a commute or trip leg that is not already a travel block of the timeline, e.g. the commute of an office day that has no event yet), `meal`, `break`, `other`.

## Review loop

`miss` / `unmiss` / `done` / `undone` (by date + `ref_id`, or title) mark blocks of a saved version in place: no new version, the task stays open. A block with neither flag is unmarked, not known-done. When a miss pattern becomes a rule, propose adding it to `planning.conventions` so every client gets it.

## If a call is rejected as unknown

The mcp container fetches the command catalog once at startup. An unknown kind or action (`transport`, `work`, `meal`, `edit`, `review`, `miss`) means the tool schema is stale: restart the mcp container.
