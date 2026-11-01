import { byId } from "./dom.js";
import { translations } from "./translations.js";
import { readPreference, savePreference } from "./preferences.js";
import { createChatDemo } from "./chat-demo.js";
import { createInvitationDemo } from "./invitation-demo.js";
import { createFeedDemo } from "./feed-demo.js";
import { initializeDemoTabs } from "./demo-tabs.js";
import { createGallery } from "./gallery.js";
import { initializeAnimations } from "./animations.js";

// This page only simulates app actions; no demo calls the server API.
let language = readPreference("sl-about-language", "uk") === "en" ? "en" : "uk";
const requestedLanguage = new URLSearchParams(location.search).get("lang");
if (["uk", "en"].includes(requestedLanguage)) language = requestedLanguage;
let theme =
  document.documentElement.dataset.theme === "light" ? "light" : "dark";

const text = (key) => translations[language][key] || key;
const chat = createChatDemo(text, () => language);
const invitation = createInvitationDemo(text);
const feed = createFeedDemo(text);
const gallery = createGallery(text, () => theme);
initializeDemoTabs();
function translatePage() {
  document.documentElement.lang = language;
  document.title = text("pageTitle");
  document.querySelector('meta[name="description"]').content =
    text("heroDescription");
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = text(node.dataset.i18n);
  });
  document.querySelectorAll("[data-placeholder]").forEach((node) => {
    node.placeholder = text(node.dataset.placeholder);
  });
  document.querySelectorAll("[data-label]").forEach((node) => {
    node.setAttribute("aria-label", text(node.dataset.label));
  });
  byId("languageToggle").textContent = language === "uk" ? "UA" : "EN";
  byId("languageToggle").setAttribute(
    "aria-label",
    language === "uk" ? "Switch to English" : "Перемкнути на українську",
  );
  updateThemeLabel();
  invitation.refresh();
  feed.refresh();
  chat.refresh();
  gallery.refresh();
}
function updateThemeLabel() {
  byId("themeToggle").setAttribute(
    "aria-label",
    text(theme === "dark" ? "lightTheme" : "darkTheme"),
  );
  byId("themeToggle").setAttribute("aria-pressed", String(theme === "light"));
  byId("themeIcon").textContent = theme === "dark" ? "☀" : "☾";
  const note = byId("galleryNote");
  note.textContent = text(
    theme === "dark" ? "darkGalleryNote" : "lightGalleryNote",
  );
}
function setTheme(nextTheme) {
  theme = nextTheme;
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]').content =
    theme === "dark" ? "#0a0d10" : "#f6f9fb";
  savePreference("sl-about-theme", theme);
  updateThemeLabel();
  gallery.refresh();
}
byId("languageToggle").addEventListener("click", () => {
  language = language === "uk" ? "en" : "uk";
  savePreference("sl-about-language", language);
  translatePage();
});
byId("themeToggle").addEventListener("click", () =>
  setTheme(theme === "dark" ? "light" : "dark"),
);

translatePage();
setTheme(theme);
initializeAnimations();
