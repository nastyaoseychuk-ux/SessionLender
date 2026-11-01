(() => {
  const form = document.querySelector('[data-friend-nickname-search]');
  if (!form) return;
  const input = form.querySelector('[name="q"]');
  const error = document.getElementById('friend-search-error');
  form.addEventListener('submit', (event) => {
    const value = input.value.trim();
    let message = '';
    if (value && !value.startsWith('@')) message = 'Нікнейм має починатися із символу @. Наприклад: @nickname.';
    else if (!/^@[^@\s]+$/.test(value)) message = 'Введіть нікнейм після @ без пробілів. Наприклад: @nickname.';
    if (message) {
      event.preventDefault();
      error.textContent = message;
      error.hidden = false;
      input.setAttribute('aria-invalid', 'true');
      input.focus();
    } else input.value = value;
  });
  input.addEventListener('input', () => {
    error.hidden = true;
    input.setAttribute('aria-invalid', 'false');
  });
})();
