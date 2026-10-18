// Écran à construire (banc-essai). Pour le maquetter, remplacez ce module en suivant CONVENTIONS.md :
// exporter mount(host, ctx) et scenarios, avec css/screens/banc-essai.css, i18n/screens/banc-essai.fr.json,
// donnees/banc-essai*.json, donnees/flux/banc-essai-*.json et notes/banc-essai.md.

import { mountPlaceholder } from "../core/placeholder.js";

export function mount(host, ctx) {
  return mountPlaceholder(host, ctx);
}

export const scenarios = [];
