// Thème et mode projection (UX-DR2). Réglages d'affichage du navigateur seulement : ils vont dans
// `localStorage` (avec les volets et les brouillons, AD-20), jamais au serveur. Chaque accès est
// gardé : sans stockage (fenêtre privée, données bloquées), le choix tient pour la page ouverte.
// Chargé en tête de page avec `blocking="render"` : `data-theme` est posé avant le premier rendu.
//
// Trois choix (D-7) : « Clair » (défaut), « Sombre » et « Système ». `data-theme` de `<html>` porte
// toujours le jeu de jetons appliqué (`light` ou `dark`) : « Système » n'a pas de troisième jeu, il
// choisit l'un des deux d'après `prefers-color-scheme` et le suit quand le système change, page
// ouverte. `data-theme-choice` porte le choix de la personne.

const THEME_KEY = "wl.theme";
const PROJECTION_KEY = "wl.projection";
const DARK_QUERY = "(prefers-color-scheme: dark)";
export const THEMES = ["light", "dark", "system"];

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

function systemMedia() {
  try {
    return matchMedia(DARK_QUERY);
  } catch {
    return null;
  }
}

// Le choix gardé (`light`, `dark` ou `system`), « Clair » faute de mieux.
export function getTheme() {
  const stored = read(THEME_KEY);
  return THEMES.includes(stored) ? stored : "light";
}

// Le jeu de jetons qu'un choix donne : `light` ou `dark`.
export function appliedTheme(choice) {
  if (choice === "system") return systemMedia()?.matches ? "dark" : "light";
  return choice === "dark" ? "dark" : "light";
}

let current = getTheme();

function apply() {
  document.documentElement.dataset.theme = appliedTheme(current);
  document.documentElement.dataset.themeChoice = current;
}

export function setTheme(theme) {
  current = THEMES.includes(theme) ? theme : "light";
  apply();
  write(THEME_KEY, current);
}

export function getProjection() {
  return read(PROJECTION_KEY) === "1";
}

export function setProjection(on) {
  document.documentElement.dataset.projection = on ? "true" : "false";
  write(PROJECTION_KEY, on ? "1" : "0");
}

// Réglages mémorisés, appliqués dès l'import ; « Système » suit les changements du système.
apply();
document.documentElement.dataset.projection = getProjection() ? "true" : "false";
systemMedia()?.addEventListener("change", () => {
  if (current === "system") apply();
});
