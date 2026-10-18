// Coquille : barre haute (menu des modules, menu repliable sous 1 024 px, menu Affichage) et lien
// d'évitement. Le HTML porte la structure ; ce module y met la liste des modules, tirée du
// registre, et câble les interactions. Rien ici n'appelle `/api/` : la coquille se rend seule.

import { MODULES, entryScreen } from "./registry.js";
import { bindDisclosure } from "./disclosure.js";
import { icon } from "./dom.js";
import { t } from "./i18n.js";
import { THEMES, getProjection, getTheme, setProjection, setTheme } from "./theme.js";

const COLLAPSE_QUERY = "(min-width: 1024px)";

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
  bindDisclosure({ button, panel, scope: document.getElementById("display-tool") });

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
