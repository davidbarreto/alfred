/*
 * Airport typeahead for the leg form: progressive enhancement for an input pair
 * (city text + IATA code + time zone). Data: /static/js/airports.json, rows of
 * [iata, city, name, country, tz], loaded once on first use.
 *
 * initAirportInput({ input, codeInput, zoneInput, isActive }) attaches a dropdown to `input`.
 * Picking a row fills the city, the IATA code and the IANA zone. Typing without picking is
 * untouched, so small airfields and non-flight legs still take free text.
 */
(function () {
  const MAX_RESULTS = 8;
  let airportsPromise = null;

  function loadAirports() {
    if (!airportsPromise) {
      airportsPromise = fetch("/static/js/airports.json")
        .then((res) => (res.ok ? res.json() : []))
        .catch(() => []);
    }
    return airportsPromise;
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

  function initAirportInput({ input, codeInput, zoneInput, isActive }) {
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

    function highlight() {
      [...panel.children].forEach((el, i) => el.classList.toggle("bg-gray-100", i === active));
    }

    function pick(row) {
      const [iata, city, , , tz] = row;
      input.value = city;
      codeInput.value = iata;
      zoneInput.value = tz;
      close();
    }

    function render() {
      panel.replaceChildren();
      results.forEach((row) => {
        const [iata, city, name, country] = row;
        const item = document.createElement("div");
        item.className = "px-3 py-1.5 text-sm cursor-pointer hover:bg-gray-100";
        const main = document.createElement("span");
        main.textContent = `${city} (${iata})`;
        const sub = document.createElement("span");
        sub.className = "ml-2 text-xs text-gray-400";
        sub.textContent = `${name} · ${country}`;
        item.append(main, sub);
        // mousedown, not click: it fires before the input's blur closes the panel.
        item.addEventListener("mousedown", (event) => { event.preventDefault(); pick(row); });
        panel.append(item);
      });
      panel.classList.toggle("hidden", results.length === 0);
      active = -1;
    }

    input.addEventListener("input", async () => {
      if (!isActive()) { close(); return; }
      const airports = await loadAirports();
      results = search(airports, input.value);
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
        pick(results[active]);
      } else if (event.key === "Escape") {
        event.stopPropagation();
        close();
      }
    });
    input.addEventListener("blur", close);
  }

  window.initAirportInput = initAirportInput;
  window.searchAirports = search;
})();
