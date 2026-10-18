// Écran à construire (base-documentaire). Pour le maquetter, remplacez ce module en suivant CONVENTIONS.md :
// exporter mount(host, ctx) et scenarios, avec css/screens/base-documentaire.css, i18n/screens/base-documentaire.fr.json,
// donnees/base-documentaire*.json, donnees/flux/base-documentaire-*.json et notes/base-documentaire.md.

import { mountPlaceholder } from "../core/placeholder.js";

export function mount(host, ctx) {
  return mountPlaceholder(host, ctx);
}

export const scenarios = [];
