import importlib.util
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.assistant.commands.registry import COMMAND_DEFINITIONS
from app.features.location.places.constants import PLACE_KINDS
from app.features.location.places.schemas import PlaceCreate, PlaceFilters, PlaceUpdate
from app.features.location.places.tables import Place


def _migration_101():
    path = Path(__file__).parents[1] / "alembic" / "versions" / "101_location_places.py"
    spec = importlib.util.spec_from_file_location("migration_101", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestPlaceKinds:
    def test_everyday_and_trip_kinds_are_one_list(self):
        assert {"home", "work", "school", "hotel", "museum", "attraction", "activity", "other"} <= set(PLACE_KINDS)

    @pytest.mark.parametrize("model", [PlaceCreate, PlaceUpdate])
    def test_kind_is_trimmed_and_lowercased(self, model):
        assert model(name="Office", kind=" Work ").kind == "work"

    @pytest.mark.parametrize("model", [PlaceCreate, PlaceUpdate])
    def test_kind_outside_the_set_is_refused(self, model):
        with pytest.raises(ValidationError):
            model(name="Office", kind="office")

    def test_filters_refuse_an_unknown_kind(self):
        with pytest.raises(HTTPException) as exc:
            PlaceFilters(kind="office")
        assert exc.value.status_code == 422

    def test_filters_normalize_a_known_kind_and_ignore_a_blank_one(self):
        assert PlaceFilters(kind=" Work").kind == "work"
        assert PlaceFilters(kind=" ").kind is None

    def test_check_constraint_lists_every_kind(self):
        (constraint,) = [c for c in Place.__table__.constraints if c.name == "ck_places_kind"]
        assert str(constraint.sqltext) == "kind IN ({})".format(", ".join(f"'{k}'" for k in PLACE_KINDS))

    def test_migration_uses_the_same_kinds_and_the_union_of_the_old_ones(self):
        module = _migration_101()
        assert module.PLACE_KINDS == PLACE_KINDS
        assert set(module.LOCATION_KINDS) | set(module.TRAVEL_KINDS) == set(PLACE_KINDS)

    def test_location_commands_list_the_kinds_and_point_to_work(self):
        details = COMMAND_DEFINITIONS["location"]["add"]["details"]
        assert ", ".join(PLACE_KINDS) in details and "--kind work" in details
