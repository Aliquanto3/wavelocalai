// Enveloppes d'erreur de la maquette (AD-18) : `{code, message, action, detail, buttons}` tirées de
// donnees/erreurs.json. `buttons` est propre à la maquette : le vrai front tire les boutons du code et
// de `detail`. Le catalogue est chargé une fois au démarrage (main.js) ; ensuite tout est synchrone.

import { loadData } from "./data.js";
import { formatDuration, formatGb } from "./format.js";
import { store } from "./store.js";

let catalog = {};

export async function loadErrors() {
  catalog = (await loadData("erreurs.json")).codes;
}

export function errorCodes({ uxDr16Only = false } = {}) {
  return Object.entries(catalog)
    .filter(([, spec]) => !uxDr16Only || spec.ux_dr16)
    .map(([code]) => code);
}

export function errorSpec(code) {
  return catalog[code] ?? null;
}

// Valeurs lisibles tirées de `detail` (clés machine) : Go, durées, nom du modèle proposé.
function defaultVars(detail) {
  const vars = { ...detail };
  if (typeof detail.needed_gb === "number") vars.needed = formatGb(detail.needed_gb);
  if (typeof detail.free_gb === "number") vars.free = formatGb(detail.free_gb);
  if (detail.suggested_model) vars.suggested = detail.suggested_model;
  if (typeof detail.timeout_s === "number") vars.timeout = formatDuration(detail.timeout_s);
  return vars;
}

function fill(text, vars) {
  return String(text ?? "").replace(/\{(\w+)\}/g, (match, name) => (name in vars ? String(vars[name]) : match));
}

// L'enveloppe d'un code. `detail` remplace l'exemple du catalogue (fusion) ; `vars` complète les
// valeurs à insérer dans les textes. Code inconnu : enveloppe `internal`.
export function errorEnvelope(code, { detail = {}, vars = {} } = {}) {
  const spec = catalog[code] ?? catalog.internal;
  const merged = { ...(spec.detail_example ?? {}), ...detail };
  const values = { ...defaultVars(merged), ...vars };
  const cloudAware = code === "ollama_down" && store.get().allowCloud && spec.action_cloud;
  return {
    code: catalog[code] ? code : "internal",
    message: fill(spec.message, values),
    action: fill(cloudAware ? spec.action_cloud : spec.action, values),
    detail: merged,
    buttons: (spec.buttons ?? []).map((button) => ({ ...button })),
  };
}
