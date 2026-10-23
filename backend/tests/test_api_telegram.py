from app.api.routes.integrations import telegram
from app.api.routes.integrations.telegram import TelegramCommandEntry


class TestBuildTelegramCommands:
    def test_total_size_within_budget(self):
        commands = telegram._build_telegram_commands()
        total = sum(len(c.command) + len(c.description) for c in commands)
        assert total <= telegram._MAX_TOTAL_CHARS

    def test_count_within_telegram_limit(self):
        assert len(telegram._build_telegram_commands()) <= 100

    def test_only_menu_commands_registered(self):
        commands = {c.command for c in telegram._build_telegram_commands()}
        assert commands <= telegram._MENU_COMMANDS

    def test_every_menu_command_exists(self):
        commands = {c.command for c in telegram._build_telegram_commands()}
        assert commands == telegram._MENU_COMMANDS


class TestFitToBudget:
    def test_short_entries_untouched(self):
        entries = [TelegramCommandEntry(command="a", description="short")]
        assert telegram._fit_to_budget(entries) == entries

    def test_long_descriptions_truncated_uniformly(self, monkeypatch):
        monkeypatch.setattr(telegram, "_MAX_TOTAL_CHARS", 100)
        entries = [TelegramCommandEntry(command="cmd", description="x" * 200) for _ in range(5)]
        fitted = telegram._fit_to_budget(entries)
        assert sum(len(e.command) + len(e.description) for e in fitted) <= 100
        assert all(e.description.endswith("…") for e in fitted)
