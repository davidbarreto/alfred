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


class TestEuEeaCoverage:
    _EU_EEA_CAPITALS = {
        "vienna": "🇦🇹", "brussels": "🇧🇪", "sofia": "🇧🇬", "zagreb": "🇭🇷", "nicosia": "🇨🇾",
        "prague": "🇨🇿", "copenhagen": "🇩🇰", "tallinn": "🇪🇪", "helsinki": "🇫🇮", "paris": "🇫🇷",
        "berlin": "🇩🇪", "athens": "🇬🇷", "budapest": "🇭🇺", "dublin": "🇮🇪", "rome": "🇮🇹",
        "riga": "🇱🇻", "vilnius": "🇱🇹", "luxembourg city": "🇱🇺", "valletta": "🇲🇹",
        "amsterdam": "🇳🇱", "warsaw": "🇵🇱", "lisbon": "🇵🇹", "bucharest": "🇷🇴",
        "bratislava": "🇸🇰", "ljubljana": "🇸🇮", "madrid": "🇪🇸", "stockholm": "🇸🇪",
        "reykjavik": "🇮🇸", "vaduz": "🇱🇮", "oslo": "🇳🇴",
    }

    def test_all_eu_eea_capitals_resolve(self):
        for capital, flag in self._EU_EEA_CAPITALS.items():
            assert country_flag(capital) == flag, f"{capital} did not resolve to {flag}"

    _EU_EEA_COUNTRIES = {
        "austria": "🇦🇹", "belgium": "🇧🇪", "bulgaria": "🇧🇬", "croatia": "🇭🇷", "cyprus": "🇨🇾",
        "czechia": "🇨🇿", "denmark": "🇩🇰", "estonia": "🇪🇪", "finland": "🇫🇮", "france": "🇫🇷",
        "germany": "🇩🇪", "greece": "🇬🇷", "hungary": "🇭🇺", "ireland": "🇮🇪", "italy": "🇮🇹",
        "latvia": "🇱🇻", "lithuania": "🇱🇹", "luxembourg": "🇱🇺", "malta": "🇲🇹",
        "netherlands": "🇳🇱", "poland": "🇵🇱", "portugal": "🇵🇹", "romania": "🇷🇴",
        "slovakia": "🇸🇰", "slovenia": "🇸🇮", "spain": "🇪🇸", "sweden": "🇸🇪",
        "iceland": "🇮🇸", "liechtenstein": "🇱🇮", "norway": "🇳🇴",
    }

    def test_all_eu_eea_countries_resolve(self):
        for country, flag in self._EU_EEA_COUNTRIES.items():
            assert country_flag(country) == flag, f"{country} did not resolve to {flag}"


class TestLanguageFlag:
    def test_known_language_code(self):
        assert language_flag("fr") == "🇫🇷"

    def test_case_insensitive(self):
        assert language_flag("FR") == "🇫🇷"

    def test_unknown_code_falls_back_to_globe(self):
        assert language_flag("xx") == "🌐"
