// Éléments du formulaire de l'Arène, extraits de `arena.js` (plafond de taille des fichiers du front).

import { ApiError } from "../core/api.js";
import { element, icon } from "../core/dom.js";
import { loadDraft, saveDraft } from "../core/drafts.js";
import { t } from "../core/i18n.js";
import { store } from "../core/store.js";
import { judgePanel } from "./arena-judge.js";

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

// Une comparaison effacée (AD-13) : sa question ne reste ni dans le champ ni dans le brouillon
// (`localStorage`). Un autre texte, tapé depuis, est gardé.
export function forgetErased(question, prompt) {
  if (!prompt || question.value !== prompt) return;
  question.value = "";
  question.dispatchEvent(new Event("input")); // brouillon effacé, raison du lancement recalculée
}

// Construit le formulaire : question et modèles à gauche, notation et lancement à droite (story 9.7,
// grille à deux colonnes dès 1400px, `.two-col`/`.col-right` de base.css).
export function buildForm(uid, draft, onRender) {
  const questionLabel = element("label", "chat-input-label field-label", t("arena.question"));
  const question = element("textarea", "chat-input arena-question");
  question.id = `${uid}-question`;
  question.rows = 3;
  questionLabel.htmlFor = question.id;
  question.value = loadDraft(draft) || t("arena.scenario.popularize.prompt");
  const scenarios = scenarioFieldset(question, draft, onRender);
  const picker = document.createElement("wl-model-picker");
  picker.setAttribute("purpose", "arena");
  picker.setAttribute("multi", "");
  picker.setAttribute("label", t("arena.models"));
  const execution = element("p", "help arena-execution", t("arena.execution"));
  const judging = judgePanel(uid);
  const launch = element("button", "btn arena-launch", t("arena.launch"));
  launch.type = "submit";
  launch.setAttribute("aria-describedby", `${uid}-reason`);
  const reason = element("p", "help arena-reason");
  reason.id = `${uid}-reason`;
  const actions = element("div", "chat-actions arena-actions");
  actions.append(launch, reason);
  const form = element("form", "arena-form two-col");
  const left = element("div", "stack");
  left.append(questionLabel, question, scenarios, picker);
  const right = element("div", "col-right");
  right.append(judging.el, execution, actions);
  form.append(left, right);
  return { form, question, scenarios, picker, execution, judging, launch, reason, actions };
}
