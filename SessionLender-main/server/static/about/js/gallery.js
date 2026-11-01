import { byId } from "./dom.js";
export function createGallery(text, getTheme) {
  let activeSlide = 0;
  const cards = Array.from(document.querySelectorAll("[data-slide]"));
  const dialog = byId("galleryDialog");
  // Stacked gallery, keyboard navigation, swipe and full-size viewing.
  function updateGallery() {
    updateCards();
    updateDots();
    updateCaption();
  }

  function updateCards() {
    cards.forEach((card, index) => {
      let offset = (index - activeSlide + cards.length) % cards.length;
      if (offset > 2) offset -= cards.length;
      card.style.setProperty("--offset", offset);
      card.style.setProperty("--distance", Math.abs(offset));
      card.classList.toggle("active", index === activeSlide);
      card.tabIndex = index === activeSlide ? 0 : -1;
      card.setAttribute("aria-hidden", String(index !== activeSlide));
      const image = card.querySelector("img");
      image.src =
        getTheme() === "light" ? image.dataset.light : image.dataset.dark;
      image.alt =
        text("slide" + (index + 1)) +
        " — " +
        text(getTheme() === "light" ? "concept" : "screenshot");
      card.setAttribute("aria-label", image.alt);
    });
  }

  function updateDots() {
    document.querySelectorAll("[data-dot]").forEach((dot, index) => {
      if (index === activeSlide) dot.setAttribute("aria-current", "true");
      else dot.removeAttribute("aria-current");
      dot.setAttribute("aria-label", text("slide" + (index + 1)));
    });
  }

  function updateCaption() {
    byId("slideNumber").textContent = "0" + (activeSlide + 1) + " / 04";
    byId("slideTitle").textContent = text("slide" + (activeSlide + 1));
    const image = cards[activeSlide].querySelector("img");
    byId("expandedImage").src = image.src;
    byId("expandedImage").alt = image.alt;
    byId("expandedCaption").textContent = image.alt;
  }

  function moveGallery(direction) {
    activeSlide = (activeSlide + direction + cards.length) % cards.length;
    updateGallery();
  }
  byId("galleryPrev").addEventListener("click", () => moveGallery(-1));
  byId("galleryNext").addEventListener("click", () => moveGallery(1));
  byId("dialogPrev").addEventListener("click", () => moveGallery(-1));
  byId("dialogNext").addEventListener("click", () => moveGallery(1));
  byId("closeGallery").addEventListener("click", () => dialog.close());
  document.querySelectorAll("[data-dot]").forEach((dot) =>
    dot.addEventListener("click", () => {
      activeSlide = Number(dot.dataset.dot);
      updateGallery();
    }),
  );
  let pointerX = null,
    suppressClickUntil = 0;
  const gallery = byId("gallery");
  gallery.addEventListener("pointerdown", (event) => {
    pointerX = event.clientX;
  });
  gallery.addEventListener("pointerup", (event) => {
    if (pointerX !== null && Math.abs(event.clientX - pointerX) > 45) {
      moveGallery(event.clientX < pointerX ? 1 : -1);
      suppressClickUntil = Date.now() + 300;
    }
    pointerX = null;
  });
  gallery.addEventListener("pointercancel", () => {
    pointerX = null;
  });
  cards.forEach((card) =>
    card.addEventListener("click", () => {
      if (Date.now() < suppressClickUntil) return;
      updateGallery();
      if (typeof dialog.showModal === "function") dialog.showModal();
    }),
  );
  gallery.addEventListener("keydown", (event) => {
    if (["ArrowLeft", "ArrowRight"].includes(event.key)) {
      event.preventDefault();
      moveGallery(event.key === "ArrowLeft" ? -1 : 1);
      cards[activeSlide].focus();
    }
  });
  dialog.addEventListener("keydown", (event) => {
    if (["ArrowLeft", "ArrowRight"].includes(event.key)) {
      event.preventDefault();
      moveGallery(event.key === "ArrowLeft" ? -1 : 1);
    }
  });
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  if (!reducedMotion.matches) {
    window.setInterval(() => {
      if (
        !document.hidden &&
        !dialog.open &&
        !gallery.matches(":hover") &&
        !gallery.contains(document.activeElement)
      )
        moveGallery(1);
    }, 6500);
  }

  return { refresh: updateGallery };
}
