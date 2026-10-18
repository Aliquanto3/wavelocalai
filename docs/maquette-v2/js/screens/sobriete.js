// Écran à construire (sobriete). Pour le maquetter, remplacez ce module en suivant CONVENTIONS.md :
// exporter mount(host, ctx) et scenarios, avec css/screens/sobriete.css, i18n/screens/sobriete.fr.json,
// donnees/sobriete*.json, donnees/flux/sobriete-*.json et notes/sobriete.md.

import { mountPlaceholder } from "../core/placeholder.js";

export function mount(host, ctx) {
  return mountPlaceholder(host, ctx);
}

export const scenarios = [];
