/*
 * /settings: search over the setting rows. Every row is on the page, so the filter runs in the browser; it matches the
 * label, key and description (data-search), hides sections with no match, updates the counts in the section nav and
 * keeps the query in ?q= so a filtered view can be linked to.
 */
(function () {
  const search = document.getElementById("settings-search");
  const noMatch = document.getElementById("settings-no-match");
  const sections = [...document.querySelectorAll("[data-section]")];

  function applySearch(query) {
    const q = query.trim().toLowerCase();
    let shownSections = 0;
    sections.forEach((section) => {
      let shown = 0;
      section.querySelectorAll("[data-setting-row], [data-link-row]").forEach((row) => {
        const match = !q || row.dataset.search.includes(q);
        row.classList.toggle("hidden", !match);
        if (match && row.hasAttribute("data-setting-row")) shown += 1;
      });
      section.querySelectorAll("[data-group]").forEach((group) => {
        group.classList.toggle("hidden", !group.querySelector("[data-setting-row]:not(.hidden)"));
      });
      const visible = !q || section.querySelector("[data-setting-row]:not(.hidden), [data-link-row]:not(.hidden)");
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
    if (search.value) applySearch(search.value);
  }

  window.settingsPage = { applySearch };
})();
