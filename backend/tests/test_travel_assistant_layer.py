import pytest

from app.api.routes.integrations.telegram import _MAX_TOTAL_CHARS, _build_telegram_commands
from app.assistant.commands.handlers.help import handle_help
from app.assistant.commands.handlers.recall import _SOURCE_TYPES, handle_recall
from app.assistant.commands.registry import COMMAND_DEFINITIONS, COMMAND_REGISTRY
from app.assistant.commands.resolver import _resolve_fragment
from app.assistant.intents.extraction_service import TravelTripGetArgs, get_schema_for_intent
from app.assistant.intents.intent_service import get_operation_type
from app.features.travel.notes_index import NOTE_SOURCE_TYPES, TravelNoteIndex, note_text
from unittest.mock import AsyncMock, MagicMock

_TRAVEL_GROUPS = ("travel_trip", "travel_leg", "travel_stay", "travel_place", "travel_visit")


class TestRegistry:
    def test_every_travel_group_is_defined(self):
        assert set(_TRAVEL_GROUPS) <= set(COMMAND_DEFINITIONS)

    def test_descriptions_fit_the_telegram_limit(self):
        for group in _TRAVEL_GROUPS:
            for action, config in COMMAND_DEFINITIONS[group].items():
                assert 0 < len(config["description"]) <= 200, f"{group}.{action}"

    def test_no_action_uses_the_reserved_mcp_name(self):
        for group in _TRAVEL_GROUPS:
            for config in COMMAND_DEFINITIONS[group].values():
                assert "action" not in config.get("arg_keys", []) and "action" not in config.get("flags", {}).values()

    @pytest.mark.parametrize("alias,group,action", [
        ("/trips", "travel_trip", "list"), ("/trip", "travel_trip", "get"), ("/tripadd", "travel_trip", "add"),
        ("/legadd", "travel_leg", "add"), ("/stayadd", "travel_stay", "add"), ("/places", "travel_place", "list"),
        ("/place", "travel_place", "get"), ("/visitadd", "travel_visit", "add"), ("/visited", "travel_visit", "visited"),
        ("/missed", "travel_visit", "missed"), ("/leglink", "travel_leg", "link"),
    ])
    def test_aliases(self, alias, group, action):
        meta = COMMAND_REGISTRY[alias]
        assert (meta.type, meta.action) == (group, action)

    def test_every_action_that_needs_a_trip_or_place_says_so(self):
        assert COMMAND_REGISTRY["/legadd"].arg_keys == ["trip_id", "mode"]
        assert COMMAND_REGISTRY["/trip"].requires_args and COMMAND_REGISTRY["/trips"].requires_args is False


class TestParsing:
    def test_leg_add_flags_and_positionals(self):
        detail = _resolve_fragment("/legadd", [
            "1", "flight", "--from", "Alpha", "--to", "Beta", "--departs", "2031-12-17T06:30", "--arrives", "2031-12-17T10:00",
            "--departs-tz", "UTC", "--arrives-tz", "Europe/Stockholm", "--carrier", "XX", "--number", "12", "--ref", "ABC123",
        ])
        assert (detail.type, detail.command) == ("travel_leg", "add")
        assert detail.args["trip_id"] == "1" and detail.args["mode"] == "flight"
        assert detail.args["origin"] == "Alpha" and detail.args["departs"] == "2031-12-17T06:30"
        assert detail.args["departs_tz"] == "UTC" and detail.args["booking_ref"] == "ABC123"

    def test_trip_add_name_and_dates(self):
        detail = _resolve_fragment("/tripadd", ["Summer", "holiday", "--start", "2031-07-01", "--end", "2031-07-14", "-t", "Family"])
        assert detail.args["name"] == "Summer holiday" and detail.args["start"] == "2031-07-01" and detail.args["tags"] == "Family"

    def test_visited_with_a_grade(self):
        detail = _resolve_fragment("/visited", ["11", "--grade", "5", "--notes", "Lovely"])
        assert detail.args == {"id": "11", "grade": "5", "notes": "Lovely"} or detail.args["grade"] == "5"

    def test_visit_add_with_a_place_name(self):
        detail = _resolve_fragment("/visitadd", ["Vasa", "Museum", "--kind", "museum", "--trip", "3", "--date", "2031-12-18"])
        assert detail.args["place"] == "Vasa Museum" and detail.args["trip"] == "3"


