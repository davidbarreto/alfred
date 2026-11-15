/*
 * City picker for the leg form: one input per leg end, backed by the saved cities (/travel/cities/search).
 * The hidden id is only sent when the user picked or cleared a city (`touched`); otherwise the backend matches the
 * terminal text on its own. The last option, "New city…", opens the new-city dialog (initNewCityDialog).
 */
(function () {
  const NEW = { isNew: true };

  const labelOf = (city) => (city ? `${city.name}, ${city.country.name}` : "");

  function initCityPicker({ input, idInput, clearButton, terminalInput, newCity }) {
    let label = "";
    let touched = false;

    function set(city, byUser) {
      idInput.value = city ? String(city.id) : "";
      label = labelOf(city);
      input.value = label;
      touched = byUser;
    }

    window.attachDropdown({
      input,
      isActive: () => true,
      find: async (query) => {
        const response = await fetch(`/travel/cities/search?q=${encodeURIComponent(query.trim())}`);
        const rows = response.ok ? await response.json() : [];
        return [...rows.slice(0, 8), NEW];
      },
      label: (row) => (row.isNew ? ["New city…", ""] : [row.name, row.country.name]),
      pick: (row) => {
        if (row.isNew) {
          input.value = label;
          newCity(terminalInput.value.trim(), (city) => set(city, true));
        } else {
          set(row, true);
        }
      },
    });
    // Text typed without picking never changes the city.
    input.addEventListener("blur", () => { input.value = label; });
    clearButton.addEventListener("click", () => set(null, true));

    return {
      reset: (city) => set(city || null, false),
      touched: () => touched,
      value: () => (idInput.value ? Number(idInput.value) : null),
    };
  }

  // The "New city…" dialog: name + country (typeahead with a hidden ISO code), POST /travel/cities.
  // A 409 means the city exists already: it is selected instead.
  function initNewCityDialog({ dialog, send }) {
    const form = dialog.querySelector("form");
    const error = form.querySelector(".form-error");
    window.initCountryInput({ input: form.elements.country, codeInput: form.elements.country_code });
    let onCreated = null;

    form.querySelector("[data-close]").addEventListener("click", () => dialog.close());
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const body = { name: form.elements.name.value.trim(), country: form.elements.country.value.trim() };
      if (form.elements.country_code.value) body.country_code = form.elements.country_code.value;
      const { ok, status, data } = await send("POST", "/travel/cities", body);
      if (ok) {
        dialog.close();
        onCreated(data);
        return;
      }
      if (status === 409) {
        const found = await (await fetch(`/travel/cities/search?q=${encodeURIComponent(body.name)}`)).json();
        const existing = found.find((c) => c.name.toLowerCase() === body.name.toLowerCase() && c.country.name.toLowerCase() === body.country.toLowerCase());
        if (existing) {
          dialog.close();
          onCreated(existing);
          return;
        }
      }
      error.textContent = data.error || "Could not create the city.";
    });

    return (name, done) => {
      form.reset();
      error.textContent = "";
      form.elements.name.value = name;
      onCreated = done;
      dialog.showModal();
    };
  }

  window.initCityPicker = initCityPicker;
  window.initNewCityDialog = initNewCityDialog;
})();
