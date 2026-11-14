"""Build web/app/static/js/stations.json, the train-station list behind the leg form's picker.

Source: the open trainline-eu/stations dataset (ODbL, https://github.com/trainline-eu/stations, also mirrored on
Kaggle as "Train stations in Europe"): a semicolon-separated stations.csv.

    curl -L -o /tmp/stations.csv https://raw.githubusercontent.com/trainline-eu/stations/master/stations.csv
    python web/scripts/build_stations.py /tmp/stations.csv

Rows are [code, name, country (ISO-2), time zone, main, alias]; `main` is 1 for the dataset's main stations (they rank first in the picker), `alias` is the name with its city in English when that differs ("Wien Hbf" -> "Vienna Hbf"), else empty; the code is the UIC code, or empty when the dataset has none (the
leg then stores only the name, and the Maps link is built from the name anyway). Kept: suggestable stations, one
row per country and name. Stations flagged as airports are kept only when they have a UIC code (the rail stops at
airports such as Schiphol or Frankfurt Flughafen); the other airport entries are the airports themselves. Swiss
stops without a UIC code are dropped unless they are main stations: the dataset lists thousands of bus stops there.

To cover another region, add a function that yields rows in the same shape (for example from Amtrak's GTFS
stops.txt for the US) and extend `main()` to merge it; the browser code needs no change.
"""
import csv
import json
import sys
from pathlib import Path

# Local city name -> English name, for the cities whose English name differs. A station whose name starts with the
# local name (followed by a non-letter or nothing) gets an English alias, so "Vienna" finds "Wien Hbf".
EXONYMS = {
    "Lisboa": "Lisbon", "Wien": "Vienna", "Köln": "Cologne", "München": "Munich", "Praha": "Prague",
    "Roma": "Rome", "Firenze": "Florence", "Venezia": "Venice", "Napoli": "Naples", "Torino": "Turin",
    "Genova": "Genoa", "Milano": "Milan", "Padova": "Padua", "Genève": "Geneva", "Zürich": "Zurich",
    "Bruxelles": "Brussels", "Brussel": "Brussels", "Antwerpen": "Antwerp", "Gent": "Ghent", "Liège": "Liege",
    "Warszawa": "Warsaw", "Kraków": "Krakow", "Wrocław": "Wroclaw", "Gdańsk": "Gdansk", "Poznań": "Poznan",
    "København": "Copenhagen", "Göteborg": "Gothenburg", "Moskva": "Moscow", "Beograd": "Belgrade",
    "București": "Bucharest", "Bucureşti": "Bucharest", "Wiener Neustadt": "Vienna Neustadt", "Nürnberg": "Nuremberg",
    "Hannover": "Hanover", "Sevilla": "Seville", "Donostia": "San Sebastian", "A Coruña": "La Coruna",
    "Basel": "Basle", "Bern": "Berne", "Luzern": "Lucerne", "Athína": "Athens", "Kyiv": "Kiev",
    "Wrocław Główny": "Wroclaw Glowny", "Lyon": "Lyons", "Bordeaux": "Bordeaux", "Marseille": "Marseilles",
    "Praga": "Prague", "Porto": "Oporto",
}
EXONYMS = {local: english for local, english in EXONYMS.items() if local != english}

OUTPUT = Path(__file__).resolve().parents[1] / "app" / "static" / "js" / "stations.json"


def _keep(row: dict[str, str]) -> bool:
    if row["is_suggestable"] != "t" or not row["name"].strip() or not row["time_zone"]:
        return False
    if row["uic"]:
        return True
    if row["is_airport"] == "t":
        return False
    return row["country"] != "CH" or row["is_main_station"] == "t"


def _alias(name: str) -> str:
    """The name with its leading city in English, or an empty string when there is none."""
    for local, english in EXONYMS.items():
        if name == local or (name.startswith(local) and not name[len(local)].isalpha()):
            return english + name[len(local):]
    return ""


def trainline_rows(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        by_name: dict[tuple[str, str], list[str]] = {}
        for r in csv.DictReader(handle, delimiter=";"):
            if not _keep(r):
                continue
            key = (r["country"], r["name"].strip())
            # A duplicate name keeps the entry that has a code.
            if key not in by_name or (r["uic"] and not by_name[key][0]):
                by_name[key] = [r["uic"], r["name"].strip(), r["country"], r["time_zone"], int(r["is_main_station"] == "t"), _alias(r["name"].strip())]
    return list(by_name.values())


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        raise SystemExit(__doc__)
    rows = sorted(trainline_rows(Path(argv[1])), key=lambda r: (r[2], r[1]))
    OUTPUT.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(rows)} stations, {OUTPUT.stat().st_size / 1024:.0f} KB -> {OUTPUT}")


if __name__ == "__main__":
    main(sys.argv)
