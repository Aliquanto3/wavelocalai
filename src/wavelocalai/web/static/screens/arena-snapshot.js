// Lecture de l'instantané d'une Arène terminée (story 3.6, AD-5, AD-20) : le verdict (3.5), les
// actions « Relancer » et « Modifier la question » (sa `config`) et le CO2 que le serveur a complété
// pour une lane arrêtée (3.4) en viennent. Le front ne calcule rien : il lit et il pose.

import { api } from "../core/api.js";

const ACTIVE = ["running", "awaiting_approval"]; // statuts non terminaux de l'instantané
const RETRIES = 20;
const RETRY_MS = 150;

// Le hub publie `run_ended` juste avant d'écrire le statut final en base : tant que l'instantané dit
// encore le run actif, il est relu (quelques fois, à intervalle court). Rend l'instantané réglé, ou
// `null` s'il n'a pas pu être lu, ou si `alive()` dit qu'une comparaison plus récente a pris la place.
export async function readSettled(runId, alive = () => true) {
  try {
    for (let attempt = 0; ; attempt += 1) {
      const snapshot = await api.run(runId);
      if (!alive()) return null;
      if (!ACTIVE.includes(snapshot?.status)) return snapshot;
      if (attempt >= RETRIES) return null;
      await new Promise((resolve) => setTimeout(resolve, RETRY_MS));
      if (!alive()) return null;
    }
  } catch {
    return null;
  }
}

const hasCo2 = (result) => typeof result?.co2?.mg === "number";

// Le CO2 d'une lane arrêtée ou interrompue : le serveur peut l'avoir complété en base après son
// dernier événement `metrics` (mesure faite jusqu'à l'arrêt). Les colonnes qui n'ont pas de CO2 chiffré
// reçoivent les mesures de l'instantané ; une lane déjà mesurée n'est jamais touchée. Rend le nombre de
// colonnes mises à jour.
export function applyLateMeasures(lanesEl, snapshot) {
  let updated = 0;
  for (const child of snapshot?.children ?? []) {
    if (child.kind !== "generation" || !hasCo2(child.metrics)) continue;
    const lane = [...lanesEl.querySelectorAll("wl-arena-lane")].find((el) => el.tag === child.model);
    if (!lane || hasCo2(lane.result)) continue;
    const { output_tokens: tokens = null, ...measures } = child.metrics;
    lane.metrics({ lane: child.model, ...measures, eval_tokens: tokens });
    updated += 1;
  }
  return updated;
}
