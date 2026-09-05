COUNTRY_TO_CODE = {
    "portugal": "PT", "ireland": "IE", "united kingdom": "GB", "uk": "GB", "england": "GB",
    "great britain": "GB", "scotland": "GB", "wales": "GB", "united states": "US", "usa": "US",
    "us": "US", "united states of america": "US", "germany": "DE", "france": "FR", "spain": "ES",
    "italy": "IT", "netherlands": "NL", "the netherlands": "NL", "holland": "NL", "belgium": "BE",
    "switzerland": "CH", "austria": "AT", "poland": "PL", "czech republic": "CZ", "czechia": "CZ",
    "hungary": "HU", "romania": "RO", "bulgaria": "BG", "greece": "GR", "sweden": "SE",
    "norway": "NO", "denmark": "DK", "finland": "FI", "iceland": "IS", "estonia": "EE",
    "latvia": "LV", "lithuania": "LT", "slovakia": "SK", "slovenia": "SI", "croatia": "HR",
    "serbia": "RS", "ukraine": "UA", "russia": "RU", "turkey": "TR", "luxembourg": "LU",
    "malta": "MT", "cyprus": "CY", "liechtenstein": "LI", "canada": "CA", "mexico": "MX", "brazil": "BR",
    "argentina": "AR", "chile": "CL", "colombia": "CO", "peru": "PE", "india": "IN",
    "china": "CN", "japan": "JP", "south korea": "KR", "korea": "KR", "singapore": "SG",
    "indonesia": "ID", "malaysia": "MY", "thailand": "TH", "vietnam": "VN", "philippines": "PH",
    "australia": "AU", "new zealand": "NZ", "south africa": "ZA", "israel": "IL",
    "united arab emirates": "AE", "uae": "AE", "saudi arabia": "SA", "egypt": "EG",
    "morocco": "MA", "nigeria": "NG", "kenya": "KE", "pakistan": "PK", "bangladesh": "BD",
}

CITY_TO_CODE = {
    "dublin": "IE", "cork": "IE", "london": "GB", "manchester": "GB", "edinburgh": "GB",
    "belfast": "GB", "lisbon": "PT", "porto": "PT", "berlin": "DE", "munich": "DE",
    "hamburg": "DE", "frankfurt": "DE", "cologne": "DE", "paris": "FR", "lyon": "FR",
    "madrid": "ES", "barcelona": "ES", "valencia": "ES", "milan": "IT", "rome": "IT",
    "amsterdam": "NL", "rotterdam": "NL", "eindhoven": "NL", "brussels": "BE",
    "zurich": "CH", "geneva": "CH", "basel": "CH", "vienna": "AT", "warsaw": "PL",
    "krakow": "PL", "wroclaw": "PL", "prague": "CZ", "brno": "CZ", "budapest": "HU",
    "bucharest": "RO", "cluj": "RO", "sofia": "BG", "athens": "GR", "stockholm": "SE",
    "gothenburg": "SE", "oslo": "NO", "copenhagen": "DK", "helsinki": "FI",
    "reykjavik": "IS", "tallinn": "EE", "riga": "LV", "vilnius": "LT", "bratislava": "SK",
    "ljubljana": "SI", "zagreb": "HR", "belgrade": "RS", "kyiv": "UA", "istanbul": "TR",
    "luxembourg city": "LU", "nicosia": "CY", "valletta": "MT", "vaduz": "LI",
    "toronto": "CA", "vancouver": "CA", "montreal": "CA",
    "new york": "US", "san francisco": "US", "seattle": "US", "austin": "US",
    "boston": "US", "chicago": "US", "los angeles": "US", "denver": "US",
    "mexico city": "MX", "sao paulo": "BR", "rio de janeiro": "BR", "buenos aires": "AR",
    "bogota": "CO", "bangalore": "IN", "mumbai": "IN", "delhi": "IN", "hyderabad": "IN",
    "shanghai": "CN", "beijing": "CN", "shenzhen": "CN", "tokyo": "JP", "osaka": "JP",
    "seoul": "KR", "jakarta": "ID", "kuala lumpur": "MY", "bangkok": "TH", "hanoi": "VN",
    "manila": "PH", "sydney": "AU", "melbourne": "AU", "auckland": "NZ",
    "cape town": "ZA", "johannesburg": "ZA", "tel aviv": "IL", "dubai": "AE",
    "abu dhabi": "AE", "riyadh": "SA", "cairo": "EG", "casablanca": "MA",
    "lagos": "NG", "nairobi": "KE", "karachi": "PK", "dhaka": "BD",
}

LANGUAGE_TO_COUNTRY_CODE = {"fr": "FR", "ru": "RU", "es": "ES", "it": "IT", "de": "DE", "en": "US"}


def flag_emoji_for_country_code(code: str) -> str:
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code.upper())


def country_flag(location: str | None) -> str:
    if not location:
        return ""
    parts = [p.strip().lower() for p in location.split(",") if p.strip()]
    if not parts:
        return ""
    for part in (parts[-1], parts[0]):
        if part in COUNTRY_TO_CODE:
            return flag_emoji_for_country_code(COUNTRY_TO_CODE[part])
    for part in parts:
        if part in CITY_TO_CODE:
            return flag_emoji_for_country_code(CITY_TO_CODE[part])
    return ""


def language_flag(code: str) -> str:
    country_code = LANGUAGE_TO_COUNTRY_CODE.get(code.lower())
    return flag_emoji_for_country_code(country_code) if country_code else "🌐"
