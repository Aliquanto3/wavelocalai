// Les trois étapes de l'évaluation (story 7.3, UX-DR11, UX-DR29) : « Recherche des extraits communs »
// (avec « Voir les extraits »), « Réponses » (une ligne par modèle) et « Notation ». L'état de chaque
// étape est dit en texte (à venir, en cours, fait, échec, arrêtée, non lancée), jamais par la seule
// couleur ni la seule icône. Les extraits sont ceux de l'événement `sources` (`wl-source-panel`) ; un
// jeu de questions choisit la question dont on lit les extraits.
//
//   const steps = stepsView(uid, nameOf);   steps.el   steps.render(model)   steps.reset()
//
// Un modèle en échec garde son `wl-error` : un `ram_guard` y trouve ses deux boutons (4.8).

import { element, icon } from "../core/dom.js";
import { t } from "../core/i18n.js";
import "../components/wl-error.js";
import "../components/wl-source-panel.js";

const STATE_ICON = {
  pending: "hourglass-empty",
  current: "sync",
  done: "check",
  failed: "error",
  stopped: "block",
  not_started: "hourglass-empty",
};

function stateBadge(state) {
  const node = element("span", "eval-step-state");
  node.dataset.state = state;
  node.append(icon(STATE_ICON[state] ?? "hourglass-empty"), element("span", "", t(`evaluation.steps.state.${state}`)));
  return node;
}

export function stepsView(uid, nameOf) {
  const title = element("h2", "eval-steps-title", t("evaluation.steps.title"));
  title.id = `${uid}-steps-title`;
  const list = element("ol", "eval-steps");
  list.setAttribute("aria-label", t("evaluation.steps.label"));

  // 1. Recherche
  const retrievalState = element("span", "eval-step-slot");
  const extractsButton = element("button", "btn eval-extracts-button", t("evaluation.steps.extracts"));
  extractsButton.type = "button";
  extractsButton.setAttribute("aria-expanded", "false");
  extractsButton.id = `${uid}-extracts-button`;
  extractsButton.hidden = true;
  const extractsRegion = element("div", "eval-extracts");
  extractsRegion.id = `${uid}-extracts`;
  extractsRegion.hidden = true;
  extractsButton.setAttribute("aria-controls", extractsRegion.id);
  const picker = element("select", "eval-extracts-select");
  picker.id = `${uid}-extracts-question`;
  const pickerLabel = element("label", "eval-extracts-label", t("evaluation.steps.extracts_question"));
  pickerLabel.htmlFor = picker.id;
  const pickerRow = element("p", "eval-extracts-row");
  pickerRow.append(pickerLabel, " ", picker);
  const panel = document.createElement("wl-source-panel");
  extractsRegion.append(pickerRow, panel);
  const retrievalItem = element("li", "eval-step");
  retrievalItem.dataset.step = "retrieval";
  retrievalItem.append(
    element("span", "eval-step-name", t("evaluation.steps.retrieval")),
    retrievalState,
    extractsButton,
    extractsRegion,
  );

  // 2. Réponses
  const answersState = element("span", "eval-step-slot");
  const lanesList = element("ul", "eval-lanes");
  const answersItem = element("li", "eval-step");
  answersItem.dataset.step = "answers";
  answersItem.append(element("span", "eval-step-name", t("evaluation.steps.answers")), answersState, lanesList);

  // 3. Notation
  const scoringState = element("span", "eval-step-slot");
  const scoringCount = element("span", "help eval-step-count");
  const scoringItem = element("li", "eval-step");
  scoringItem.dataset.step = "scoring";
  scoringItem.append(element("span", "eval-step-name", t("evaluation.steps.scoring")), scoringState, scoringCount);

  list.append(retrievalItem, answersItem, scoringItem);
  const el = element("section", "eval-steps-box");
  el.setAttribute("aria-labelledby", title.id);
  el.append(title, list);

  const laneItems = new Map(); // tag -> { li, signature }
  let shown = -1; // question dont le panneau montre les extraits
  let latest = null;

  function toggleExtracts(open) {
    extractsRegion.hidden = !open;
    extractsButton.setAttribute("aria-expanded", String(open));
    extractsButton.textContent = t(open ? "evaluation.steps.extracts_hide" : "evaluation.steps.extracts");
  }

  function showSources(index) {
    shown = index;
    const sources = latest?.state.sources.get(index) ?? [];
    if (!sources.length) panel.clear();
    else if (panel.sources !== sources) panel.sources = sources; // une même liste ne se redessine pas
  }

  function syncPicker(model) {
    const count = model.state.questions.length;
    pickerRow.hidden = count < 2;
    const wanted = Array.from({ length: count }, (_, index) => String(index));
    const have = [...picker.options].map((option) => option.value);
    if (wanted.join(",") !== have.join(",")) {
      picker.replaceChildren(
        ...wanted.map((value) => {
          const option = element("option", "", `${t("evaluation.detail.question", { n: Number(value) + 1 })} · ${model.state.questions[Number(value)]}`);
          option.value = value;
          return option;
        }),
      );
      picker.value = String(Math.max(shown, 0));
    }
  }

  extractsButton.addEventListener("click", () => {
    const open = extractsRegion.hidden;
    toggleExtracts(open);
    if (open && latest) showSources(Number(picker.value) || 0);
  });
  picker.addEventListener("change", () => showSources(Number(picker.value) || 0));

  function laneItem(lane) {
    const signature = `${lane.status}|${lane.error?.code ?? ""}|${lane.error?.message ?? ""}`;
    let entry = laneItems.get(lane.tag);
    if (entry && entry.signature === signature) {
      entry.name.textContent = nameOf(lane.tag);
      return entry.li;
    }
    const li = element("li", "eval-lane");
    li.dataset.lane = lane.tag;
    li.dataset.status = lane.status;
    const name = element("strong", "eval-lane-name", nameOf(lane.tag));
    li.append(name, " · ", element("span", "eval-lane-state", t(`evaluation.steps.lane.${lane.status}`, {})));
    if (lane.error) {
      const error = document.createElement("wl-error");
      error.error = lane.error;
      li.append(error);
    }
    entry = { li, signature, name };
    laneItems.set(lane.tag, entry);
    return li;
  }

  return {
    el,
    panel,
    // Les sources se lisent dans le modèle à l'ouverture : on les garde à jour tant qu'elles sont ouvertes.
    render(model) {
      latest = model;
      const view = model.steps();
      retrievalState.replaceChildren(stateBadge(view.retrieval));
      answersState.replaceChildren(stateBadge(view.answers));
      scoringState.replaceChildren(stateBadge(view.scoring));
      scoringCount.textContent =
        view.scoringTotal > 0 && view.scoring !== "pending"
          ? t("evaluation.steps.scoring_count", { done: view.scoringDone, total: view.scoringTotal })
          : "";
      extractsButton.hidden = model.state.sources.size === 0;
      syncPicker(model);
      if (!extractsRegion.hidden) showSources(Number(picker.value) || 0);
      lanesList.replaceChildren(...view.lanes.map(laneItem));
      for (const tag of [...laneItems.keys()]) if (!view.lanes.some((lane) => lane.tag === tag)) laneItems.delete(tag);
    },
    reset() {
      laneItems.clear();
      lanesList.replaceChildren();
      retrievalState.replaceChildren();
      answersState.replaceChildren();
      scoringState.replaceChildren();
      scoringCount.textContent = "";
      extractsButton.hidden = true;
      toggleExtracts(false);
      picker.replaceChildren();
      panel.clear();
      shown = -1;
      latest = null;
    },
  };
}
