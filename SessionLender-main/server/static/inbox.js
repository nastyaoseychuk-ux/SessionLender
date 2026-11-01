// Unread counters: WebSocket push when available, HTTP polling fallback on hosts
// without WebSockets (Vercel serverless cannot hold ws:// connections).
(() => {
  let socket,
    stopped = false,
    retry = 1000,
    failures = 0,
    pollTimer = null;

  const setBadge = (count) => {
    window.dispatchEvent(
      new CustomEvent("inbox:unread", { detail: { count } }),
    );
    document.querySelectorAll('a[href="/messages/"]').forEach((link) => {
      const mobile = !!link.closest(".mobile-nav");
      let badge = link.querySelector(".nav-badge, .nav-dot");
      if (!count) {
        badge?.remove();
        return;
      }
      if (!badge) {
        badge = document.createElement("b");
        badge.className = mobile ? "nav-dot" : "nav-badge";
        (mobile ? link.querySelector(".mobile-icon-wrap") : link).appendChild(
          badge,
        );
      }
      badge.textContent = count;
    });
  };

  const startPolling = () => {
    if (pollTimer) return;
    const tick = async () => {
      try {
        const response = await fetch("/messages/unread-count/", {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        });
        if (response.ok) setBadge((await response.json()).count);
      } catch (_) {
        /* network hiccup; next tick retries */
      }
    };
    tick();
    pollTimer = setInterval(tick, 30000);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) tick();
    });
  };

  const stopPolling = () => {
    clearInterval(pollTimer);
    pollTimer = null;
  };

  const connect = () => {
    if (stopped || pollTimer) return;
    let opened = false;
    socket = new WebSocket(
      `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/ws/inbox/`,
    );
    socket.onopen = () => {
      opened = true;
      failures = 0;
      retry = 1000;
    };
    socket.onmessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (_) {
        return;
      }
      if (data.type !== "unread") return;
      setBadge(data.count);
    };
    socket.onclose = (event) => {
      if ([4403, 1008].includes(event.code)) return;
      if (stopped) return;
      if (!opened) failures += 1;
      if (failures >= 3) {
        startPolling();
        return;
      }
      setTimeout(connect, retry + Math.random() * 500);
      retry = Math.min(retry * 2, 30000);
    };
  };

  window.addEventListener("pageshow", (event) => {
    if (event.persisted) {
      stopped = false;
      if (!pollTimer) connect();
    }
  });
  window.addEventListener("pagehide", () => {
    stopped = true;
    socket?.close();
  });
  connect();
})();
