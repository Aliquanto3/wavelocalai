// Thème et mode projection (UX-DR2). Réglages d'affichage du navigateur seulement : ils vont dans
// `localStorage` (avec les volets et les brouillons, AD-20), jamais au serveur. Chaque accès est
// gardé : sans stockage (fenêtre privée, données bloquées), le choix tient pour la page ouverte.
// Chargé en tête de page avec `blocking="render"` : `data-theme` est posé avant le premier rendu.

const THEME_KEY = "wl.theme";
const PROJECTION_KEY = "wl.projection";
export const THEMES = ["light", "dark"];

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

export function getTheme() {
  const stored = read(THEME_KEY);
  return THEMES.includes(stored) ? stored : "light";
}

export function setTheme(theme) {
  const value = THEMES.includes(theme) ? theme : "light";
  document.documentElement.dataset.theme = value;
  write(THEME_KEY, value);
}

export function getProjection() {
  return read(PROJECTION_KEY) === "1";
}

export function setProjection(on) {
  document.documentElement.dataset.projection = on ? "true" : "false";
  write(PROJECTION_KEY, on ? "1" : "0");
}

// Réglages mémorisés, appliqués dès l'import.
document.documentElement.dataset.theme = getTheme();
document.documentElement.dataset.projection = getProjection() ? "true" : "false";
