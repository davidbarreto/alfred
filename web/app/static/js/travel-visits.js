// Visit dialog shared by the trip page and the place page (see templates/_travel_visit_dialog.html).
// config: { tripId: number|null, placeId: number|null } -- a fixed place hides the place picker.
function initTravelVisits(config) {
  const dialog = document.getElementById('visit-dialog');
  const form = document.getElementById('visit-form');
  if (!dialog || !form) return;
  const error = form.querySelector('.form-error');
  const placeSelect = form.elements.place_id;
  const newPlaceFields = document.getElementById('visit-new-place');
  let editing = null;

  async function send(method, url, body) {
    const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, data };
  }

  function syncPlaceFields() {
    if (!placeSelect) return;
    const isNew = placeSelect.value === 'new';
    newPlaceFields.classList.toggle('hidden', !isNew);
    form.elements.place_name.required = isNew;
  }
  placeSelect?.addEventListener('change', syncPlaceFields);

  function syncGrade() {
    const visited = form.elements.status.value === 'visited';
    form.elements.grade.disabled = !visited;
    if (!visited) form.elements.grade.value = '';
  }
  form.elements.status.addEventListener('change', syncGrade);

  function open(visit) {
    editing = visit;
    form.reset();
    error.textContent = '';
    document.getElementById('visit-title').textContent = visit ? 'Edit visit' : 'Add visit';
    if (placeSelect) {
      placeSelect.value = visit ? String(visit.place_id) : (config.placeId ? String(config.placeId) : 'new');
      if (visit && placeSelect.value !== String(visit.place_id)) {
        placeSelect.add(new Option(visit.place.name, visit.place_id, true, true));
      }
    }
    form.elements.status.value = visit ? visit.status : 'planned';
    form.elements.visit_date.value = visit && visit.visit_date ? visit.visit_date : '';
    form.elements.visit_time.value = visit && visit.visit_time ? visit.visit_time.slice(0, 5) : '';
    form.elements.grade.value = visit && visit.grade ? visit.grade : '';
    form.elements.notes.value = visit ? (visit.notes || '') : '';
    syncPlaceFields();
    syncGrade();
    dialog.showModal();
  }

  document.getElementById('add-visit')?.addEventListener('click', () => open(null));
  document.querySelectorAll('.edit-visit').forEach((b) => b.addEventListener('click', () => open(JSON.parse(b.dataset.item))));
  dialog.querySelector('[data-close]').addEventListener('click', () => dialog.close());

  document.querySelectorAll('.mark-visit').forEach((b) => b.addEventListener('click', async () => {
    const { ok, data } = await send('PATCH', `/travel/visits/${b.dataset.id}`, { status: b.dataset.status });
    if (!ok) { alert(data.error || 'Could not update the visit.'); return; }
    location.reload();
  }));

  document.querySelectorAll('.delete-visit').forEach((b) => b.addEventListener('click', async () => {
    if (!confirm('Delete this visit?')) return;
    const { ok, data } = await send('DELETE', `/travel/visits/${b.dataset.id}`);
    if (!ok) { alert(data.error || 'Could not delete the visit.'); return; }
    location.reload();
  }));

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    let placeId = placeSelect ? placeSelect.value : String(config.placeId);
    if (placeId === 'new') {
      const place = { kind: form.elements.place_kind.value, name: form.elements.place_name.value.trim() };
      for (const [field, input] of [['city', 'place_city'], ['country', 'place_country'], ['maps_url', 'place_maps_url']]) {
        const value = form.elements[input].value.trim();
        if (value) place[field] = value;
      }
      const created = await send('POST', '/travel/places', place);
      if (!created.ok) { error.textContent = created.data.error || 'Could not create the place.'; return; }
      placeId = created.data.id;
    }
    const body = { place_id: Number(placeId), status: form.elements.status.value };
    for (const name of ['visit_date', 'visit_time', 'notes']) {
      const value = form.elements[name].value.trim();
      if (value) body[name] = value; else if (editing) body[name] = null;
    }
    const grade = form.elements.grade.value;
    if (grade) body.grade = Number(grade); else if (editing) body.grade = null;
    if (!editing && config.tripId) body.trip_id = config.tripId;
    const { ok, data } = editing
      ? await send('PATCH', `/travel/visits/${editing.id}`, body)
      : await send('POST', '/travel/visits', body);
    if (!ok) { error.textContent = data.error || 'Something went wrong.'; return; }
    location.reload();
  });
}
