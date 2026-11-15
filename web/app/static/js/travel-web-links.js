// Add / edit / delete links on the trip page, the place page and the links pages
// (see templates/_travel_web_link_dialog.html and _travel_web_link_row.html).
// Owners: trip, place, city or country.
// Buttons: .add-web-link (data-owner-kind, data-owner-id), .edit-web-link (data-item), .delete-web-link (data-id).
const OWNER_PATHS = { trip: 'trips', place: 'places', city: 'cities', country: 'countries' };

function initWebLinks() {
  const dialog = document.getElementById('web-link-dialog');
  const form = document.getElementById('web-link-form');
  if (!dialog || !form) return;
  const title = document.getElementById('web-link-title');
  const autoOption = document.getElementById('web-link-auto');
  const error = form.querySelector('.form-error');
  let owner = null;   // { kind: 'trip'|'place'|'city'|'country', id } when adding
  let editing = null; // the link being edited

  async function send(method, url, body) {
    const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, data };
  }

  function open(heading) {
    title.textContent = heading;
    error.textContent = '';
    dialog.showModal();
  }

  document.querySelectorAll('.add-web-link').forEach((button) => button.addEventListener('click', () => {
    owner = { kind: button.dataset.ownerKind, id: button.dataset.ownerId };
    editing = null;
    form.reset();
    autoOption.hidden = false;
    open('Add link');
  }));

  document.querySelectorAll('.edit-web-link').forEach((button) => button.addEventListener('click', () => {
    editing = JSON.parse(button.dataset.item);
    owner = null;
    form.reset();
    autoOption.hidden = true;
    form.elements.url.value = editing.url;
    form.elements.kind.value = editing.kind;
    form.elements.title.value = editing.title || '';
    form.elements.notes.value = editing.notes || '';
    open('Edit link');
  }));

  document.querySelectorAll('.delete-web-link').forEach((button) => button.addEventListener('click', async () => {
    if (!confirm('Delete this link?')) return;
    const { ok, data } = await send('DELETE', `/travel/web-links/${button.dataset.id}`);
    if (!ok) { alert(data.error || 'Could not delete the link.'); return; }
    location.reload();
  }));

  form.querySelector('[data-close]').addEventListener('click', () => dialog.close());

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const url = form.elements.url.value.trim();
    const linkTitle = form.elements.title.value.trim();
    const notes = form.elements.notes.value.trim();
    const kind = form.elements.kind.value;
    let result;
    if (editing) {
      // Only what changed: a new address re-fetches the preview, an untouched one must not.
      const body = {};
      if (url !== editing.url) body.url = url;
      if (kind !== editing.kind) body.kind = kind;
      if (linkTitle !== (editing.title || '')) body.title = linkTitle || null;
      if (notes !== (editing.notes || '')) body.notes = notes || null;
      if (!Object.keys(body).length) { dialog.close(); return; }
      result = await send('PATCH', `/travel/web-links/${editing.id}`, body);
    } else {
      const body = { url, notes: notes || null };
      if (kind) body.kind = kind;
      if (linkTitle) body.title = linkTitle;
      result = await send('POST', `/travel/${OWNER_PATHS[owner.kind]}/${owner.id}/links`, body);
    }
    if (!result.ok) { error.textContent = result.data.error || 'Something went wrong.'; return; }
    location.reload();
  });
}
