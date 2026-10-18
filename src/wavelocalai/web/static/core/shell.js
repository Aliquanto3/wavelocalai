// Coquille : barre haute (menu des modules, menu repliable sous 1 024 px, menu Affichage) et lien
// d'évitement. Le HTML porte la structure ; ce module y met la liste des modules, tirée du
// registre, et câble les interactions. Rien ici n'appelle `/api/` : la coquille se rend seule.

import { MODULES, entryScreen } from "./registry.js";
import { t } from "./i18n.js";
import { THEMES, getProjection, getTheme, setProjection, setTheme } from "./theme.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const COLLAPSE_QUERY = "(min-width: 1024px)";

function icon(name) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", `/static/icons.svg#i-${name}`);
  svg.append(use);
  return svg;
}

// Un module disponible est un lien ; un module à venir est un `<a>` sans `href`, `aria-disabled`,
// focalisable, dont la raison est un texte visible relié par `aria-describedby`.
function moduleItem(module) {
  const item = document.createElement("li");
  item.className = "module";
  const link = document.createElement("a");
  link.className = "module-link";
  link.dataset.module = module.id;
  const label = document.createElement("span");
  label.textContent = t(`modules.${module.id}`);
  link.append(icon(module.icon), label);
  item.append(link);

  const entry = entryScreen(module);
  if (entry) {
    link.setAttribute("href", `#${entry.path}`);
  } else {
    const reason = document.createElement("span");
    reason.className = "module-reason";
    reason.id = `reason-${module.id}`;
    reason.textContent = t("router.planned");
    link.setAttribute("role", "link");
    link.setAttribute("aria-disabled", "true");
    link.setAttribute("tabindex", "0");
    link.setAttribute("aria-describedby", reason.id);
    link.addEventListener("click", (event) => event.preventDefault());
    item.append(reason);
  }
  return item;
}

function setupModuleMenu(nav, toggle, list) {
  const wide = matchMedia(COLLAPSE_QUERY);
  const setOpen = (open) => {
    nav.dataset.open = open ? "true" : "false";
    toggle.setAttribute("aria-expanded", String(open));
  };
  setOpen(false);
  toggle.addEventListener("click", () => setOpen(nav.dataset.open !== "true"));
  // Échap ferme le menu où que soit le focus dans la barre haute (le bouton est hors du `nav`).
  nav.closest("header").addEventListener("keydown", (event) => {
    if (event.key === "Escape" && nav.dataset.open === "true" && !wide.matches) {
      setOpen(false);
      toggle.focus();
    }
  });
  wide.addEventListener("change", () => setOpen(false));
  list.addEventListener("click", (event) => {
    if (event.target.closest("a[href]")) setOpen(false);
  });
  return () => setOpen(false);
}

function setupDisplayMenu() {
  const button = document.getElementById("display-button");
  const panel = document.getElementById("display-panel");
  const setOpen = (open) => {
    panel.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
  };
  setOpen(false);
  button.addEventListener("click", () => setOpen(panel.hidden));
  document.addEventListener("pointerdown", (event) => {
    if (!panel.hidden && !event.target.closest(".topbar-tools")) setOpen(false);
  });
  panel.addEventListener("focusout", (event) => {
    if (!panel.hidden && event.relatedTarget && !event.relatedTarget.closest(".topbar-tools")) {
      setOpen(false);
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) {
      setOpen(false);
      button.focus();
    }
  });

  const current = getTheme();
  for (const radio of panel.querySelectorAll('input[name="theme"]')) {
    radio.checked = radio.value === current;
    radio.addEventListener("change", () => {
      if (radio.checked && THEMES.includes(radio.value)) setTheme(radio.value);
    });
  }
  const projection = panel.querySelector('input[name="projection"]');
  projection.checked = getProjection();
  projection.addEventListener("change", () => setProjection(projection.checked));
}

// Câble la coquille ; rend `setCurrent(screen)`, qui marque le module courant (`aria-current`).
export function initShell() {
  const nav = document.getElementById("modules-nav");
  const list = document.getElementById("module-list");
  list.replaceChildren(...MODULES.map(moduleItem));
  const closeMenu = setupModuleMenu(nav, document.getElementById("nav-toggle"), list);
  setupDisplayMenu();

  // Le lien d'évitement ne change pas le hash : il appartient au routeur.
  document.getElementById("skip-link").addEventListener("click", (event) => {
    event.preventDefault();
    document.getElementById("main").focus();
  });

  return function setCurrent(screen) {
    for (const link of list.querySelectorAll("a[data-module]")) {
      if (link.dataset.module === screen.module) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
    closeMenu();
  };
}
