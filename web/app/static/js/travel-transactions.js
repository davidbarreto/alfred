// Link finance transactions to a leg, stay or visit (see templates/_travel_tx_dialog.html).
function initTravelTransactions() {
  const dialog = document.getElementById('tx-dialog');
  if (!dialog) return;
  const linked = document.getElementById('tx-linked');
  const results = document.getElementById('tx-results');
  const search = document.getElementById('tx-search');
  const error = document.getElementById('tx-error');
  const cost = document.getElementById('tx-cost');
  let current = null;
  let changed = false;
  let timer = null;

  const money = (value) => (value === null || value === undefined ? 'no EUR amount' : `${Number(value).toFixed(2)} €`);
  const line = (t) => `${t.date.slice(0, 10)} · ${t.merchant || t.description || '(no name)'} · ${Number(t.amount).toFixed(2)} ${t.currency}`;

  async function call(method, url, body) {
    const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, data };
  }

  function row(text, label, onClick, danger, openId) {
    const el = document.createElement('div');
    el.className = 'flex items-center justify-between gap-2 text-xs';
    const span = document.createElement('span');
    span.textContent = text;
    const button = document.createElement('button');
    button.className = 'btn btn-xs btn-ghost' + (danger ? ' text-red-600' : '');
    button.textContent = label;
    button.addEventListener('click', onClick);
    const actions = document.createElement('span');
    actions.className = 'flex items-center gap-1 shrink-0';
    if (openId) {
      const open = document.createElement('a');
      open.className = 'btn btn-xs btn-ghost text-[#378ADD]';
      open.href = `/finance/transactions?open=${openId}`;
      open.textContent = 'Open';
      actions.append(open);
    }
    actions.append(button);
    el.append(span, actions);
    return el;
  }

  function render(data) {
    linked.replaceChildren(...data.transactions.map((t) => row(line(t) + ` · ${money(t.amount_eur)}`, 'Unlink', async () => {
      const r = await call('DELETE', `/travel/links/${current.kind}/${current.id}/${t.id}`);
      if (!r.ok) { error.textContent = r.data.error || 'Could not unlink.'; return; }
      changed = true;
      load();
    }, true, t.id)));
    if (!data.transactions.length) linked.textContent = 'Nothing linked yet.';
    const c = data.cost;
    cost.textContent = c.transaction_count
      ? `Total ${Number(c.total_eur).toFixed(2)} €${c.unconverted_count ? ` (${c.unconverted_count} without an EUR amount, not counted)` : ''}`
      : '';
  }

  async function load() {
    error.textContent = '';
    const { ok, data } = await call('GET', `/travel/links/${current.kind}/${current.id}`);
    if (!ok) { error.textContent = data.error || 'Could not load.'; return; }
    render(data);
  }

  async function runSearch() {
    results.replaceChildren();
    const q = search.value.trim();
    if (!q) return;
    const res = await fetch(`/travel/transactions/search?q=${encodeURIComponent(q)}`);
    const data = await res.json().catch(() => []);
    if (!res.ok) { error.textContent = data.error || 'Search failed.'; return; }
    results.replaceChildren(...data.map((t) => row(line(t), 'Link', async () => {
      const r = await call('POST', `/travel/links/${current.kind}/${current.id}`, { transaction_id: t.id });
      if (!r.ok) { error.textContent = r.data.error || 'Could not link.'; return; }
      changed = true;
      render(r.data);
    })));
    if (!data.length) results.textContent = 'No transactions match.';
  }

  search.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(runSearch, 300); });
  document.getElementById('tx-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => { if (changed) location.reload(); });

  document.querySelectorAll('.tx-open').forEach((button) => button.addEventListener('click', () => {
    current = { kind: button.dataset.kind, id: button.dataset.id };
    changed = false;
    search.value = '';
    results.replaceChildren();
    document.getElementById('tx-title').textContent = `Transactions: ${button.dataset.title}`;
    dialog.showModal();
    load();
  }));
}
