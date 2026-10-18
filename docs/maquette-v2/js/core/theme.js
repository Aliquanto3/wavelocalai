// Thème et mode projection (repris de static/core/theme.js, UX-DR2). Ajout de la maquette : le
// choix « Système » suit `prefers-color-scheme` (écart noté dans notes/coquille.md). Le réglage
// va dans `localStorage` ; `data-theme` reçoit toujours le thème résolu (`light` ou `dark`), que
// tokens.css lit. Le script inline d'index.html pose les mêmes attributs avant le premier rendu.

const THEME_KEY = "wl.theme";
const PROJECTION_KEY = "wl.projection";
export const THEMES = ["light", "dark", "system"];
const DARK_QUERY = matchMedia("(prefers-color-scheme: dark)");

function read(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Pas de stockage : le choix vaut pour cette page seulement.
  }
}

let current = THEMES.includes(read(THEME_KEY)) ? read(THEME_KEY) : "light";

export function resolvedTheme(theme = current) {
  if (theme === "system") return DARK_QUERY.matches ? "dark" : "light";
  return theme;
}

function apply() {
  document.documentElement.dataset.theme = resolvedTheme();
  document.documentElement.dataset.themeChoice = current;
}

export function getTheme() {
  return current;
}

export function setTheme(theme) {
  current = THEMES.includes(theme) ? theme : "light";
  write(THEME_KEY, current);
  apply();
  document.dispatchEvent(new CustomEvent("wl-theme-change", { detail: { theme: current } }));
}

export function getProjection() {
  return document.documentElement.dataset.projection === "true";
}

export function setProjection(on) {
  document.documentElement.dataset.projection = on ? "true" : "false";
  write(PROJECTION_KEY, on ? "1" : "0");
  document.dispatchEvent(new CustomEvent("wl-projection-change", { detail: { on } }));
}

DARK_QUERY.addEventListener("change", () => {
  if (current === "system") apply();
});

apply();
document.documentElement.dataset.projection = read(PROJECTION_KEY) === "1" ? "true" : "false";
