document.querySelectorAll('.link-unlinked').forEach((button) => button.addEventListener('click', async () => {
  const target = button.closest('[data-unlinked], [data-tagged]').querySelector('.unlinked-target').value;
  if (!target) return;
  const [kind, id] = target.split(':');
  const res = await fetch(`/travel/links/${kind}/${id}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ transaction_id: Number(button.dataset.id) }),
  });
  const data = await res.json().catch(() => ({}));
  if (res.ok) location.reload(); else alert(data.error || 'Could not link the charge.');
}));

const detailDialog = document.getElementById('tx-detail-dialog');
if (detailDialog) {
  const body = document.getElementById('tx-detail-body');
  const show = async (path, id) => {
    body.innerHTML = '<p class="text-sm text-gray-400">Loading…</p>';
    const res = await fetch(`/travel/transactions/${id}/${path}`);
    body.innerHTML = await res.text();
    if (path === 'edit' && window.TagInput) window.TagInput.init(body);
  };
  document.getElementById('tx-detail-close').addEventListener('click', () => detailDialog.close());
  document.querySelectorAll('.tx-detail').forEach((link) => link.addEventListener('click', () => {
    detailDialog.showModal();
    show('detail', link.dataset.id);
  }));
  body.addEventListener('click', (event) => {
    const edit = event.target.closest('.tx-edit');
    if (edit) show('edit', edit.dataset.id);
    const cancel = event.target.closest('.tx-edit-cancel');
    if (cancel) show('detail', cancel.dataset.id);
  });
  body.addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    const data = Object.fromEntries(new FormData(form));
    const payload = {
      // Expense/income are stored as a positive magnitude; only transfers keep a sign.
      amount: data.type === 'transfer' ? data.amount : String(Math.abs(parseFloat(data.amount) || 0)),
      type: data.type,
      account_id: Number(data.account_id),
      category_id: data.category_id ? Number(data.category_id) : null,
      merchant: data.merchant || null,
      description: data.description || null,
      note: data.note || null,
      tags: data.tags.split(',').map((tag) => tag.trim()).filter(Boolean),
    };
    // An unchanged date is left out so the transaction keeps its time of day.
    if (data.date !== form.dataset.originalDate) payload.date = data.date;
    const res = await fetch(`/travel/transactions/${form.dataset.id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    });
    if (res.ok) { location.reload(); return; }
    const error = (await res.json().catch(() => ({}))).error;
    const errorEl = document.getElementById('tx-edit-error');
    errorEl.textContent = error || 'Could not save the transaction.';
    errorEl.classList.remove('hidden');
  });
}
