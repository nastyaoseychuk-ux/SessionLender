// Reuse the real authenticated chat page, including sending, history and receipts.
(() => {
  if (window.top !== window || location.origin !== __SERVER_ORIGIN__) return;
  const report = () => window.quickPageState(JSON.stringify({
    path: location.pathname,
    visible: document.visibilityState === "visible",
    focused: document.hasFocus(),
  }));
  for (const event of ["focus", "blur", "pageshow"]) window.addEventListener(event, report);
  document.addEventListener("visibilitychange", report);
  window.addEventListener("pagehide", () => window.quickPageState(JSON.stringify({path: location.pathname, visible: false, focused: false})));
  setInterval(report, 15000);

  // Install CSS before the document is painted, avoiding a flash of the sidebar.
  const style = document.createElement("style");
  style.textContent = `
    html, body {margin:0!important; height:100%!important; overflow:hidden!important; background:#141619!important; color:#eef0f4; font-family:"Segoe UI",sans-serif}
    .sidebar,.topbar,.mobile-nav,.skip-link,.chat-head,.chat-members-panel {display:none!important}
    .shell,.main {display:flex!important; width:100%!important; height:100%!important; min-height:0!important; margin:0!important; padding:0!important}
    .shell {flex-direction:column!important}
    .main {flex:1!important; min-height:0!important}
    #mainContent {display:flex!important; flex:1!important; flex-direction:column!important; min-height:0!important; width:100%!important; max-width:none!important; padding:0 8px 8px!important; margin:0!important}
    .chat-window {flex:1!important; min-height:0!important; margin:0!important; border-radius:16px!important}
    .chat-messages {flex:1!important; min-height:0!important; padding:12px!important}
    .chat-form {padding:8px!important; gap:6px!important}
    .chat-form textarea {min-height:44px!important; max-height:70px!important; font-size:13px!important}
    .chat-bubble {max-width:100%!important; font-size:13px!important}
    .chat-message {gap:6px!important}
    .chat-form .btn {padding:8px!important; font-size:12px!important}
    #quickHeader {height:40px; flex:0 0 40px; display:flex; align-items:center; padding:0 14px; gap:10px; background:linear-gradient(120deg,#ffffff0c,#ffffff02); border-bottom:1px solid #ffffff12; user-select:none}
    #quickHeader strong {flex:1; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; font-size:12px}
    #quickHeader button {border:0; background:transparent; color:#bfc4cf; cursor:pointer; padding:5px; width:28px; height:28px}
    #quickHeader button:hover {color:white; background:#ffffff14; border-radius:7px}
  `;
  const installStyle = () => { if (document.head && !style.isConnected) document.head.append(style); };
  const observer = new MutationObserver(installStyle);
  observer.observe(document, {childList:true, subtree:true});
  installStyle();
  document.addEventListener("DOMContentLoaded", () => {
    installStyle(); observer.disconnect();
    const header = document.createElement("header");
    header.id = "quickHeader";
    const title = document.createElement("strong");
    title.textContent = document.querySelector(".chat-head h1")?.textContent.trim() || "SessionLender";
    const open = document.createElement("button");
    open.title = "Відкрити додаток"; open.setAttribute("aria-label", open.title);
    open.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M13 5H5v14h14v-8M12 12 21 3M14 3h7v7"/></svg>';
    open.onclick = () => window.quickOpen();
    const close = document.createElement("button");
    close.textContent = "×"; close.title = "Закрити"; close.setAttribute("aria-label", close.title);
    close.onclick = () => window.quickClose();
    header.append(title, open, close);
    header.onmousedown = event => { if (event.button === 0 && !event.target.closest("button")) window.quickDrag(); };
    const shell = document.querySelector(".shell");
    if (shell) shell.prepend(header);
    else {
      // An expired session may return the login page. Keep close/open available.
      Object.assign(header.style, {position:"fixed", top:"0", left:"0", right:"0", zIndex:"10000", background:"#181a1e"});
      document.body.prepend(header);
    }
    report();
  }, {once:true});
  document.addEventListener("keydown", event => { if (event.key === "Escape") window.quickClose(); });
  document.addEventListener("click", event => {
    const link = event.target.closest("a[href]");
    if (!link) return;
    const target = new URL(link.href, location.href);
    if (target.origin === location.origin && target.pathname === location.pathname && !link.target) return;
    event.preventDefault();
    // Keep the compact window on its chat. Other navigation opens the main app.
    if (target.origin === location.origin) window.quickOpen();
    else if (["https:", "http:"].includes(target.protocol)) window.quickExternal(target.href);
  }, true);
})();
