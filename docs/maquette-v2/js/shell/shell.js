// Coquille (repris de static/core/shell.js) : menu des modules tiré de donnees/routes.json, menu
// repliable sous 1 024 px, menu Affichage (thème clair, sombre ou système ; projection), lien
// d'évitement. Dans le front définitif, les six modules sont disponibles : aucun n'est désactivé.

import { bindDisclosure } from "../core/disclosure.js";
import { element, icon } from "../core/dom.js";
import { THEMES, getProjection, getTheme, setProjection, setTheme } from "../core/theme.js";

const COLLAPSE_QUERY = "(min-width: 1024px)";

function moduleItem(module, routes) {
  const entry = routes.find((route) => route.slug === module.entry);
  const item = element("li", "module");
  const link = element("a", "module-link");
  link.dataset.module = module.id;
  link.href = `#${entry.path}`;
  link.append(icon(module.icon), element("span", "", module.label));
  item.append(link);
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
  nav.closest("header").addEventListener("keydown", (event) => {
    if (event.key === "Escape" && nav.dataset.open === "true" && !wide.matches) {
      event.preventDefault();
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
  const radios = [...panel.querySelectorAll('input[name="theme"]')];
  const sync = () => {
    for (const radio of radios) radio.checked = radio.value === getTheme();
  };
  for (const radio of radios) {
    radio.addEventListener("change", () => {
      if (radio.checked && THEMES.includes(radio.value)) setTheme(radio.value);
    });
  }
  const projection = panel.querySelector('input[name="projection"]');
  projection.addEventListener("change", () => setProjection(projection.checked));
  // Le panneau Scénarios change aussi ces réglages : le menu suit.
  document.addEventListener("wl-theme-change", sync);
  document.addEventListener("wl-projection-change", () => {
    projection.checked = getProjection();
  });
  sync();
  projection.checked = getProjection();
}

// Câble la coquille ; rend `setCurrent(route)`, qui marque le module courant (`aria-current`).
export function initShell({ modules, routes }) {
  const nav = document.getElementById("modules-nav");
  const list = document.getElementById("module-list");
  list.replaceChildren(...modules.map((module) => moduleItem(module, routes)));
  const closeMenu = setupModuleMenu(nav, document.getElementById("nav-toggle"), list);
  setupDisplayMenu();

  document.getElementById("skip-link").addEventListener("click", (event) => {
    event.preventDefault();
    document.getElementById("main").focus();
  });

  return function setCurrent(route) {
    for (const link of list.querySelectorAll("a[data-module]")) {
      if (link.dataset.module === route.module) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
    closeMenu();
  };
}

// Onglets d'un module (repris de feat/v2-ecran-chat, core/screen-tabs.js) : les routes du module qui
// portent un `tab`, dans l'ordre de donnees/routes.json ; l'écran courant a `aria-current="page"`.
export function screenTabs(routes, moduleId, currentSlug, label) {
  const nav = element("nav", "screen-tabs");
  nav.setAttribute("aria-label", label);
  const list = element("ul", "screen-tabs-list");
  for (const route of routes.filter((candidate) => candidate.module === moduleId && candidate.tab)) {
    const item = element("li", "screen-tab");
    const link = element("a", "screen-tab-link", route.tab);
    link.href = `#${route.path}`;
    if (route.slug === currentSlug || route.screen === currentSlug) link.setAttribute("aria-current", "page");
    item.append(link);
    list.append(item);
  }
  nav.append(list);
  return nav;
}
