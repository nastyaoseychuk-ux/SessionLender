import { byId } from "./dom.js";
export function initializeDemoTabs() {
  // Accessible tabs: mouse, keyboard arrows, Home and End.
  const tabs = Array.from(document.querySelectorAll("[data-demo]"));
  function selectDemo(name, focus = false) {
    tabs.forEach((tab) => {
      const selected = tab.dataset.demo === name;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      byId(tab.getAttribute("aria-controls")).hidden = !selected;
      if (selected && focus) tab.focus();
    });
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => selectDemo(tab.dataset.demo));
    tab.addEventListener("keydown", (event) => {
      let target;
      if (event.key === "ArrowRight") target = (index + 1) % tabs.length;
      if (event.key === "ArrowLeft")
        target = (index + tabs.length - 1) % tabs.length;
      if (event.key === "Home") target = 0;
      if (event.key === "End") target = tabs.length - 1;
      if (target !== undefined) {
        event.preventDefault();
        selectDemo(tabs[target].dataset.demo, true);
      }
    });
  });
}
