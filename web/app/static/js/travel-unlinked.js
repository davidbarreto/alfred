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