class TestTelegramMenu:
    def test_menu_has_the_daily_travel_commands_within_budget(self):
        entries = _build_telegram_commands()
        commands = {e.command for e in entries}
        assert {"trips", "trip", "visited"} <= commands
        assert sum(len(e.command) + len(e.description) for e in entries) <= _MAX_TOTAL_CHARS
        assert all(len(e.description) <= 256 for e in entries)

    def test_the_rest_stay_typed_only(self):
        commands = {e.command for e in _build_telegram_commands()}
        assert not commands & {"legadd", "stayadd", "placeadd", "visitadd", "tripadd"}


class TestHelp:
    def test_summary_groups_travel_commands(self):
        groups = handle_help({})["groups"]
        assert "Travel: trips" in groups and "Travel: visits" in groups
        assert "/trips" in [e["command"] for e in groups["Travel: trips"]]


class TestIntents:
    def test_trip_list_and_get_are_reads(self):
        assert get_operation_type(["travel_trip.list"]) == "read"
        assert get_operation_type(["travel_trip.get"]) == "read"

    def test_trip_get_extracts_a_trip_reference(self):
        assert get_schema_for_intent("travel_trip.get") is TravelTripGetArgs
        assert "trip" in TravelTripGetArgs.model_fields

    def test_intents_map_to_defined_actions(self):
        for intent in ("travel_trip.list", "travel_trip.get"):
            group, action = intent.split(".")
            assert action in COMMAND_DEFINITIONS[group]


class TestRecall:
    def test_searches_the_travel_note_sources(self):
        assert set(NOTE_SOURCE_TYPES) <= set(_SOURCE_TYPES)

    async def test_a_travel_note_hit_comes_back_with_its_label(self):
        embeddings = AsyncMock()
        embeddings.search.return_value = [MagicMock(
            source_type="place_note", source_id=3, content="Cafe Example: book the terrace", similarity=0.8,
        )]
        result = await handle_recall("search", {"query": "terrace"}, embeddings)
        assert result == [{"type": "place_note", "source_id": 3, "content": "Cafe Example: book the terrace", "similarity": 0.8}]
        assert "place_note" in embeddings.search.await_args.args[0].source_types


class TestNoteIndex:
    async def test_without_an_embedding_service_nothing_happens(self):
        index = TravelNoteIndex(None)
        await index.sync("trip_note", 1, "Trip X", "notes")
        await index.remove("trip_note", 1)

    async def test_notes_are_embedded_in_the_background_with_a_label(self):
        embeddings = MagicMock()
        embeddings.delete_by_source = AsyncMock()
        await TravelNoteIndex(embeddings).sync("stay_note", 7, "Stay at Hotel Example", "  Quiet room  ")
        data = embeddings.embed_background.call_args.args[0]
        assert (data.source_type, data.source_id, data.content) == ("stay_note", 7, "Stay at Hotel Example: Quiet room")
        embeddings.delete_by_source.assert_not_awaited()

    @pytest.mark.parametrize("notes", [None, "", "   "])
    async def test_cleared_notes_drop_the_embedding(self, notes):
        embeddings = MagicMock()
        embeddings.delete_by_source = AsyncMock()
        await TravelNoteIndex(embeddings).sync("visit_note", 4, "Visit to X", notes)
        embeddings.embed_background.assert_not_called()
        embeddings.delete_by_source.assert_awaited_once_with("visit_note", 4)

    async def test_cleanup_failure_never_breaks_the_write(self):
        embeddings = MagicMock()
        embeddings.delete_by_source = AsyncMock(side_effect=RuntimeError("db down"))
        await TravelNoteIndex(embeddings).remove("leg_note", 1)

    def test_note_text(self):
        assert note_text("Label", " body ") == "Label: body"
