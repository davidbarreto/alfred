from app.templates_config import _country_flag


class TestCountryFlag:
    def test_city_comma_country_format(self):
        assert _country_flag("Dublin, Ireland") == "🇮🇪"

    def test_country_only(self):
        assert _country_flag("Ireland") == "🇮🇪"

    def test_city_only_known_city(self):
        assert _country_flag("Dublin") == "🇮🇪"

    def test_case_insensitive(self):
        assert _country_flag("dublin, ireland") == "🇮🇪"

    def test_unknown_location_returns_empty(self):
        assert _country_flag("Somewhere, Nowhereland") == ""

    def test_none_returns_empty(self):
        assert _country_flag(None) == ""

    def test_blank_returns_empty(self):
        assert _country_flag("") == ""

    def test_remote_only_returns_empty(self):
        assert _country_flag("Remote") == ""
