from app.shared.flags import country_flag, language_flag


class TestCountryFlag:
    def test_city_comma_country_format(self):
        assert country_flag("Dublin, Ireland") == "🇮🇪"

    def test_country_only(self):
        assert country_flag("Ireland") == "🇮🇪"

    def test_city_only_known_city(self):
        assert country_flag("Dublin") == "🇮🇪"

    def test_case_insensitive(self):
        assert country_flag("dublin, ireland") == "🇮🇪"

    def test_unknown_location_returns_empty(self):
        assert country_flag("Somewhere, Nowhereland") == ""

    def test_none_returns_empty(self):
        assert country_flag(None) == ""

    def test_blank_returns_empty(self):
        assert country_flag("") == ""

    def test_remote_only_returns_empty(self):
        assert country_flag("Remote") == ""


class TestLanguageFlag:
    def test_known_language_code(self):
        assert language_flag("fr") == "🇫🇷"

    def test_case_insensitive(self):
        assert language_flag("FR") == "🇫🇷"

    def test_unknown_code_falls_back_to_globe(self):
        assert language_flag("xx") == "🌐"
