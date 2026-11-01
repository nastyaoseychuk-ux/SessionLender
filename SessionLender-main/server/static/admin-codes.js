// Only code creation is enhanced; other administrative actions submit normally.
(() => {
  function showNotice(message, code) {
    const notice = document.createElement('div');
    notice.className = 'alert alert-success';
    notice.setAttribute('role', 'status');
    notice.textContent = message;
    if (code) {
      // Keep the issued code available if the browser blocks clipboard access.
      const field = document.createElement('input');
      field.value = code;
      field.readOnly = true;
      field.setAttribute('aria-label', 'Тимчасовий код для копіювання');
      field.addEventListener('click', () => field.select());
      notice.append(document.createElement('br'), field);
    }
    document.querySelector('#mainContent').prepend(notice);
    return notice;
  }

  async function copyCode(code) {
    if (navigator.clipboard?.writeText) {
      try { await navigator.clipboard.writeText(code); return true; }
      catch { /* Try the compatible selection-based clipboard below. */ }
    }
    const field = document.createElement('textarea');
    field.value = code;
    field.style.cssText = 'position:fixed;left:-9999px;top:0';
    document.body.append(field);
    const focused = document.activeElement;
    field.select();
    let copied = false;
    try { copied = document.execCommand('copy'); }
    catch { /* The notice still contains the code for manual copying. */ }
    field.remove();
    focused?.focus({preventScroll:true});
    return copied;
  }

  for (const form of document.querySelectorAll('.user-actions')) {
    let pending = false;
    form.addEventListener('submit', async event => {
      const button = event.submitter;
      if (button?.value !== 'create-code') return;
      event.preventDefault();
      if (pending) return;
      // app.js already handles the button's existing confirmation dialog.
      const data = new FormData(form);
      data.set(button.name, button.value);
      pending = true;
      button.disabled = true;
      let notice;
      try {
        const response = await fetch(form.getAttribute('action') || location.href, {
          method:'POST', body:data, credentials:'same-origin', cache:'no-store',
          headers:{Accept:'application/json'},
        });
        if (!response.ok) throw new Error(`Сервер повернув HTTP ${response.status}.`);
        let result;
        if (response.headers.get('Content-Type')?.includes('application/json')) {
          result = await response.json();
        } else {
          // The original view redirects back with a Django flash message.
          // Read that same response; never repeat the POST to obtain the code.
          const page = new DOMParser().parseFromString(await response.text(), 'text/html');
          const alerts = [...page.querySelectorAll('#mainContent .alert')];
          const message = alerts.find(alert =>
            alert.textContent.includes('Тимчасовий код для @') && /\bSL-[A-F0-9]{12}\b/.test(alert.textContent));
          if (!message) {
            const error = alerts.find(alert => /alert-(error|danger|warning)/.test(alert.className));
            throw new Error(error?.textContent.trim() || 'Сервер не повернув сповіщення з кодом. Перевірте авторизацію адміністратора.');
          }
          result = {message:message.textContent.trim(), code:message.textContent.match(/\bSL-[A-F0-9]{12}\b/)[0]};
        }
        if (typeof result.code !== 'string' || !/^SL-[A-F0-9]{12}$/.test(result.code) || typeof result.message !== 'string') {
          throw new Error('Сервер повернув некоректну відповідь із кодом.');
        }
        notice = showNotice(result.message, result.code);
        const copied = await copyCode(result.code);
        const status = document.createElement('div');
        status.textContent = copied
          ? 'Код скопійовано в буфер обміну.'
          : 'Браузер заблокував копіювання. Натисніть на поле коду та скопіюйте його вручну.';
        notice.append(status);
      } catch (error) {
        if (!notice) {
          const failure = showNotice(`${error.message || 'Не вдалося отримати відповідь сервера.'} Не створюйте код повторно, поки не перевірите результат.`);
          failure.className = 'alert alert-error';
        }
      } finally {
        pending = false;
        button.disabled = false;
      }
    });
  }
})();
