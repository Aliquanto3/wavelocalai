// Trois gestes sur le run suivi par l'Arène, sortis de `arena.js` (600 lignes au plus par fichier) :
//
//   showRunAddress(runId)   à la fin d'un run, l'adresse devient `#/arene/comparer/<run_id>` (écart
//                           n° 7), sans entrée d'historique de plus : un rechargement ou un lien
//                           rouvre cette comparaison (`arena-reopen.js`) ;
//   await stopFailure(id)   demande l'arrêt du run ; rend `null` si le serveur l'a pris, sinon le
//                           message à afficher ;
//   await stopLaneFailure(laneRunId)   arrête une seule lane (story 9.2, « Arrêter ce modèle ») ; sa
//                           réponse partielle est gardée et notée, à la différence de `stopFailure`
//                           ci-dessus qui arrête toute l'Arène sans rien noter. Même rendu.

import { api, ApiError } from "../core/api.js";
import { t } from "../core/i18n.js";
import { replaceAddress } from "../core/router.js";

const BASE = "#/arene/comparer";

// Jamais sur un autre écran (l'Arène reste montée en arrière-plan), ni si l'adresse est déjà la bonne.
export function showRunAddress(runId) {
  if (!runId) return;
  const target = `${BASE}/${encodeURIComponent(runId)}`;
  const here = location.hash;
  if (here === target || (here !== BASE && !here.startsWith(`${BASE}/`))) return;
  replaceAddress(target); // `history.replaceState`, clé du routeur accordée : rien n'est remonté
}

export async function stopFailure(id) {
  try {
    await api.cancelRun(id);
    return null;
  } catch (failure) {
    return failure instanceof ApiError && failure.envelope
      ? failure.envelope.message
      : t("components.run_status.cancel_failed");
  }
}

export async function stopLaneFailure(laneRunId) {
  try {
    await api.stopLane(laneRunId);
    return null;
  } catch (failure) {
    return failure instanceof ApiError && failure.envelope
      ? failure.envelope.message
      : t("components.run_status.cancel_failed");
  }
}
