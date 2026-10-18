// Brouillons de saisie (AD-20) : le texte tapé et pas encore envoyé survit à un rechargement, dans
// `localStorage` seulement (jamais la bascule cloud, qui vit dans le store). Le stockage peut être
// absent ou refusé (fenêtre privée, données bloquées) : chaque accès est protégé, l'écran marche sans.

const PREFIX = "wavelocalai.draft.";

export function loadDraft(name) {
  try {
    return localStorage.getItem(PREFIX + name) ?? "";
  } catch {
    return "";
  }
}

// Un brouillon vide est effacé plutôt que gardé.
export function saveDraft(name, value) {
  try {
    if (value) localStorage.setItem(PREFIX + name, value);
    else localStorage.removeItem(PREFIX + name);
  } catch {
    // Pas de stockage : le brouillon reste dans le champ, c'est tout.
  }
}
