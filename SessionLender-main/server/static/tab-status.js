// One place controls the browser tab. Counts come from the existing inbox socket.
(() => {
  const favicon = document.getElementById("siteFavicon");
  if (!favicon) return;
  const originalTitle = document.title;
  const background = new Image();
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 64;
  let unread = Number(document.body.dataset.unread) || 0;
  function render() {
    document.title = unread ? `${unread} Нових повідомлень` : originalTitle;
    if (!unread) {
      favicon.href = favicon.dataset.logo;
      return;
    }
    if (!background.complete || !background.naturalWidth) return;
    const context = canvas.getContext("2d");
    context.clearRect(0, 0, 64, 64);
    context.drawImage(background, 0, 0, 64, 64);
    // The empty triangle leaves room for the count where the letters used to be.
    const label = String(unread);
    context.font = `bold ${Math.max(8, Math.min(23, 48 / label.length))}px sans-serif`;
    context.fillStyle = "#e6ffff";
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillText(label, 28, 32);
    favicon.href = canvas.toDataURL("image/png");
  }
  background.onload = render;
  background.src = favicon.dataset.unread;
  window.addEventListener("inbox:unread", (event) => {
    unread = Math.max(0, Number(event.detail.count) || 0);
    render();
  });
  render();
})();
