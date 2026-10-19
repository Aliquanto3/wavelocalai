// Éléments du formulaire de l'Arène, extraits de `arena.js` (plafond de taille des fichiers du front).

import { ApiError } from "../core/api.js";
import { element, icon } from "../core/dom.js";
import { saveDraft } from "../core/drafts.js";
import { t } from "../core/i18n.js";
import { store } from "../core/store.js";

export const SCENARIOS = ["popularize", "extract", "summarize", "translate"];
const MIN_MODELS = 2;
const MAX_MODELS = 4;

// Un échec de l'API : son enveloppe (AD-18), sinon un message de lancement impossible.
export function envelopeOf(error) {
  if (error instanceof ApiError && error.envelope) return error.envelope;
  return { code: "internal", message: t("arena.start_failed") };
}

// Le premier prérequis du lancement qui manque, en texte (vide : on peut lancer). `busy()` dit qu'une
// comparaison est en cours ou en cours d'envoi. La première raison l'emporte.
export function launchReasonOf({ busy, picker, question, judging }) {
  const availableChoices = () =>
    picker.values.filter((tag) => picker.modelFor(tag)?.available !== false).length;
  const checks = [
    () => (busy() ? t("arena.busy") : ""),
    () =>
      picker.localReadyCount === 0 && !store.get().allowCloud && availableChoices() < MIN_MODELS
        ? t("arena.no_local_reason")
        : "",
    () => (picker.values.length < MIN_MODELS ? t("arena.need_models") : ""),
    () => (picker.values.length > MAX_MODELS ? t("arena.too_many") : ""),
    () => (question.value.trim() ? "" : t("arena.need_question")),
    () => (judging.ready() ? "" : t("arena.judge.need_judge")),
  ];
  return () => {
    for (const check of checks) {
      const why = check();
      if (why) return why;
    }
    return "";
  };
}

// Les scénarios d'exemple : un clic remplace la question (et son brouillon), puis rend le focus.
export function scenarioFieldset(question, draft, onPick) {
  const scenarios = element("fieldset", "arena-scenarios");
  scenarios.append(element("legend", "", t("arena.scenarios")));
  const row = element("div", "arena-scenario-row");
  for (const id of SCENARIOS) {
    const button = element("button", "btn", t(`arena.scenario.${id}.label`));
    button.type = "button";
    button.addEventListener("click", () => {
      question.value = t(`arena.scenario.${id}.prompt`);
      saveDraft(draft, question.value);
      onPick();
      question.focus();
    });
    row.append(button);
  }
  scenarios.append(row, element("p", "help", t("arena.scenarios_help")));
  return scenarios;
}

// Sans modèle local prêt (D-11) : `alert-info` qui dit quoi faire, au-dessus du formulaire.
export function noLocalNotice() {
  const el = element("p", "wl-notice wl-notice-info");
  el.setAttribute("role", "status");
  const text = element("span", "");
  el.append(icon("info"), text); // masqué ou non par l'écran, dès le montage
  return { el, text };
}
