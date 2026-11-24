import importlib.util
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.assistant.commands.registry import COMMAND_DEFINITIONS
from app.features.organizer.locations.constants import LOCATION_KINDS
from app.features.organizer.locations.schemas import LocationCreate, LocationFilters, LocationUpdate
from app.features.organizer.locations.tables import Location


class TestLocationKinds:
    def test_work_and_home_are_kinds(self):
        assert {"home", "work", "school", "other"} <= set(LOCATION_KINDS)

    @pytest.mark.parametrize("model", [LocationCreate, LocationUpdate])
    def test_kind_is_trimmed_and_lowercased(self, model):
        assert model(name="Office", kind=" Work ").kind == "work"

    @pytest.mark.parametrize("model", [LocationCreate, LocationUpdate])
    def test_kind_outside_the_set_is_refused(self, model):
        with pytest.raises(ValidationError):
            model(name="Office", kind="office")

    def test_filters_refuse_an_unknown_kind(self):
        with pytest.raises(HTTPException) as exc:
            LocationFilters(kind="office")
        assert exc.value.status_code == 422

    def test_filters_normalize_a_known_kind_and_ignore_a_blank_one(self):
        assert LocationFilters(kind=" Work").kind == "work"
        assert LocationFilters(kind=" ").kind is None

    def test_check_constraint_lists_every_kind(self):
        (constraint,) = [c for c in Location.__table__.constraints if c.name == "ck_locations_kind"]
        assert str(constraint.sqltext) == "kind IN ({})".format(", ".join(f"'{k}'" for k in LOCATION_KINDS))

    def test_migration_uses_the_same_kinds(self):
        path = Path(__file__).parents[1] / "alembic" / "versions" / "098_location_kinds.py"
        spec = importlib.util.spec_from_file_location("migration_098", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module._KINDS == LOCATION_KINDS

    def test_location_commands_list_the_kinds_and_point_to_work(self):
        details = COMMAND_DEFINITIONS["location"]["add"]["details"]
        assert ", ".join(LOCATION_KINDS) in details and "--kind work" in details
