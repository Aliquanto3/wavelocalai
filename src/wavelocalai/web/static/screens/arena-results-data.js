// Résultats de l'Arène (story 3.4) : les calculs d'affichage du classement, de la matrice et du
// tableau, sans DOM. Le front ne calcule aucune mesure (AD-20) : il ordonne les notes du juge, choisit
// l'unité commune du CO2 et met en texte ce que le serveur a publié.
//
// Une « lane » ici est ce que `screens/arena-results.js` lit sur chaque colonne :
//   { tag, name, origin, status, score: { score, reason } | null, result: <événement `metrics`> | null }
// Un inconnu n'est jamais un 0 : « non évalué » (note), « non mesurable » (CO2 que le serveur n'a pas
// pu mesurer), « non mesuré » (aucune mesure publiée : délai, échec, arrêt), « en cours ».

import { co2Group, formatDuration, formatRate, formatScore } from "../core/format.js";
import { t } from "../core/i18n.js";
import { reasonText } from "../components/wl-arena-lane.js";

// Statuts de lane qui ne changeront plus (`done` compris : sa note est alors arrivée).
export const SETTLED = new Set(["done", "timeout", "failed", "cancelled", "interrupted"]);
const NO_SCORE_STATUS = new Set(["timeout", "failed", "cancelled", "interrupted"]);

export const isScored = (lane) => typeof lane.score?.score === "number";

// Lanes notées, de la meilleure à la moins bonne ; à note égale, l'ordre de lancement (stable).
// `rank` : rang à égalité (1, 1, 3) ; `tied` : une autre lane a la même note.
export function rankLanes(lanes) {
  const scored = lanes.filter(isScored).sort((a, b) => b.score.score - a.score.score);
  return scored.map((lane, index) => {
    const first = scored.findIndex((other) => other.score.score === lane.score.score);
    const tied = scored.filter((other) => other.score.score === lane.score.score).length > 1;
    return { lane, rank: first + 1, tied, index };
  });
}

// Lanes sans note qui n'en auront plus (juge sans note, statut final, ou comparaison terminée),
// dans l'ordre de lancement ; les autres sont « pas encore notées ».
export function splitUnscored(lanes, ended) {
  const unscored = lanes.filter((lane) => !isScored(lane));
  const settled = unscored.filter((lane) => ended || SETTLED.has(lane.status));
  return { settled, pending: unscored.filter((lane) => !settled.includes(lane)) };
}

// La raison d'un « non évalué », sans le préfixe ni la majuscule : « réponse vide », « délai dépassé ».
export function notEvaluatedReason(lane) {
  if (lane.score) {
    const reason = reasonText(lane.score.reason);
    if (reason) return reason[0].toLocaleLowerCase("fr-FR") + reason.slice(1);
  }
  if (NO_SCORE_STATUS.has(lane.status)) return t(`components.lane.not_evaluated_status.${lane.status}`);
  return t("arena.results.reason_unknown");
}

// « Non évalué : réponse vide » (classement), « non évalué : réponse vide » (cellule du tableau).
export const notEvaluatedLine = (lane) => t("arena.results.not_evaluated_line", { reason: notEvaluatedReason(lane) });
export const notEvaluatedCell = (lane) => t("arena.results.not_evaluated_cell", { reason: notEvaluatedReason(lane) });

// Absence de mesure : « en cours » tant que la lane n'a pas fini, « non mesuré » ensuite.
const noMeasure = (lane, ended) =>
  ended || SETTLED.has(lane.status) ? t("arena.results.not_measured") : t("arena.results.in_progress");

// L'unité commune du CO2 de la comparaison (celle du plus grand CO2 mesuré), AD-10 : toutes les
// valeurs de l'écran (classement, tableau, légende de taille) la partagent.
export function co2GroupOf(lanes) {
  return co2Group(lanes.map((lane) => lane.result?.co2?.mg).filter((mg) => typeof mg === "number"));
}

export function co2Text(lane, group, ended) {
  const co2 = lane.result?.co2;
  if (!lane.result) return noMeasure(lane, ended);
  if (typeof co2?.mg !== "number") return t("components.thread.co2_unmeasurable");
  const value = group.format(co2.mg);
  return co2.estimated ? t("components.thread.co2_estimated", { value }) : value;
}

export function rateText(lane, ended) {
  return typeof lane.result?.tps === "number" ? formatRate(lane.result.tps) : noMeasure(lane, ended);
}

export function loadText(lane, ended) {
  if (lane.origin === "cloud") return t("arena.chart.not_applicable");
  return typeof lane.result?.load_s === "number" ? formatDuration(lane.result.load_s) : noMeasure(lane, ended);
}

export function totalText(lane, ended) {
  return typeof lane.result?.total_s === "number" ? formatDuration(lane.result.total_s) : noMeasure(lane, ended);
}

export const scoreText = (lane) => (isScored(lane) ? formatScore(lane.score.score) : "");

// Les lanes que la matrice peut placer : une note ET un débit. Les autres sont dites « non placées ».
export function splitPlotted(lanes) {
  const plotted = lanes.filter((lane) => isScored(lane) && typeof lane.result?.tps === "number");
  return { plotted, missing: lanes.filter((lane) => !plotted.includes(lane)) };
}
