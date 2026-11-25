import pytest

from app.features.organizer.locations.coordinates import coordinates_from_maps_url, parse_coordinates


class TestParseCoordinates:
    @pytest.mark.parametrize("text", ["41.1579, -8.6291", "41.1579,-8.6291", " 41.1579 -8.6291 ", "41.1579; -8.6291"])
    def test_accepts_what_maps_copies(self, text):
        assert parse_coordinates(text) == (41.1579, -8.6291)

    def test_rounds_to_six_decimals(self):
        assert parse_coordinates("41.15791234, -8.62914321") == (41.157912, -8.629143)

    @pytest.mark.parametrize("text", ["", "41.1579", "north, west", "91, 0", "0, 181", "41.1, -8.6, 3"])
    def test_refuses_anything_else(self, text):
        with pytest.raises(ValueError):
            parse_coordinates(text)


class TestFromMapsUrl:
    def test_place_pin_wins_over_map_centre(self):
        url = "https://www.google.com/maps/place/Somewhere/@41.15,-8.62,17z/data=!3m1!4b1!4m6!3m5!1s0x0:0x0!8m2!3d41.1579!4d-8.6291"
        assert coordinates_from_maps_url(url) == (41.1579, -8.6291)

    def test_map_centre(self):
        assert coordinates_from_maps_url("https://www.google.com/maps/@38.7223,-9.1393,15z") == (38.7223, -9.1393)

    def test_query_parameter(self):
        assert coordinates_from_maps_url("https://maps.google.com/?q=38.7223,-9.1393") == (38.7223, -9.1393)

    @pytest.mark.parametrize("url", [None, "", "https://maps.app.goo.gl/AbCdEf123", "https://www.google.com/maps/@95,10,15z"])
    def test_none_when_the_link_has_no_coordinates(self, url):
        assert coordinates_from_maps_url(url) is None
