/*
 * Airport typeahead for the leg form: progressive enhancement for an input pair
 * (city text + IATA code + time zone). Data: /static/js/airports.json, rows of
 * [iata, city, name, country, tz], loaded once on first use.
 *
 * initCityInput({ input, countryInput }) is the same dropdown over distinct cities for place forms:
 * picking a city fills the country name (via Intl.DisplayNames).
 *
 * initTerminalInput({ input, codeInput, zoneInput, mode }) attaches a dropdown to `input`; `mode()` returns the
 * leg's mode. For "flight" it searches the airports, for "train" the stations in /static/js/stations.json
 * (rows of [uic, name, country, tz, main, alias], built by web/scripts/build_stations.py); other modes get no dropdown.
 * Picking a row fills the city or station name, the code (IATA or UIC) and the IANA zone. Typing without
 * picking is untouched, so small airfields, halts and other modes still take free text.
 */
(function () {
  const MAX_RESULTS = 8;
  const MAX_STATION_RESULTS = 12;
  let airportsPromise = null;

  function loadAirports() {
    if (!airportsPromise) {
      airportsPromise = fetch("/static/js/airports.json")
        .then((res) => (res.ok ? res.json() : []))
        .catch(() => []);
    }
    return airportsPromise;
  }

  let stationsPromise = null;

  function loadStations() {
    if (!stationsPromise) {
      stationsPromise = fetch("/static/js/stations.json")
        .then((res) => (res.ok ? res.json() : []))
        .catch(() => []);
    }
    return stationsPromise;
  }

  // Accent- and case-insensitive: "lisboa santa apolonia" finds "Lisboa Santa Apolónia".
  const fold = (text) => text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

  function searchStations(stations, query) {
    const q = fold(query.trim());
    if (q.length < 2) return [];
    const hits = [];
    for (const row of stations) {
      const name = fold(row[1]);
      const alias = fold(row[5]);
      let s = null;
      if (row[0] === q || name === q || alias === q) s = 0;
      else if (name.startsWith(q) || alias.startsWith(q)) s = 1;
      else if (name.includes(q) || alias.includes(q)) s = 2;
      if (s !== null) hits.push([s, row]);
    }
    // Best match first, then main stations, then shorter names; a city has many stops, so show more than for airports.
    hits.sort((a, b) => a[0] - b[0] || b[1][4] - a[1][4] || a[1][1].length - b[1][1].length || a[1][1].localeCompare(b[1][1]));
    return hits.slice(0, MAX_STATION_RESULTS).map((h) => h[1]);
  }

  // Lower score is better; null means no match. Codes rank first, then city, then airport name.
  function score(row, q) {
    const [iata, city, name] = row;
    const code = iata.toLowerCase();
    const cityL = city.toLowerCase();
    if (code === q) return 0;
    if (cityL === q) return 1;
    if (cityL.startsWith(q)) return 2;
    if (code.startsWith(q)) return 3;
    if (name.toLowerCase().includes(q)) return 4;
    if (cityL.includes(q)) return 5;
    return null;
  }

  function search(airports, query) {
    const q = query.trim().toLowerCase();
    if (q.length < 2) return [];
    const hits = [];
    for (const row of airports) {
      const s = score(row, q);
      if (s !== null) hits.push([s, row]);
    }
    hits.sort((a, b) => a[0] - b[0] || a[1][1].localeCompare(b[1][1]));
    return hits.slice(0, MAX_RESULTS).map((h) => h[1]);
  }

  // Shared dropdown: `find(query)` returns rows, `label(row)` -> [main, sub], `pick(row)` fills the form.
  function attachDropdown({ input, isActive, find, label, pick }) {
    const wrap = document.createElement("div");
    wrap.className = "relative";
    input.before(wrap);
    wrap.append(input);
    const panel = document.createElement("div");
    panel.className = "hidden absolute left-0 right-0 top-full mt-1 z-20 bg-white border border-gray-100 rounded-lg shadow-lg max-h-64 overflow-y-auto";
    wrap.append(panel);
    input.autocomplete = "off";

    let results = [];
    let active = -1;

    function close() {
      panel.classList.add("hidden");
      active = -1;
    }

    function choose(row) {
      pick(row);
      close();
    }

    function highlight() {
      [...panel.children].forEach((el, i) => el.classList.toggle("bg-gray-100", i === active));
    }

    function render() {
      panel.replaceChildren();
      results.forEach((row) => {
        const [mainText, subText] = label(row);
        const item = document.createElement("div");
        item.className = "px-3 py-1.5 text-sm cursor-pointer hover:bg-gray-100";
        const main = document.createElement("span");
        main.textContent = mainText;
        const sub = document.createElement("span");
        sub.className = "ml-2 text-xs text-gray-400";
        sub.textContent = subText;
        item.append(main, sub);
        // mousedown, not click: it fires before the input's blur closes the panel.
        item.addEventListener("mousedown", (event) => { event.preventDefault(); choose(row); });
        panel.append(item);
      });
      panel.classList.toggle("hidden", results.length === 0);
      active = -1;
    }

    input.addEventListener("input", async () => {
      if (!isActive()) { close(); return; }
      results = await find(input.value);
      render();
    });
    input.addEventListener("keydown", (event) => {
      if (panel.classList.contains("hidden")) return;
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const step = event.key === "ArrowDown" ? 1 : -1;
        active = (active + step + results.length) % results.length;
        highlight();
      } else if (event.key === "Enter" && active >= 0) {
        event.preventDefault();
        choose(results[active]);
      } else if (event.key === "Escape") {
        event.stopPropagation();
        close();
      }
    });
    input.addEventListener("blur", close);
  }

  function initTerminalInput({ input, codeInput, zoneInput, mode }) {
    attachDropdown({
      input,
      isActive: () => mode() === "flight" || mode() === "train",
      find: async (query) => (mode() === "train" ? searchStations(await loadStations(), query) : search(await loadAirports(), query)),
      // airports: [iata, city, name, country, tz]; stations: [uic, name, country, tz]
      label: (row) => (mode() === "train" ? [row[5] || row[1], row[5] ? `${row[2]} · ${row[1]}` : row[2]] : [`${row[1]} (${row[0]})`, `${row[2]} · ${row[3]}`]),
      pick: (row) => {
        // A station is saved under its English name when it has one, like airports and the stay city picker, so a
        // leg's end still matches the city of the stay.
        input.value = mode() === "train" ? row[5] || row[1] : row[1];
        codeInput.value = row[0];
        zoneInput.value = mode() === "train" ? row[3] : row[4];
      },
    });
  }

  let regionNames = null;
  function countryName(code) {
    try {
      regionNames = regionNames || new Intl.DisplayNames(["en"], { type: "region" });
      return regionNames.of(code) || code;
    } catch (e) {
      return code;
    }
  }

  // One row per city + country, derived from the airports list: [city, country name].
  let citiesPromise = null;
  function loadCities() {
    if (!citiesPromise) {
      citiesPromise = loadAirports().then((airports) => {
        const seen = new Set();
        const cities = [];
        for (const [, city, , country, tz] of airports) {
          const key = `${city}|${country}`;
          if (!city || seen.has(key)) continue;
          seen.add(key);
          cities.push([city, countryName(country), tz]);
        }
        return cities;
      });
    }
    return citiesPromise;
  }

  function searchCities(cities, query) {
    const q = query.trim().toLowerCase();
    if (q.length < 2) return [];
    const hits = [];
    for (const row of cities) {
      const name = row[0].toLowerCase();
      if (name === q) hits.push([0, row]);
      else if (name.startsWith(q)) hits.push([1, row]);
      else if (name.includes(q)) hits.push([2, row]);
    }
    hits.sort((a, b) => a[0] - b[0] || a[1][0].localeCompare(b[1][0]));
    return hits.slice(0, MAX_RESULTS).map((h) => h[1]);
  }

  // City typeahead for place forms: picking a city also fills the country and, if given, the time zone (editable afterwards).
  function initCityInput({ input, countryInput, zoneInput }) {
    attachDropdown({
      input,
      isActive: () => true,
      find: async (query) => searchCities(await loadCities(), query),
      label: ([city, country]) => [city, country],
      pick: ([city, country, tz]) => {
        input.value = city;
        countryInput.value = country;
        if (zoneInput && tz) zoneInput.value = tz;
      },
    });
  }

  window.initTerminalInput = initTerminalInput;
  window.initCityInput = initCityInput;
  window.searchAirports = search;
  window.searchStations = searchStations;
  window.searchCities = searchCities;
})();
