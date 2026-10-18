// Écran à construire (references). Pour le maquetter, remplacez ce module en suivant CONVENTIONS.md :
// exporter mount(host, ctx) et scenarios, avec css/screens/references.css, i18n/screens/references.fr.json,
// donnees/references*.json, donnees/flux/references-*.json et notes/references.md.

import { mountPlaceholder } from "../core/placeholder.js";

export function mount(host, ctx) {
  return mountPlaceholder(host, ctx);
}

export const scenarios = [];
