/*
 * Tag chip input: progressive enhancement for <input data-tag-input data-known='["Travel", ...]'>.
 *
 * The original input stays in the form (hidden) and keeps a comma-separated value, so server
 * code is unchanged. Existing names autocomplete per chip; a name that is not a known tag is
 * shown as a "new" chip, with a "Did you mean ...?" suggestion when it is close to a known
 * one, so a typo is visible before it silently becomes a new tag.
 */
(function () {
  const CHIP = "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs";
  const CHIP_KNOWN = CHIP + " bg-[#E6F1FB] text-[#0C447C]";
  const CHIP_NEW = CHIP + " bg-[#FDF1E2] text-[#8A5A0B]";

  function distance(a, b) {
    const prev = Array.from({ length: b.length + 1 }, (_, j) => j);
    for (let i = 1; i <= a.length; i++) {
      let diag = prev[0];
      prev[0] = i;
      for (let j = 1; j <= b.length; j++) {
        const tmp = prev[j];
        prev[j] = Math.min(prev[j] + 1, prev[j - 1] + 1, diag + (a[i - 1] === b[j - 1] ? 0 : 1));
        diag = tmp;
      }
    }
    return prev[b.length];
  }

  // Tags that have a budget; fetched once per page and shared by every input.
  let budgetedPromise = null;
  function budgetedTags() {
    if (!budgetedPromise) {
      budgetedPromise = fetch("/finance/tags/budgeted")
        .then((r) => (r.ok ? r.json() : []))
        .catch(() => []);
    }
    return budgetedPromise;
  }

  function parse(raw) {
    const seen = new Set();
    const out = [];
    (raw || "").split(",").forEach((part) => {
      const name = part.trim();
      if (name && !seen.has(name.toLowerCase())) {
        seen.add(name.toLowerCase());
        out.push(name);
      }
    });
    return out;
  }

  function enhance(input) {
    if (input.dataset.tagInputReady) return;
    input.dataset.tagInputReady = "1";

    let known = [];
    try { known = JSON.parse(input.dataset.known || "[]"); } catch (e) { known = []; }
    const canonical = (name) => known.find((k) => k.toLowerCase() === name.toLowerCase());
    const closest = (name) => {
      const lower = name.toLowerCase();
      let best = null;
      let bestDist = Infinity;
      known.forEach((k) => {
        const d = distance(lower, k.toLowerCase());
        if (d < bestDist) { best = k; bestDist = d; }
      });
      const limit = lower.length <= 4 ? 1 : 2;
      return best && bestDist <= limit && bestDist > 0 ? best : null;
    };

    let tags = [];
    const valueDesc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");

    const wrap = document.createElement("div");
    wrap.className = "border border-gray-200 rounded-lg px-2 py-1.5 bg-white w-full relative flex flex-wrap items-center gap-1 focus-within:ring-1 focus-within:ring-[#378ADD]";
    const chips = document.createElement("div");
    chips.className = "contents";
    const typed = document.createElement("input");
    typed.type = "text";
    typed.autocomplete = "off";
    typed.placeholder = input.getAttribute("placeholder") || "Add tag";
    typed.className = "flex-1 min-w-[90px] text-sm bg-transparent outline-none py-0.5";
    const menu = document.createElement("div");
    menu.className = "hidden absolute left-0 top-full mt-1 z-20 bg-white border border-gray-100 rounded-lg shadow-lg py-1 min-w-[180px] max-h-56 overflow-y-auto text-sm";
    const warning = document.createElement("p");
    warning.className = "hidden text-[11px] text-amber-600 mt-1";
    wrap.append(chips, typed, menu);
    input.after(wrap);
    wrap.after(warning);
    input.style.display = "none";

    let budgeted = [];
    if (!("noBudgetWarning" in input.dataset)) {
      budgetedTags().then((names) => { budgeted = names; render(); });
    }

    function sync() {
      valueDesc.set.call(input, tags.join(", "));
    }

    function updateWarning() {
      const picked = tags.filter((t) => budgeted.some((b) => b.toLowerCase() === t.toLowerCase()));
      if (picked.length > 1) {
        warning.textContent = picked.join(" and ") + " both have a budget. The transaction counts toward the older budget only.";
        warning.classList.remove("hidden");
      } else {
        warning.classList.add("hidden");
      }
    }

    function render() {
      chips.replaceChildren();
      tags.forEach((name, idx) => {
        const isNew = !canonical(name);
        const chip = document.createElement("span");
        chip.className = isNew ? CHIP_NEW : CHIP_KNOWN;
        chip.title = isNew ? "New tag: will be created" : "Existing tag";
        const label = document.createElement("span");
        label.textContent = isNew ? name + " (new)" : name;
        const remove = document.createElement("button");
        remove.type = "button";
        remove.textContent = "×";
        remove.className = "leading-none hover:text-red-600";
        remove.setAttribute("aria-label", "Remove " + name);
        remove.addEventListener("click", () => {
          tags.splice(idx, 1);
          sync();
          render();
          typed.focus();
        });
        chip.append(label, remove);
        chips.append(chip);
      });
      updateWarning();
    }

    function add(raw) {
      const name = raw.trim();
      if (!name) return;
      const final = canonical(name) || name;
      if (!tags.some((t) => t.toLowerCase() === final.toLowerCase())) tags.push(final);
      typed.value = "";
      sync();
      render();
      hideMenu();
    }

    function hideMenu() {
      menu.classList.add("hidden");
      menu.replaceChildren();
    }

    function option(text, hint, onPick) {
      const el = document.createElement("button");
      el.type = "button";
      el.className = "block w-full text-left px-3 py-1 hover:bg-gray-50 whitespace-nowrap";
      el.textContent = text;
      if (hint) {
        const h = document.createElement("span");
        h.className = "ml-2 text-[11px] text-gray-400";
        h.textContent = hint;
        el.append(h);
      }
      el.addEventListener("mousedown", (e) => { e.preventDefault(); onPick(); });
      return el;
    }

    function showMenu() {
      const query = typed.value.trim();
      const lower = query.toLowerCase();
      const taken = new Set(tags.map((t) => t.toLowerCase()));
      menu.replaceChildren();
      known
        .filter((k) => !taken.has(k.toLowerCase()) && (!lower || k.toLowerCase().includes(lower)))
        .slice(0, 8)
        .forEach((k) => menu.append(option(k, "", () => add(k))));
      if (query && !canonical(query)) {
        const near = closest(query);
        if (near && !taken.has(near.toLowerCase())) {
          menu.append(option("Did you mean " + near + "?", "", () => add(near)));
        }
        menu.append(option('Create "' + query + '"', "new tag", () => add(query)));
      }
      menu.classList.toggle("hidden", menu.children.length === 0);
    }

    typed.addEventListener("input", () => {
      if (typed.value.includes(",")) {
        const parts = typed.value.split(",");
        parts.slice(0, -1).forEach(add);
        typed.value = parts[parts.length - 1];
      }
      showMenu();
    });
    typed.addEventListener("focus", showMenu);
    typed.addEventListener("blur", () => { add(typed.value); hideMenu(); });
    typed.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === "Tab") {
        if (typed.value.trim()) { e.preventDefault(); add(typed.value); }
        else if (e.key === "Enter") e.preventDefault();
      } else if (e.key === "Backspace" && !typed.value && tags.length) {
        tags.pop();
        sync();
        render();
      }
    });
    wrap.addEventListener("click", () => typed.focus());

    // Programmatic `input.value = "a, b"` (the edit-transaction form) re-renders the chips.
    Object.defineProperty(input, "value", {
      get() { return valueDesc.get.call(input); },
      set(v) { valueDesc.set.call(input, v); tags = parse(v); render(); },
    });
    if (input.form) {
      input.form.addEventListener("reset", () => {
        setTimeout(() => { tags = parse(valueDesc.get.call(input)); render(); }, 0);
      });
    }

    tags = parse(input.value);
    render();
  }

  function init(root) {
    (root || document).querySelectorAll("input[data-tag-input]").forEach(enhance);
  }

  document.addEventListener("DOMContentLoaded", () => init(document));
  document.addEventListener("htmx:load", (e) => init(e.target));
  window.TagInput = { init };
})();
