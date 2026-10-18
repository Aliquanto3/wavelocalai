// Écran à construire (agent-seul). Pour le maquetter, remplacez ce module en suivant CONVENTIONS.md :
// exporter mount(host, ctx) et scenarios, avec css/screens/agent-seul.css, i18n/screens/agent-seul.fr.json,
// donnees/agent-seul*.json, donnees/flux/agent-seul-*.json et notes/agent-seul.md.

import { mountPlaceholder } from "../core/placeholder.js";

export function mount(host, ctx) {
  return mountPlaceholder(host, ctx);
}

export const scenarios = [];
