try {
  document.documentElement.dataset.theme =
    localStorage.getItem("sl-about-theme") === "light" ? "light" : "dark";
} catch (e) {}
