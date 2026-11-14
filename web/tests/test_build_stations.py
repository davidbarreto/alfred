import csv
import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location("build_stations", Path(__file__).resolve().parents[1] / "scripts" / "build_stations.py")
build_stations = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(build_stations)

_FIELDS = ["name", "uic", "country", "time_zone", "is_main_station", "is_airport", "is_suggestable"]


def _write(tmp_path, rows):
    path = tmp_path / "stations.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_FIELDS, delimiter=";")
        writer.writeheader()
        for name, uic, country, suggestable in rows:
            writer.writerow({"name": name, "uic": uic, "country": country, "time_zone": "Europe/Helsinki", "is_main_station": "f",
                             "is_airport": "f", "is_suggestable": suggestable})
    return path


class TestMainStationCode:
    def test_codeless_city_takes_code_of_unsuggested_main_station(self, tmp_path):
        path = _write(tmp_path, [("Helsinki", "", "FI", "t"), ("Helsinki asema", "1000001", "FI", "f")])
        assert build_stations.trainline_rows(path) == [["1000001", "Helsinki", "FI", "Europe/Helsinki", 0, ""]]

    def test_ambiguous_codes_leave_city_codeless(self, tmp_path):
        path = _write(tmp_path, [("Kotka", "", "FI", "t"), ("Kotka asema", "1", "FI", "f"), ("Kotka asema", "2", "FI", "f")])
        assert build_stations.trainline_rows(path)[0][0] == ""

    def test_already_kept_station_is_not_borrowed_from(self, tmp_path):
        path = _write(tmp_path, [("Hamburg", "", "DE", "t"), ("Hamburg Hbf", "8001019", "DE", "t"), ("Hamburg Hbf", "8001020", "DE", "f")])
        rows = {row[1]: row[0] for row in build_stations.trainline_rows(path)}
        assert rows == {"Hamburg": "", "Hamburg Hbf": "8001019"}

    def test_other_country_is_not_matched(self, tmp_path):
        path = _write(tmp_path, [("Helsinki", "", "FI", "t"), ("Helsinki asema", "1000001", "SE", "f")])
        assert build_stations.trainline_rows(path)[0][0] == ""
