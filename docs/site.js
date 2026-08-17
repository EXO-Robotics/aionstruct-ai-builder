const header = document.querySelector("[data-header]");
const parallax = document.querySelector("[data-parallax]");
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const updateHeader = () => header?.classList.toggle("is-scrolled", window.scrollY > 24);
updateHeader();
window.addEventListener("scroll", updateHeader, { passive: true });

if (!reduceMotion && parallax) {
  window.addEventListener(
    "scroll",
    () => {
      const offset = Math.min(window.scrollY * 0.085, 76);
      parallax.style.transform = `translate3d(0, ${offset}px, 0)`;
    },
    { passive: true },
  );
}

const revealObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-visible");
        revealObserver.unobserve(entry.target);
      }
    });
  },
  { threshold: 0.12 },
);

document.querySelectorAll(".reveal").forEach((element) => revealObserver.observe(element));

document.querySelectorAll("[data-gallery]").forEach((gallery) => {
  const image = gallery.querySelector(".gallery-image");
  const label = gallery.querySelector("[data-gallery-label]");
  const buttons = [...gallery.querySelectorAll("[data-image]")];

  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      if (button.classList.contains("is-active")) return;

      buttons.forEach((candidate) => {
        candidate.classList.remove("is-active");
        candidate.setAttribute("aria-pressed", "false");
      });
      button.classList.add("is-active");
      button.setAttribute("aria-pressed", "true");
      image.classList.add("is-switching");

      window.setTimeout(() => {
        image.src = button.dataset.image;
        image.alt = `${gallery.dataset.gallery} ${button.textContent.trim().toLowerCase()} engineering preview`;
        label.textContent = button.dataset.label;
        image.classList.remove("is-switching");
      }, reduceMotion ? 0 : 160);
    });
  });
});

const copyButton = document.querySelector("[data-copy]");
copyButton?.addEventListener("click", async () => {
  const commands = [
    "codex plugin marketplace add EXO-Robotics/aionstruct-ai-builder --ref main",
    "codex plugin add aionstruct-ai-builder@aionstruct",
  ].join("\n");

  try {
    await navigator.clipboard.writeText(commands);
    copyButton.textContent = "Copied";
    window.setTimeout(() => (copyButton.textContent = "Copy commands"), 1600);
  } catch {
    copyButton.textContent = "Select text above";
  }
});
