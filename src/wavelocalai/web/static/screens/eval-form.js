// Formulaire de l'évaluation (story 7.3, UX-DR29, D-27, D-29) : « Question » ou « Jeu de questions »
// (une question par ligne, 20 au plus), `wl-model-picker` multi sur le défaut `arena` (D-27), juge sur
// le défaut `judge` avec sa raison (donnée par le sélecteur) et l'avertissement « note peu fiable »,
// puis « Lancer l'évaluation », désactivé avec sa raison visible reliée au bouton.
//
//   const form = formView(uid);   form.el  form.questions()  form.models()  form.reason()
//
// Le front ne décide rien du juge : il envoie le choix du sélecteur (absent, le serveur prend son
// défaut) ; la fiabilité réelle vient de l'événement `judge` (`eval-summary`, `documents-eval.js`).

import { ApiError } from "../core/api.js";
import { element } from "../core/dom.js";
import { loadDraft, saveDraft } from "../core/drafts.js";
import { t } from "../core/i18n.js";
import { store } from "../core/store.js";
import { segments } from "../components/segments.js";

export const MIN_MODELS = 1;
export const MAX_MODELS = 4;
export const MAX_QUESTIONS = 20;
const DRAFT_ONE = "evaluation";
const DRAFT_SET = "evaluation-set";

// Un échec de l'API : son enveloppe (AD-18), sinon un message de lancement impossible.
export function envelopeOf(error) {
  if (error instanceof ApiError && error.envelope) return error.envelope;
  return { code: "internal", message: t("evaluation.start_failed") };
}

// Les questions d'un champ : une par ligne, sans lignes vides.
export const splitQuestions = (text) =>
  String(text)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

function field(uid, name, rows, draft) {
  const input = element("textarea", "chat-input eval-question");
  input.id = `${uid}-${name}`;
  input.rows = rows;
  input.value = loadDraft(draft);
  input.addEventListener("input", () => saveDraft(draft, input.value));
  return input;
}

export function formView(uid) {
  let mode = "question";
  let baseDocuments = null; // nombre de documents prêts, ou null tant que la base n'est pas lue
  let isBusy = () => false;

  const one = field(uid, "question", 3, DRAFT_ONE);
  const oneLabel = element("label", "chat-input-label", t("evaluation.question"));
  oneLabel.htmlFor = one.id;
  const many = field(uid, "set", 7, DRAFT_SET);
  const manyLabel = element("label", "chat-input-label", t("evaluation.set_label"));
  manyLabel.htmlFor = many.id;
  const manyHelp = element("p", "help", t("evaluation.set_help"));
  many.setAttribute("aria-describedby", (manyHelp.id = `${uid}-set-help`));
  const oneBox = element("div", "eval-field");
  oneBox.append(oneLabel, one);
  const manyBox = element("div", "eval-field");
  manyBox.append(manyLabel, many, manyHelp);
  manyBox.hidden = true;

  const seg = segments({
    label: t("evaluation.mode_label"),
    options: [
      { value: "question", label: t("evaluation.mode_question") },
      { value: "set", label: t("evaluation.mode_set") },
    ],
    value: mode,
    onChange: (value) => {
      mode = value;
      oneBox.hidden = value !== "question";
      manyBox.hidden = value !== "set";
      el.dispatchEvent(new CustomEvent("wl-eval-change", { bubbles: true }));
    },
  });

  const picker = document.createElement("wl-model-picker");
  picker.setAttribute("purpose", "arena");
  picker.setAttribute("multi", "");
  picker.setAttribute("label", t("evaluation.models"));
  const extracts = element("p", "help", t("evaluation.same_extracts"));
  const execution = element("p", "help eval-execution", t("evaluation.execution"));

  const judge = document.createElement("wl-model-picker");
  judge.setAttribute("purpose", "judge");
  judge.setAttribute("label", t("evaluation.judge_label"));
  const judgeHelp = element("p", "help", t("evaluation.judge_help"));
  const cloudNote = element("p", "eval-cloud-note", t("evaluation.cloud_note"));
  cloudNote.hidden = true;

  const launch = element("button", "btn eval-launch", t("evaluation.launch"));
  launch.type = "submit";
  launch.setAttribute("aria-describedby", `${uid}-reason`);
  const reasonText = element("span", "");
  const baseLink = element("a", "eval-base-link", t("evaluation.base_link"));
  baseLink.href = "#/documents/base";
  baseLink.hidden = true;
  const reason = element("p", "help eval-reason");
  reason.id = `${uid}-reason`;
  reason.append(reasonText, " ", baseLink);
  const actions = element("div", "chat-actions eval-actions");
  actions.append(launch, reason);

  const el = element("form", "eval-form");
  el.append(seg.root, oneBox, manyBox, picker, extracts, execution, judge, judgeHelp, cloudNote, actions);

  const questions = () => splitQuestions(mode === "set" ? many.value : one.value);
  const judgeReady = () => {
    const fiche = judge.value ? judge.modelFor(judge.value) : null;
    if (!judge.value || fiche?.available === false) return false;
    return fiche?.origin !== "cloud" || store.get().allowCloud;
  };
  const availableChoices = () => picker.values.filter((tag) => picker.modelFor(tag)?.available !== false).length;

  // La première raison qui empêche de lancer (vide : on peut lancer).
  function launchReason() {
    const asked = questions();
    const checks = [
      [isBusy() ? t("evaluation.busy") : "", false],
      [baseDocuments === 0 ? t("evaluation.need_base") : "", true],
      [
        picker.localReadyCount === 0 && !store.get().allowCloud && availableChoices() < MIN_MODELS
          ? t("evaluation.no_local_reason")
          : "",
        false,
      ],
      [picker.values.length < MIN_MODELS ? t("evaluation.need_models") : "", false],
      [picker.values.length > MAX_MODELS ? t("evaluation.too_many") : "", false],
      [asked.length === 0 ? t("evaluation.need_question") : "", false],
      [asked.length > MAX_QUESTIONS ? t("evaluation.too_many_questions") : "", false],
      [judgeReady() ? "" : t("evaluation.need_judge"), false],
    ];
    const found = checks.find(([text]) => text);
    return found ? { text: found[0], link: found[1] } : { text: "", link: false };
  }

  function refresh() {
    const why = launchReason();
    launch.disabled = why.text !== "";
    reasonText.textContent = why.text;
    baseLink.hidden = !why.link;
    reason.hidden = why.text === "";
    const cloud = [...picker.values, judge.value].some((tag) => tag && (picker.modelFor(tag) ?? judge.modelFor(tag))?.origin === "cloud");
    cloudNote.hidden = !cloud;
    return why.text;
  }

  return {
    el,
    picker,
    judge,
    launch,
    refresh,
    reason: () => launchReason().text,
    questions,
    models: () => picker.values,
    chosenJudge() {
      const fiche = judge.value ? judge.modelFor(judge.value) : null;
      return judge.value ? { tag: judge.value, name: fiche?.name ?? judge.value, origin: fiche?.origin } : null;
    },
    setBusy(fn) {
      isBusy = fn;
    },
    // Le nombre de documents prêts de la base (`totals.documents`), ou `null` si on ne l'a pas lu.
    setBase(count) {
      baseDocuments = typeof count === "number" ? count : null;
      refresh();
    },
    focusQuestion() {
      (mode === "set" ? many : one).focus();
    },
  };
}
