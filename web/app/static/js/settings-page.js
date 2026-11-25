/*
 * /settings in the browser.
 *
 * Search: every row is on the page, so the filter runs here. It matches the label, key and description (data-search),
 * hides sections with no match, updates the counts in the section nav and keeps the query in ?q=.
 * Tuning rows (data-advanced) show only with "Show tuning" on (remembered in localStorage), or when a search matches.
 *
 * Editing: each row holds the value the page loaded (data-value, JSON). readValue() turns the control back into the
 * value its API expects; a row whose value differs from the loaded one is "changed". One Save for the page: the bar
 * at the bottom counts the changes, Review lists them (key: old → new, with any confirm note), and Save posts only the
 * changed fields to /settings/save, which answers per namespace. Saved sections take the new values; a failed one
 * shows the error at the top of its card and keeps its rows changed.
 */
(function () {
  // Read-only and link rows are never edited or sent.
  const rows = [...document.querySelectorAll("[data-setting-row]")]
    .filter((row) => !["readonly", "link"].includes(row.dataset.widget));
  const sections = [...document.querySelectorAll("[data-section]")];
  const WINDOW = /^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$/;

  // ── Search ──────────────────────────────────────────────────────────────

  const search = document.getElementById("settings-search");
  const noMatch = document.getElementById("settings-no-match");
  const tuningSwitch = document.getElementById("show-tuning");
  const TUNING_KEY = "settings.showTuning";
  try { tuningSwitch.checked = localStorage.getItem(TUNING_KEY) === "1"; } catch (e) { /* storage blocked */ }

  function applySearch(query) {
    const q = query.trim().toLowerCase();
    const showTuning = tuningSwitch.checked;
    let shownSections = 0;
    sections.forEach((section) => {
      let shown = 0;
      section.querySelectorAll("[data-setting-row], [data-link-row]").forEach((row) => {
        const match = q ? row.dataset.search.includes(q) : (showTuning || !row.hasAttribute("data-advanced"));
        row.classList.toggle("hidden", !match);
        if (match && row.hasAttribute("data-setting-row")) shown += 1;
      });
      section.querySelectorAll("[data-group]").forEach((group) => {
        group.classList.toggle("hidden", !group.querySelector("[data-setting-row]:not(.hidden)"));
      });
      // A section shows while it has a visible row; without a search a non-tuning section always shows (its load
      // error, if any, stays readable).
      const visible = Boolean(section.querySelector("[data-setting-row]:not(.hidden), [data-link-row]:not(.hidden)"))
        || (!q && !section.hasAttribute("data-advanced"));
      section.classList.toggle("hidden", !visible);
      if (visible) shownSections += 1;
      document.querySelectorAll(`[data-nav="${section.dataset.section}"]`).forEach((link) => {
        link.classList.toggle("hidden", !visible);
        link.querySelector("[data-nav-count]").textContent = String(shown);
      });
    });
    document.querySelector("[data-stored]")?.classList.toggle("hidden", Boolean(q));
    noMatch.classList.toggle("hidden", shownSections > 0);
    const url = new URL(window.location.href);
    if (q) url.searchParams.set("q", query.trim());
    else url.searchParams.delete("q");
    window.history.replaceState(null, "", url);
  }

  if (search) {
    search.value = new URL(window.location.href).searchParams.get("q") || "";
    search.addEventListener("input", () => applySearch(search.value));
    tuningSwitch.addEventListener("change", () => {
      try { localStorage.setItem(TUNING_KEY, tuningSwitch.checked ? "1" : "0"); } catch (e) { /* storage blocked */ }
      applySearch(search.value);
    });
    applySearch(search.value);
  }

  // ── Values ──────────────────────────────────────────────────────────────

  const state = new Map(); // row -> { loaded, json (current value of a json row), picker }

  const parse = (raw) => (raw === undefined ? undefined : JSON.parse(raw));
  const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
  const control = (row) => row.querySelector("[data-control]");

  /** The control's value as the API expects it, or { error } when it cannot be sent. */
  function readValue(row) {
    const { widget, nullable } = row.dataset;
    const input = control(row);
    switch (widget) {
      case "number": {
        if (input.value === "") return nullable === "true" ? { value: null } : { error: "Enter a number." };
        if (!input.checkValidity()) return { error: input.validationMessage || "Out of range." };
        return { value: Number(input.value) };
      }
      case "toggle":
        return { value: input.checked };
      case "time":
        return { value: input.value || null };
      case "text":
      case "longtext": {
        const text = input.value.trim();
        if (!text && nullable !== "true") return { error: "This cannot be empty." };
        return { value: text || null };
      }
      case "weekdays":
        return { value: [...row.querySelectorAll("[data-day]:checked")].map((box) => box.dataset.day) };
      case "windows":
        return { value: [...row.querySelectorAll("[data-chip]")].map((chip) => chip.dataset.chip) };
      case "city": {
        const id = row.querySelector("[data-city-id]").value;
        return { value: id ? Number(id) : null };
      }
      case "json":
        return { value: state.get(row).json };
      case "place": {
        // "location:5", "city:3" or "" (Home): the row's value covers both fields.
        const [kind, id] = input.value.split(":");
        return { value: { location_id: kind === "location" ? Number(id) : null, city_id: kind === "city" ? Number(id) : null } };
      }
      default:
        return { value: undefined };
    }
  }

  function chip(window) {
    const el = document.createElement("span");
    el.className = "badge badge-sm gap-1 bg-[#E6F1FB] text-[#0C447C] border-0";
    el.dataset.chip = window;
    el.textContent = window + " ";
    const remove = document.createElement("button");
    remove.type = "button";
    remove.dataset.chipRemove = "";
    remove.setAttribute("aria-label", `Remove ${window}`);
    remove.innerHTML = '<i class="ti ti-x text-[10px]"></i>';
    el.appendChild(remove);
    return el;
  }

  function summaryLines(value) {
    return Object.entries(value || {}).map(([entry, items]) => `${entry}: ${Array.isArray(items) ? items.join(", ") : items}`);
  }

  /** Put a value (as the API returns it) back into the row's control. `extra` carries the city object. */
  function setValue(row, value, extra) {
    const input = control(row);
    switch (row.dataset.widget) {
      case "number": input.value = value ?? ""; break;
      case "toggle": input.checked = Boolean(value); break;
      case "time": input.value = value || ""; break;
      case "text": input.value = value || ""; break;
      case "longtext": input.value = value || ""; updateCounter(row); break;
      case "weekdays":
        row.querySelectorAll("[data-day]").forEach((box) => { box.checked = (value || []).includes(box.dataset.day); });
        break;
      case "windows": {
        const chips = row.querySelector("[data-chips]");
        chips.replaceChildren(...(value || []).map(chip));
        break;
      }
      case "city": state.get(row).picker?.reset(extra ?? null); break;
      case "place":
        input.value = value?.location_id != null ? `location:${value.location_id}` : value?.city_id != null ? `city:${value.city_id}` : "";
        break;
      case "json": {
        state.get(row).json = value;
        row.querySelector("[data-json-summary]").replaceChildren(...summaryLines(value).map((line) => {
          const li = document.createElement("li");
          li.textContent = line;
          return li;
        }));
        break;
      }
      default: break;
    }
  }

  function updateCounter(row) {
    const counter = row.querySelector("[data-counter]");
    if (counter) counter.textContent = String(control(row).value.length);
  }

  // ── Change tracking ─────────────────────────────────────────────────────

  const bar = document.getElementById("save-bar");

  function refresh(row) {
    const { value, error } = readValue(row);
    const changed = error !== undefined || !same(value, state.get(row).loaded);
    row.toggleAttribute("data-changed", changed);
    row.querySelector("[data-row-error]").textContent = changed && error ? error : "";
    const badge = row.querySelector("[data-modified]");
    if (badge && error === undefined) badge.classList.toggle("hidden", same(value, parse(row.dataset.default)));
    updateBar();
  }

  function changedRows() {
    return rows.filter((row) => row.hasAttribute("data-changed"));
  }

  function updateBar() {
    const count = changedRows().length;
    bar.classList.toggle("hidden", count === 0);
    document.querySelector("main")?.classList.toggle("pb-16", count > 0);
    document.getElementById("change-count").textContent = String(count);
    document.getElementById("change-noun").textContent = count === 1 ? "change" : "changes";
    document.getElementById("save-bar-error").textContent = "";
  }

  rows.forEach((row) => {
    state.set(row, { loaded: parse(row.dataset.value), json: parse(row.dataset.value), picker: null });
    row.addEventListener("input", () => { updateCounter(row); refresh(row); });
    row.addEventListener("change", () => refresh(row));
  });

  // Windows: chips added after an HH:MM-HH:MM check, removed with their x.
  rows.filter((row) => row.dataset.widget === "windows").forEach((row) => {
    const input = row.querySelector("[data-chip-input]");
    const error = row.querySelector("[data-chip-error]");
    function add() {
      const window = input.value.trim();
      const existing = [...row.querySelectorAll("[data-chip]")].map((c) => c.dataset.chip);
      if (!WINDOW.test(window) || window.split("-")[1] <= window.split("-")[0]) {
        error.textContent = "Use HH:MM-HH:MM with the end after the start.";
        return;
      }
      error.textContent = "";
      input.value = "";
      if (!existing.includes(window)) row.querySelector("[data-chips]").appendChild(chip(window));
      refresh(row);
    }
    row.querySelector("[data-chip-add]").addEventListener("click", add);
    input.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); add(); } });
    // The chip input is not the value: typing in it alone changes nothing.
    input.addEventListener("input", (event) => event.stopPropagation());
    row.querySelector("[data-chips]").addEventListener("click", (event) => {
      const remove = event.target.closest("[data-chip-remove]");
      if (!remove) return;
      remove.closest("[data-chip]").remove();
      refresh(row);
    });
  });

  // City: the travel page's picker; picking or clearing marks the row.
  const cityDialog = document.getElementById("city-dialog");
  async function send(method, url, body) {
    const res = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
    return { ok: res.ok, status: res.status, data: await res.json().catch(() => ({})) };
  }
  rows.filter((row) => row.dataset.widget === "city").forEach((row) => {
    const text = row.querySelector("[data-city-text]");
    const picker = window.initCityPicker({
      input: text, idInput: row.querySelector("[data-city-id]"), clearButton: row.querySelector("[data-city-clear]"),
      terminalInput: text, newCity: window.initNewCityDialog({ dialog: cityDialog, send }),
      onChange: () => refresh(row),
    });
    state.get(row).picker = picker;
    picker.reset(parse(row.querySelector("[data-city]").textContent));
  });
  // The typed filter text is not the value either.
  rows.filter((row) => row.dataset.widget === "city").forEach((row) => {
    row.querySelector("[data-city-text]").addEventListener("input", (event) => event.stopPropagation());
  });

  // ── JSON editor ─────────────────────────────────────────────────────────

  const jsonDialog = document.getElementById("json-dialog");
  const jsonText = document.getElementById("json-text");
  const jsonError = document.getElementById("json-error");
  let jsonRow = null;

  function checkShape(value, options) {
    if (value === null || typeof value !== "object" || Array.isArray(value)) return "Expected an object: { \"name\": [\"1h\", \"0\"] }.";
    for (const [entry, items] of Object.entries(value)) {
      if (options && !options.includes(entry)) return `Unknown entry "${entry}". Expected one of: ${options.join(", ")}.`;
      if (!Array.isArray(items) || items.length === 0 || !items.every((item) => typeof item === "string")) {
        return `"${entry}" must be a non-empty list of strings.`;
      }
    }
    return null;
  }

  document.querySelectorAll("[data-json-edit]").forEach((button) => {
    button.addEventListener("click", () => {
      jsonRow = button.closest("[data-setting-row]");
      document.getElementById("json-title").textContent = jsonRow.dataset.label;
      jsonText.value = JSON.stringify(state.get(jsonRow).json, null, 2);
      jsonError.textContent = "";
      jsonDialog.showModal();
    });
  });
  document.getElementById("json-apply").addEventListener("click", () => {
    let value;
    try {
      value = JSON.parse(jsonText.value);
    } catch (exc) {
      jsonError.textContent = `Not valid JSON: ${exc.message}`;
      return;
    }
    const problem = checkShape(value, parse(jsonRow.dataset.options));
    if (problem) {
      jsonError.textContent = problem;
      return;
    }
    setValue(jsonRow, value);
    jsonDialog.close();
    refresh(jsonRow);
  });
  document.querySelectorAll("dialog [data-close]").forEach((button) => {
    button.addEventListener("click", () => button.closest("dialog").close());
  });

  // ── Review and save ─────────────────────────────────────────────────────

  function display(row, value) {
    if (value === null || value === undefined || value === "") return "not set";
    if (typeof value === "boolean") return value ? "on" : "off";
    if (Array.isArray(value)) return value.length ? value.join(", ") : "none";
    return String(value);
  }

  /** The changed entries of a json row: { entry: newValue }. */
  function changedEntries(row) {
    const { loaded, json } = state.get(row);
    return Object.fromEntries(Object.entries(json || {}).filter(([entry, items]) => !same(items, (loaded || {})[entry])));
  }

  function collect() {
    const changes = {};
    const problems = [];
    changedRows().forEach((row) => {
      const { value, error } = readValue(row);
      if (error) {
        problems.push(row);
        return;
      }
      const sent = row.dataset.widget === "json" ? changedEntries(row) : value;
      if (row.dataset.widget === "json" && Object.keys(sent).length === 0) return;
      (changes[row.dataset.namespace] ||= {})[row.dataset.field] = sent;
    });
    return { changes, problems };
  }

  function reviewLine(row) {
    const div = document.createElement("div");
    div.className = "text-xs";
    const key = document.createElement("p");
    key.className = "font-mono text-gray-600 break-all";
    key.textContent = row.dataset.key;
    div.appendChild(key);
    const lines = [];
    if (row.dataset.widget === "json") {
      const loaded = state.get(row).loaded || {};
      Object.entries(changedEntries(row)).forEach(([entry, items]) => {
        lines.push(`${entry}: ${display(row, loaded[entry])} → ${display(row, items)}`);
      });
    } else if (row.dataset.widget === "place") {
      const select = control(row);
      const labelOf = (v) => {
        const option = [...select.options].find((o) => o.value === (v?.location_id != null ? `location:${v.location_id}` : v?.city_id != null ? `city:${v.city_id}` : ""));
        return option ? option.textContent.trim() : "not set";
      };
      lines.push(`${labelOf(state.get(row).loaded)} → ${labelOf(readValue(row).value)}`);
    } else if (row.dataset.widget === "city") {
      const loaded = parse(row.querySelector("[data-city]").textContent);
      const now = row.querySelector("[data-city-text]").value;
      lines.push(`${loaded ? `${loaded.name}, ${loaded.country.name}` : "not set"} → ${now || "not set"}`);
    } else {
      lines.push(`${display(row, state.get(row).loaded)} → ${display(row, readValue(row).value)}`);
    }
    lines.forEach((text) => {
      const p = document.createElement("p");
      p.className = "text-gray-900 break-words";
      p.textContent = text;
      div.appendChild(p);
    });
    if (row.dataset.confirmNote) {
      const note = document.createElement("p");
      note.className = "text-[#8A5A00]";
      note.textContent = row.dataset.confirmNote;
      div.appendChild(note);
    }
    return div;
  }

  const reviewDialog = document.getElementById("review-dialog");
  document.getElementById("review-changes").addEventListener("click", () => {
    const { changes, problems } = collect();
    if (problems.length) {
      problems.forEach(refresh);
      problems[0].scrollIntoView({ block: "center" });
      document.getElementById("save-bar-error").textContent = "Fix the highlighted values first.";
      return;
    }
    const list = document.getElementById("review-list");
    list.replaceChildren();
    sections.forEach((section) => {
      const namespace = section.dataset.section;
      if (!changes[namespace]) return;
      const group = document.createElement("div");
      group.className = "space-y-2";
      const title = document.createElement("p");
      title.className = "text-xs font-medium text-gray-500 uppercase tracking-wide";
      title.textContent = section.querySelector("h2").textContent;
      group.appendChild(title);
      changedRows().filter((row) => row.dataset.namespace === namespace && row.dataset.field in changes[namespace])
        .forEach((row) => group.appendChild(reviewLine(row)));
      list.appendChild(group);
    });
    document.getElementById("review-error").textContent = "";
    reviewDialog.showModal();
  });

  document.getElementById("confirm-save").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const { changes } = collect();
    button.disabled = true;
    const res = await fetch("/settings/save", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(changes),
    });
    const data = await res.json().catch(() => ({}));
    button.disabled = false;
    if (!res.ok) {
      document.getElementById("review-error").textContent = data.error || "Could not save the settings.";
      return;
    }
    Object.entries(data).forEach(([namespace, result]) => {
      const section = document.querySelector(`[data-section="${namespace}"]`);
      const error = section.querySelector("[data-section-error]");
      if (!result.ok) {
        error.textContent = result.error;
        error.classList.remove("hidden");
        return;
      }
      error.textContent = "";
      error.classList.add("hidden");
      rows.filter((row) => row.dataset.namespace === namespace && row.hasAttribute("data-changed")).forEach((row) => {
        const field = row.dataset.field;
        const saved = field in result.values ? result.values[field] : readValue(row).value;
        const extra = row.dataset.widget === "city" ? result.values[field.replace(/_id$/, "")] : undefined;
        if (row.dataset.widget === "city") row.querySelector("[data-city]").textContent = JSON.stringify(extra ?? null);
        if (row.dataset.widget === "place") {
          const label = row.querySelector("[data-place-label]");
          label.textContent = result.values.place_label ? `In use: ${result.values.place_label}` : "No weather now: add coordinates to the Home location or pick a place.";
          label.className = `text-[11px] ${result.values.place_label ? "text-gray-500" : "text-red-600"}`;
        }
        state.get(row).loaded = saved;
        row.dataset.value = JSON.stringify(saved);
        setValue(row, saved, extra);
        refresh(row);
      });
    });
    reviewDialog.close();
    const failed = Object.values(data).filter((result) => !result.ok).length;
    if (failed) document.getElementById("save-bar-error").textContent = `${failed} section${failed === 1 ? "" : "s"} could not be saved.`;
  });

  document.getElementById("discard-changes").addEventListener("click", () => {
    changedRows().forEach((row) => {
      const loaded = state.get(row).loaded;
      setValue(row, loaded, row.dataset.widget === "city" ? parse(row.querySelector("[data-city]").textContent) : undefined);
      refresh(row);
    });
  });

  window.addEventListener("beforeunload", (event) => {
    if (changedRows().length === 0) return;
    event.preventDefault();
    event.returnValue = "";
  });

  window.settingsPage = { applySearch, readValue, refresh };
})();
