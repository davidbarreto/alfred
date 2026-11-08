/*
 * Searchable select: progressive enhancement for <select data-searchable>.
 *
 * The native <select> stays in the DOM (hidden) and remains the source of truth, so form
 * submits, `onchange` handlers and code that rewrites its options keep working. The widget
 * is a button that opens a panel with a search box above the full, scrollable option list.
 */
(function () {
  function enhance(select) {
    if (select.dataset.searchableReady) return;
    select.dataset.searchableReady = "1";

    const wrap = document.createElement("div");
    wrap.className = "relative inline-block";
    const button = document.createElement("button");
    button.type = "button";
    button.className = (select.className || "") + " flex items-center gap-1.5 text-left cursor-pointer";
    const label = document.createElement("span");
    label.className = "truncate";
    const chevron = document.createElement("i");
    chevron.className = "ti ti-chevron-down text-xs ml-auto text-gray-400";
    button.append(label, chevron);

    const panel = document.createElement("div");
    panel.className = "hidden absolute left-0 top-full mt-1 z-20 bg-white border border-gray-100 rounded-lg shadow-lg p-2 min-w-[180px]";
    const search = document.createElement("input");
    search.type = "search";
    search.autocomplete = "off";
    search.placeholder = "Search…";
    search.className = "w-full mb-2 border border-gray-200 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-[#378ADD]";
    const list = document.createElement("div");
    list.className = "max-h-60 overflow-y-auto";
    panel.append(search, list);
    wrap.append(button, panel);
    // Before the select, so code using select.nextElementSibling still finds its sibling.
    select.before(wrap);
    select.style.display = "none";

    function syncButton() {
      const opt = select.options[select.selectedIndex];
      label.textContent = opt ? opt.text : "";
      button.disabled = select.disabled;
      button.classList.toggle("opacity-50", select.disabled);
    }

    function renderList() {
      const q = search.value.trim().toLowerCase();
      list.replaceChildren();
      Array.from(select.options).forEach((opt) => {
        if (q && !opt.text.toLowerCase().includes(q)) return;
        const item = document.createElement("button");
        item.type = "button";
        item.textContent = opt.text;
        item.className = "block w-full text-left px-2 py-1 text-sm rounded hover:bg-gray-50 whitespace-nowrap"
          + (opt.selected ? " font-medium text-[#378ADD]" : " text-gray-700");
        item.addEventListener("click", () => {
          select.value = opt.value;
          close();
          syncButton();
          select.dispatchEvent(new Event("change", { bubbles: true }));
        });
        list.append(item);
      });
      if (!list.children.length) {
        const none = document.createElement("p");
        none.className = "px-2 py-1 text-sm text-gray-400";
        none.textContent = "No matches";
        list.append(none);
      }
    }

    function close() {
      panel.classList.add("hidden");
      search.value = "";
    }

    button.addEventListener("click", () => {
      if (!panel.classList.contains("hidden")) { close(); return; }
      renderList();
      panel.classList.remove("hidden");
      search.focus();
    });
    search.addEventListener("input", renderList);
    search.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { close(); button.focus(); }
      else if (e.key === "Enter") {
        e.preventDefault();
        const first = list.querySelector("button");
        if (first) first.click();
      }
    });
    document.addEventListener("click", (e) => { if (!wrap.contains(e.target)) close(); });

    // Code such as the budget tag picker rewrites options and `disabled` at runtime.
    new MutationObserver(syncButton).observe(select, { childList: true, attributes: true });
    syncButton();
  }

  function init(root) {
    (root || document).querySelectorAll("select[data-searchable]").forEach(enhance);
  }

  document.addEventListener("DOMContentLoaded", () => init(document));
  document.addEventListener("htmx:load", (e) => init(e.target));
  window.SearchableSelect = { init };
})();
