export function initializeAnimations() {
  function updateProgress() {
    const available =
      document.documentElement.scrollHeight - window.innerHeight;
    const progress = available > 0 ? window.scrollY / available : 0;
    document.querySelector(".scroll-progress").style.transform =
      `scaleX(${Math.min(1, Math.max(0, progress))})`;
  }
  window.addEventListener("scroll", updateProgress, { passive: true });
  window.addEventListener("resize", updateProgress);
  if ("IntersectionObserver" in window) {
    document.documentElement.classList.add("js-reveal");
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.08 },
    );
    document
      .querySelectorAll(".reveal")
      .forEach((node) => observer.observe(node));
  }

  updateProgress();
}
