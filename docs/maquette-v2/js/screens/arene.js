// Écran à construire (arene). Pour le maquetter, remplacez ce module en suivant CONVENTIONS.md :
// exporter mount(host, ctx) et scenarios, avec css/screens/arene.css, i18n/screens/arene.fr.json,
// donnees/arene*.json, donnees/flux/arene-*.json et notes/arene.md.

import { mountPlaceholder } from "../core/placeholder.js";

export function mount(host, ctx) {
  return mountPlaceholder(host, ctx);
}

export const scenarios = [];
