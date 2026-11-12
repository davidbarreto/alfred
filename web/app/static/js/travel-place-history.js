// Shows what is already known about the place picked in a dialog: its grade, the "Would return" style tags and a link.
// Options carry data-grade, data-count and data-tags (comma separated); `hint` is the element to fill.
function initPlaceHistory(select, hint) {
  if (!select || !hint) return;
  function show() {
    const option = select.selectedOptions[0];
    hint.replaceChildren();
    if (!option || !option.dataset.href) return;
    const count = Number(option.dataset.count || 0);
    const tags = (option.dataset.tags || '').split(',').filter(Boolean);
    const parts = [];
    parts.push(count ? `Been here: ${Number(option.dataset.grade).toFixed(1)}/5 from ${count} rating${count === 1 ? '' : 's'}` : 'Known place, not graded yet');
    if (tags.length) parts.push(tags.join(', '));
    hint.append(`${parts.join(' · ')} `);
    const link = document.createElement('a');
    link.href = option.dataset.href;
    link.className = 'text-[#378ADD] hover:underline';
    link.textContent = 'History';
    hint.append(link);
  }
  select.addEventListener('change', show);
  select.addEventListener('place-history:refresh', show);
  show();
}
