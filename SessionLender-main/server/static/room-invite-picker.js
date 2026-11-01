(() => {
  const dialog = document.querySelector('[data-room-invite-picker]');
  if (!dialog) return;
  const form = dialog.querySelector('form');
  let opener;
  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-room-invite-open]');
    if (!button || button.disabled) return;
    opener = button;
    form.querySelector('[data-room-invite-nickname]').value = button.dataset.nickname;
    dialog.querySelector('[data-room-invite-recipient]').textContent = 'Запросити @' + button.dataset.nickname;
    const create = dialog.querySelector('[data-room-invite-create]');
    const userId = button.dataset.userId;
    create.href = userId ? '/rooms/?invitee=' + encodeURIComponent(userId) : '/rooms/';
    dialog.showModal();
  });
  dialog.querySelector('[data-room-invite-close]').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => { if (opener?.isConnected) opener.focus(); });
})();
