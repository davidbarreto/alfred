import pytest

from app.features.metrics.entries.durations import format_duration, parse_ago


class TestParseAgo:
    @pytest.mark.parametrize(
        "text,seconds",
        [("5m", 300), ("1h30m", 5400), ("90s", 90), ("2h", 7200), ("10", 600), ("1h 5m", 3900), ("1H30M", 5400)],
    )
    def test_parses(self, text, seconds):
        assert parse_ago(text) == seconds

    @pytest.mark.parametrize("text", ["", "abc", "5x", "m5", "-5m", "1.5h"])
    def test_rejects_garbage(self, text):
        with pytest.raises(ValueError):
            parse_ago(text)


class TestFormatDuration:
    @pytest.mark.parametrize(
        "seconds,text",
        [(45, "45 s"), (60, "1 min"), (2040, "34 min"), (3600, "1 h"), (3900, "1 h 05 min"), (7500, "2 h 05 min")],
    )
    def test_formats(self, seconds, text):
        assert format_duration(seconds) == text
