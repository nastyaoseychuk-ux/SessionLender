// Runs only inside the trusted application origin. Cookies stay HttpOnly.
(() => {
  if (window.top !== window || location.origin !== __SERVER_ORIGIN__) return;
  let stopped = false;
  let renewal;
  let retryDelay = 2000;

  function csrfToken() {
    const field = document.querySelector('[name="csrfmiddlewaretoken"]');
    if (field && field.value) return field.value;
    const cookie = document.cookie.split(";").map(value => value.trim());
    const match = cookie.find(value => value.startsWith("csrftoken="));
    return match ? decodeURIComponent(match.slice("csrftoken=".length)) : "";
  }

  async function synchronizeSession() {
    try {
      const response = await fetch("/desktop/session/", {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: {"X-CSRFToken": csrfToken()},
      });
      if (stopped) return;
      if (response.status === 401 || response.status === 403) {
        await window.desktopSession("");
        return;
      }
      if (!response.ok) {
        const failure = new Error("Desktop endpoint unavailable");
        failure.display = response.status === 404
          ? "Оновіть сервер: /desktop/session/ відсутній"
          : "Сервер сповіщень: HTTP " + response.status;
        throw failure;
      }
      const session = await response.json();
      if (!stopped) await window.desktopSession(JSON.stringify(session));
      retryDelay = 2000;
      if (!stopped) renewal = setTimeout(synchronizeSession, 20 * 60 * 1000);
    } catch (error) {
      // A network error must not discard an already working native connection.
      if (!stopped) {
        window.desktopStatus(error.display || "Повторна спроба підключення сповіщень…");
        renewal = setTimeout(synchronizeSession, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 60000);
      }
    }
  }

  function reportPageState() {
    window.desktopPageState(JSON.stringify({
      path: location.pathname,
      visible: document.visibilityState === "visible",
      focused: document.hasFocus(),
    }));
  }
  window.addEventListener("focus", reportPageState);
  window.addEventListener("blur", reportPageState);
  document.addEventListener("visibilitychange", reportPageState);
  window.addEventListener("popstate", reportPageState);
  const pageHeartbeat = setInterval(reportPageState, 15000);

  document.addEventListener("DOMContentLoaded", () => {
    const style = document.createElement("style");
    style.textContent = ".topbar-download{display:none!important}";
    document.head.append(style);
    reportPageState();
    synchronizeSession();
  }, {once:true});

  window.addEventListener("pageshow", event => {
    if (event.persisted) {stopped = false; reportPageState(); synchronizeSession();}
  });
  window.addEventListener("pagehide", () => { stopped = true; clearTimeout(renewal); window.desktopPageState(JSON.stringify({path:location.pathname,visible:false,focused:false})); });
  document.addEventListener("click", event => {
    const link = event.target.closest("a[href]");
    if (!link) return;
    const target = new URL(link.href, location.href);
    if (target.origin === location.origin) {
      // Keep target=_blank app links inside the same authenticated window.
      if (link.target === "_blank") {event.preventDefault(); location.href = target.href;}
      return;
    }
    event.preventDefault();
    if (["https:", "http:"].includes(target.protocol)) window.desktopOpenExternal(target.href);
  }, true);
})();
