// Read-only detail dialog for legs, stays and visits (see templates/_travel_detail_dialog.html).
// A row opts in with class "detail-row", data-detail-kind="leg|stay|visit" and data-detail="<item json>".
// Clicks on buttons, links and inputs inside the row keep their own behaviour.
function initTravelDetail() {
  const dialog = document.getElementById('detail-dialog');
  if (!dialog) return;
  const title = document.getElementById('detail-title');
  const body = document.getElementById('detail-body');

  const shortDate = (iso) => new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
  const local = (iso, tz) => `${shortDate(iso)} ${iso.slice(11, 16)}${tz ? ` (${tz})` : ''}`;
  const link = (url, label) => ({ url, label });

  const builders = {
    leg: (d) => ({
      title: `${d.origin} → ${d.destination}`,
      rows: [
        ['Mode', d.mode],
        ['From', d.origin_code ? `${d.origin} (${d.origin_code})` : d.origin],
        ['To', d.destination_code ? `${d.destination} (${d.destination_code})` : d.destination],
        ['Departs', local(d.departs_local, d.departs_tz)],
        ['Arrives', local(d.arrives_local, d.arrives_tz)],
        ['Carrier', d.carrier],
        ['Number', d.number],
        ['Booking ref', d.booking_ref],
        ['Seat', d.seat],
        ['Booking link', d.booking_url && link(d.booking_url, 'Open')],
        ['Calendar event', d.calendar_event_id ? 'Linked' : null],
        ['Notes', d.notes],
      ],
    }),
    stay: (d) => ({
      title: d.place.name,
      rows: [
        ['City', [d.place.city, d.place.country].filter(Boolean).join(', ')],
        ['Address', d.place.address],
        ['Map', link(d.place.maps_link, 'Open')],
        ['Check-in', local(d.check_in_local, d.timezone)],
        ['Check-out', local(d.check_out_local, d.timezone)],
        ['Nights', d.nights],
        ['Booking ref', d.booking_ref],
        ['Booking link', d.booking_url && link(d.booking_url, 'Open')],
        ['Grade', d.grade ? `${d.grade}/5` : null],
        ['Calendar event', d.calendar_event_id ? 'Linked' : null],
        ['Notes', d.notes],
      ],
    }),
    visit: (d) => ({
      title: d.place.name,
      rows: [
        ['Status', d.status],
        ['Day', d.visit_date ? shortDate(d.visit_date) : 'No day yet'],
        ['Time', d.visit_time && d.visit_time.slice(0, 5)],
        ['City', [d.place.city, d.place.country].filter(Boolean).join(', ')],
        ['Address', d.place.address],
        ['Map', link(d.place.maps_link, 'Open')],
        ['Trip', d.trip_name],
        ['Grade', d.grade ? `${d.grade}/5` : null],
        ['Calendar event', d.calendar_event_id ? 'Linked' : null],
        ['Notes', d.notes],
      ],
    }),
  };

  function render(kind, data) {
    const view = builders[kind](data);
    title.textContent = view.title;
    body.replaceChildren();
    for (const [label, value] of view.rows) {
      if (value === null || value === undefined || value === '') continue;
      const row = document.createElement('div');
      row.className = 'grid grid-cols-3 gap-2 text-sm';
      const term = document.createElement('span');
      term.className = 'text-xs text-gray-500';
      term.textContent = label;
      const desc = document.createElement('span');
      desc.className = 'col-span-2 text-gray-900 whitespace-pre-line break-words';
      if (typeof value === 'object') {
        const a = document.createElement('a');
        a.href = value.url;
        a.target = '_blank';
        a.rel = 'noopener';
        a.className = 'text-[#378ADD] hover:underline';
        a.textContent = value.label;
        desc.appendChild(a);
      } else {
        desc.textContent = String(value);
      }
      row.append(term, desc);
      body.appendChild(row);
    }
    dialog.showModal();
  }

  document.querySelectorAll('.detail-row').forEach((row) => row.addEventListener('click', (event) => {
    if (event.target.closest('button, a, input, select, textarea, label')) return;
    render(row.dataset.detailKind, JSON.parse(row.dataset.detail));
  }));
  document.getElementById('detail-close').addEventListener('click', () => dialog.close());
}
