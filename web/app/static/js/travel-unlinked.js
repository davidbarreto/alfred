document.querySelectorAll('.link-unlinked').forEach((button) => button.addEventListener('click', async () => {
  const target = button.closest('[data-unlinked]').querySelector('.unlinked-target').value;
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
  document.getElementById('tx-detail-close').addEventListener('click', () => detailDialog.close());
  document.querySelectorAll('.tx-detail').forEach((link) => link.addEventListener('click', async () => {
    const body = document.getElementById('tx-detail-body');
    body.innerHTML = '<p class="text-sm text-gray-400">Loading…</p>';
    detailDialog.showModal();
    const res = await fetch(`/travel/transactions/${link.dataset.id}/detail`);
    body.innerHTML = await res.text();
  }));
}
