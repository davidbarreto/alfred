import pytest
from app.assistant.commands.registry import (
    COMMAND_REGISTRY,
    COMMAND_DEFINITIONS,
    _build_registry,
    FLAG_TAGS,
    FLAG_PRIORITY,
    FLAG_DUE,
    FLAG_STATUS,
    TASK_ADD_FLAGS,
    TASK_LIST_FLAGS,
    TASK_UPDATE_FLAGS,
)
from app.assistant.commands.schemas import CommandMetadata


class TestBuildRegistry:
    def test_returns_dict(self):
        registry = _build_registry()
        assert isinstance(registry, dict)

    def test_all_aliases_lowercase(self):
        registry = _build_registry()
        for alias in registry:
            assert alias == alias.lower(), f"Alias '{alias}' should be lowercase"

    def test_alias_maps_to_command_metadata(self):
        registry = _build_registry()
        for alias, meta in registry.items():
            assert isinstance(meta, CommandMetadata)
            assert meta.type
            assert meta.action

    def test_every_definition_alias_is_registered(self):
        registry = _build_registry()
        for cmd_type, actions in COMMAND_DEFINITIONS.items():
            for action_name, config in actions.items():
                for alias in config["aliases"]:
                    assert alias.lower() in registry, (
                        f"Alias '{alias}' for {cmd_type}.{action_name} not in registry"
                    )


class TestCommandRegistryTaskAdd:
    @pytest.mark.parametrize("alias", ["/taskadd", "/t", "/ta", "/task"])
    def test_task_add_aliases(self, alias):
        meta = COMMAND_REGISTRY[alias]
        assert meta.type == "task"
        assert meta.action == "add"
        assert meta.requires_args is True
        assert meta.arg_keys == ["title"]

    def test_task_add_has_deadline_flag(self):
        meta = COMMAND_REGISTRY["/taskadd"]
        assert "-d" in meta.flags or "--due" in meta.flags

    def test_task_add_has_priority_flag(self):
        meta = COMMAND_REGISTRY["/taskadd"]
        assert "-p" in meta.flags or "--priority" in meta.flags

    def test_task_add_has_tags_flag(self):
        meta = COMMAND_REGISTRY["/ta"]
        assert "-t" in meta.flags or "--tags" in meta.flags


class TestCommandRegistryTaskList:
    @pytest.mark.parametrize("alias", ["/tasklist", "/tl", "/list", "/tasks"])
    def test_task_list_aliases(self, alias):
        meta = COMMAND_REGISTRY[alias]
        assert meta.type == "task"
        assert meta.action == "list"
        assert meta.requires_args is False

    def test_task_list_has_status_flag(self):
        meta = COMMAND_REGISTRY["/tasklist"]
        assert "-s" in meta.flags or "--status" in meta.flags

    def test_task_list_has_limit_flag(self):
        meta = COMMAND_REGISTRY["/tasklist"]
        assert "--limit" in meta.flags


class TestCommandRegistryTaskUpdate:
    @pytest.mark.parametrize("alias", ["/tu", "/taskupd"])
    def test_task_update_aliases(self, alias):
        meta = COMMAND_REGISTRY[alias]
        assert meta.type == "task"
        assert meta.action == "update"
        assert meta.requires_args is True
        assert meta.arg_keys == ["id"]


class TestCommandRegistryTaskActions:
    @pytest.mark.parametrize("alias", ["/taskdone", "/td", "/done"])
    def test_task_complete_aliases(self, alias):
        meta = COMMAND_REGISTRY[alias]
        assert meta.type == "task"
        assert meta.action == "complete"
        assert meta.requires_args is True

    @pytest.mark.parametrize("alias", ["/taskdelete", "/trm", "/taskrm"])
    def test_task_delete_aliases(self, alias):
        meta = COMMAND_REGISTRY[alias]
        assert meta.type == "task"
        assert meta.action == "delete"
        assert meta.requires_args is True


class TestCommandRegistryNotes:
    @pytest.mark.parametrize("alias", ["/noteadd", "/n", "/na", "/note"])
    def test_note_add_aliases(self, alias):
        meta = COMMAND_REGISTRY[alias]
        assert meta.type == "note"
        assert meta.action == "add"
        assert meta.requires_args is True

    @pytest.mark.parametrize("alias", ["/notelist", "/nl", "/notes"])
    def test_note_list_aliases(self, alias):
        meta = COMMAND_REGISTRY[alias]
        assert meta.type == "note"
        assert meta.action == "list"

    @pytest.mark.parametrize("alias", ["/notesearch", "/ns", "/notefind"])
    def test_note_search_aliases(self, alias):
        meta = COMMAND_REGISTRY[alias]
        assert meta.type == "note"
        assert meta.action == "search"

    @pytest.mark.parametrize("alias", ["/notedelete", "/nd", "/nrm", "/noterm"])
    def test_note_delete_aliases(self, alias):
        meta = COMMAND_REGISTRY[alias]
        assert meta.type == "note"
        assert meta.action == "delete"


class TestCommandRegistryEvents:
    @pytest.mark.parametrize("alias", ["/eventadd", "/ea", "/event"])
    def test_event_add_aliases(self, alias):
        meta = COMMAND_REGISTRY[alias]
        assert meta.type == "event"
        assert meta.action == "add"

    @pytest.mark.parametrize("alias", ["/eventlist", "/el", "/events"])
    def test_event_list_aliases(self, alias):
        meta = COMMAND_REGISTRY[alias]
        assert meta.type == "event"
        assert meta.action == "list"

    @pytest.mark.parametrize("alias", ["/eventdelete", "/ed", "/edel", "/eventrm", "/cancel"])
    def test_event_delete_aliases(self, alias):
        meta = COMMAND_REGISTRY[alias]
        assert meta.type == "event"
        assert meta.action == "delete"

    @pytest.mark.parametrize("alias", ["/eu", "/eventupd", "/move"])
    def test_event_update_aliases(self, alias):
        meta = COMMAND_REGISTRY[alias]
        assert meta.type == "event"
        assert meta.action == "update"


class TestCommandRegistryHelp:
    @pytest.mark.parametrize("alias", ["/help", "/h", "/?"])
    def test_help_aliases(self, alias):
        meta = COMMAND_REGISTRY[alias]
        assert meta.type == "help"
        assert meta.action == "help"


class TestFlagConstants:
    def test_flag_tags(self):
        assert "-t" in FLAG_TAGS
        assert FLAG_TAGS["-t"] == "tags"

    def test_flag_priority(self):
        assert "-p" in FLAG_PRIORITY
        assert FLAG_PRIORITY["-p"] == "priority"

    def test_task_add_flags_composition(self):
        assert "-d" in TASK_ADD_FLAGS   # deadline
        assert "-p" in TASK_ADD_FLAGS   # priority
        assert "-t" in TASK_ADD_FLAGS   # tags

    def test_task_list_flags_composition(self):
        assert "--limit" in TASK_LIST_FLAGS
        assert "-s" in TASK_LIST_FLAGS  # status

    def test_task_update_flags_composition(self):
        assert "-s" in TASK_UPDATE_FLAGS  # status
        assert "-p" in TASK_UPDATE_FLAGS  # priority
