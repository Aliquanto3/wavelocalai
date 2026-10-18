// Évaluation de la qualité, `#/documents/evaluation[/<run_id>]` (UX-DR11, UX-DR13, UX-DR14, UX-DR17,
// UX-DR29, stories 7.1 à 7.3) : écran de l'Assistant documentaire, à l'état livré. Deux routes, un
// module : sans `run_id`, le formulaire et le run ; avec `run_id`, le résultat conservé, rouvert sans
// relancer de modèle.
//
// - Réglages : segments « Question » · « Jeu de questions », modèles évalués (`wl-model-picker`
//   multi, 4 au plus), juge (défaut `judge` et sa raison, « note peu fiable » sous ~4B actifs),
//   « Les mêmes extraits sont fournis à tous les modèles. », « Lancer l'évaluation » désactivé avec la
//   raison (base vide, aucun modèle, question vide).
// - Étapes nommées (« Recherche des extraits communs » + « Voir les extraits », « Réponses » par
//   modèle, « Notation : fidélité · pertinence · précision du contexte »), états en texte.
// - Résultats : tableau (fidélité, pertinence, précision du contexte, débit, CO₂) qui se remplit au
//   fil de `eval_metric` ; chaque score est un bouton qui ouvre le « Détail » (verdicts par
//   affirmation avec l'extrait d'appui) ; « non évalué » avec sa raison, jamais 0 ; « Matrice » en SVG.
// - Un résultat terminé est conservé (store `ragEvals`) et rouvrable par son adresse.
//
// Contournements locaux (composants communs manquants) : `wl-data-table` et `wl-chart-svg` n'existent
// pas encore (le tableau et le SVG sont construits ici), les étapes de l'évaluation sont
// nommées par `wl-run-status.setStage`, `wl-source-panel` est dans documents-commun.js.

import { bubbleMatrix } from "../components/charts.js";
import { segments } from "../components/segments.js";
import { element, icon } from "../core/dom.js";
import { formatCo2, formatDate, formatInteger, formatNumber, formatRate, formatTime } from "../core/format.js";
import { plural, t } from "../core/i18n.js";
import { setMaquette, store } from "../core/store.js";
import { findModel, modelDefaults } from "../sim/modeles.js";
import { sim } from "../sim/sim.js";
import { setOllamaDown } from "../sim/systeme.js";
import {
  baseCounts,
  createSourcePanel,
  ensureBase,
  getBase,
  helpToggle,
  pause,
  prepare,
  setBasePreset,
  subscribeBase,
  waitUntil,
} from "./documents-commun.js";

let counter = 0;
let view = null; // l'instance montée, pour les scénarios

const METRICS = ["faithfulness", "relevance", "context_precision"];
const VERDICT = { "appuyée": "supported", "non appuyée": "unsupported", "contredite": "contradicted" };
const VERDICT_ICON = { supported: "check", unsupported: "warning", contradicted: "error" };
const clamp = (value, low, high) => Math.min(high, Math.max(low, value));

// --- « Serveur » simulé : ce que le juge rendrait pour un modèle --------------------------------

function outcomeFor(data, tag, spec) {
  const profileKey = data.models[tag]?.profile ?? "B";
  const profile = data.profiles[profileKey];
  const unscored = data.profile_unscored[profileKey] ?? 0;
  const override = spec.overrides?.[tag];
  const timeout = (spec.timeouts ?? []).includes(tag);
  const scores = {};
  for (const metric of METRICS) {
    const reason = timeout ? "délai dépassé" : (override?.[metric] ?? override?.all ?? null);
    if (reason) {
      scores[metric] = { score: null, reason };
      continue;
    }
    const base = profile[metric];
    const common = { reason: base.reason ?? null, verdicts: base.claims ?? null, questions: base.questions ?? null, useful: base.useful ?? null };
    if (spec.mode === "set") {
      const questions = data.sets.find((set) => set.id === spec.set_id).questions;
      const limit = questions.length - unscored;
      const byQuestion = questions.map((question, index) =>
        index < limit
          ? { question, score: clamp(base.score + data.deltas[index % data.deltas.length], 0, 100) }
          : { question, score: null, reason: "sortie du juge invalide" },
      );
      const scored = byQuestion.filter((item) => item.score !== null).map((item) => item.score);
      scores[metric] = {
        ...common,
        score: Math.round(scored.reduce((sum, value) => sum + value, 0) / scored.length),
        by_question: byQuestion,
        n_questions: questions.length,
        n_unscored: unscored,
      };
    } else {
      scores[metric] = { ...common, score: base.score };
    }
  }
  const metrics = timeout ? null : { lane: tag, ...(data.lane_metrics[tag] ?? data.lane_metrics["qwen3.5:2b"]) };
  return { timeout, metrics, scores };
}

// Les événements d'un run d'évaluation, au format des scripts du simulateur.
function buildEvents(data, spec, outcomes, extracts, { loaded }) {
  const questions = spec.mode === "set" ? data.sets.find((set) => set.id === spec.set_id).questions.length : 1;
  const events = [{ wait: 0, type: "run_started", data: { kind: "eval", models: spec.models, params: { judge: spec.judge, questions } } }];
  events.push({ wait: 60, type: "retrieval_step", data: { strategy: "common", step: "search" } });
  for (const tag of spec.models) events.push({ wait: 0, type: "lane_status", data: { lane: tag, status: "waiting" } });
  events.push({ wait: 900, type: "sources", data: { sources: extracts } });
  for (const tag of spec.models) {
    const outcome = outcomes.get(tag);
    const cold = spec.origins[tag] === "local" && !loaded.has(tag);
    if (cold) events.push({ wait: 150, type: "lane_status", data: { lane: tag, status: "loading" } });
    events.push({ wait: cold ? 1800 : 200, ...(cold ? { slow_wait: 12000 } : {}), type: "lane_status", data: { lane: tag, status: "generating" } });
    if (outcome.timeout) {
      events.push({ wait: 3500, type: "lane_status", data: { lane: tag, status: "timeout" } });
    } else {
      events.push({ wait: 1400, type: "metrics", data: outcome.metrics });
    }
    loaded.add(tag);
  }
  for (const tag of spec.models) {
    const outcome = outcomes.get(tag);
    if (!outcome.timeout) events.push({ wait: 300, type: "lane_status", data: { lane: tag, status: "judging" } });
    for (const metric of METRICS) {
      const result = outcome.scores[metric];
      events.push({
        wait: outcome.timeout ? 80 : 650,
        type: "eval_metric",
        data: { lane: tag, metric, ...result },
      });
    }
    events.push({ wait: 50, type: "lane_status", data: { lane: tag, status: "done" } });
  }
  events.push({ wait: 200, type: "run_ended", data: { status: "ok", error: null } });
  return events;
}

function newLane(model) {
  return { tag: model.tag, name: model.name, origin: model.origin, answer: "waiting", judge: "waiting", metrics: null, scores: {} };
}

export async function mount(host, ctx) {
  await prepare();
  const uid = `eval-${++counter}`;
  const [data, discussion] = await Promise.all([ctx.data("evaluation.json"), ctx.data("discussion.json"), ensureBase()]);
  const extracts = discussion.sources.slice(0, 4);
  const runId = ctx.params.run_id ?? null;

  // --- État du run affiché -----------------------------------------------------------------
  const ev = {
    id: null,
    status: "idle", // idle | running | ok | cancelled | error | interrupted
    mode: "question",
    question: "",
    setId: data.sets[0].id,
    judge: null,
    lanes: [],
    extracts: [],
    search: "todo",
    finishedAt: null,
    spec: null,
  };
  let view_ = "table"; // table | matrix
  let detail = null; // { tag, metric }
  let run = null;
  let attachment = null;
  let lastSeq = 0;
  let wasHidden = host.hidden;
  const loaded = new Set();

  // --- Structure : réglages ----------------------------------------------------------------
  const guard = ctx.states.ollamaGuard();

  function segmented(name, legend, options, current) {
    const fieldset = element("fieldset", "eval-segments");
    fieldset.append(element("legend", "eval-segments-legend", legend));
    const row = element("div", "eval-segment-row");
    for (const [value, label] of options) {
      const wrap = element("label", "eval-segment");
      const radio = element("input");
      Object.assign(radio, { type: "radio", name: `${uid}-${name}`, value, checked: value === current });
      wrap.append(radio, element("span", "eval-segment-label", label));
      row.append(wrap);
    }
    fieldset.append(row);
    return fieldset;
  }

  const modes = segmented("mode", t("evaluation.source_legend"), [["question", t("evaluation.mode_question")], ["set", t("evaluation.mode_set")]], ev.mode);
  const questionInput = element("textarea", "docs-input eval-question");
  questionInput.id = `${uid}-question`;
  questionInput.rows = 2;
  const questionLabel = element("label", "docs-field-label", t("evaluation.question"));
  questionLabel.htmlFor = questionInput.id;
  const questionField = element("div", "docs-field");
  questionField.append(questionLabel, questionInput);

  const setSelect = element("select", "docs-select");
  setSelect.id = `${uid}-set`;
  for (const set of data.sets) {
    const option = element("option", "", set.label);
    option.value = set.id;
    setSelect.append(option);
  }
  const setLabel = element("label", "docs-field-label", t("evaluation.set"));
  setLabel.htmlFor = setSelect.id;
  const setList = element("ol", "eval-set-list");
  const setDetails = element("details", "eval-set-details");
  const setSummary = element("summary");
  setDetails.append(setSummary, setList);
  const setField = element("div", "docs-field");
  setField.append(setLabel, setSelect, setDetails);
  setField.hidden = true;

  const modelsPicker = document.createElement("wl-model-picker");
  modelsPicker.setAttribute("purpose", "arena");
  modelsPicker.setAttribute("multi", "");
  modelsPicker.setAttribute("label", t("evaluation.models"));
  const judgePicker = document.createElement("wl-model-picker");
  judgePicker.setAttribute("purpose", "judge");
  judgePicker.setAttribute("label", t("evaluation.judge"));
  const pickers = element("div", "eval-pickers");
  pickers.append(modelsPicker, judgePicker);
  const formNotes = element("div", "eval-form-notes");

  const sameExtracts = element("p", "help eval-same", t("evaluation.same_extracts"));
  const launch = element("button", "btn btn-primary", t("evaluation.launch"));
  launch.type = "submit";
  const launchReason = element("p", "help eval-reason");
  launchReason.id = `${uid}-reason`;
  const baseLink = element("a", "", t("evaluation.reason_base_link"));
  baseLink.href = "#/documents/base";
  const launchRow = element("div", "eval-launch");
  launchRow.append(launch, launchReason);
  const settingsTitle = element("h2", "", t("evaluation.settings_title"));
  const form = element("form", "eval-form");
  form.append(modes, questionField, setField, pickers, formNotes, sameExtracts, launchRow);
  const settings = element("section", "eval-settings");
  settings.append(settingsTitle, form);

  // Résultat rouvert : récapitulatif à la place du formulaire.
  const recap = element("section", "eval-recap");
  recap.hidden = true;

  // --- Structure : étapes et résultats -----------------------------------------------------
  const status = document.createElement("wl-run-status");
  status.setAttribute("driven", "");
  const error = document.createElement("wl-error");
  error.setAttribute("alert", "");
  const notices = element("div", "eval-notices");
  const stepsTitle = element("h2", "", t("evaluation.steps_title"));
  const steps = element("ol", "eval-steps");
  steps.setAttribute("aria-label", t("evaluation.steps_label"));
  const panel = createSourcePanel({ prefix: "docs.extracts", autoOpen: false });
  panel.root.classList.add("eval-extracts");
  panel.root.hidden = true;
  const stepsSection = element("section", "eval-steps-section");
  stepsSection.hidden = true;
  stepsSection.append(stepsTitle, status, steps, panel.root);

  const resultsTitle = element("h2", "", t("evaluation.results_title"));
  const judgeBadge = document.createElement("wl-badge");
  judgeBadge.setAttribute("kind", "single-judge");
  const methodHelp = helpToggle(t("evaluation.method"), t("evaluation.method_help"));
  const viewSwitch = segments({
    label: t("evaluation.view_label"),
    options: [
      { value: "table", label: t("evaluation.view_table") },
      { value: "matrix", label: t("evaluation.view_matrix") },
    ],
    value: view_,
    onChange: (value) => setView(value),
  });
  viewSwitch.root.classList.add("eval-view");
  const resultsHead = element("div", "eval-results-head");
  resultsHead.append(resultsTitle, judgeBadge, methodHelp);
  const resultsBody = element("div", "eval-results-body");
  const resultsNotes = element("div", "eval-notices");
  const detailHost = element("div", "eval-detail-host");
  const resultsSection = element("section", "eval-results");
  resultsSection.hidden = true;
  resultsSection.append(resultsHead, viewSwitch.root, resultsBody, resultsNotes, detailHost);

  host.replaceChildren(
    element("h1", "", ctx.route.title),
    ctx.tabs(),
    element("p", "lead", t("evaluation.lead")),
    guard,
    recap,
    settings,
    error,
    notices,
    stepsSection,
    resultsSection,
  );

  // --- Réglages : lecture et garde-fous de lancement --------------------------------------
  function chosenTags() {
    return modelsPicker.values;
  }

  function modelOf(tag) {
    return knownModels.get(tag) ?? null;
  }

  const knownModels = new Map();
  async function rememberModels() {
    for (const tag of [...chosenTags(), judgePicker.value]) {
      if (tag && !knownModels.has(tag)) {
        const model = await findModel(tag);
        if (model) knownModels.set(tag, model);
      }
    }
  }

  function setQuestions() {
    return data.sets.find((set) => set.id === setSelect.value).questions;
  }

  function launchBlocker() {
    if (ev.status === "running") return { text: t("evaluation.reason_running") };
    if (baseCounts(getBase()).documents === 0) return { text: t("evaluation.reason_base"), link: true };
    const tags = chosenTags();
    if (tags.length === 0) return { text: t("evaluation.reason_models") };
    if (tags.length > data.max_models) return { text: t("evaluation.reason_models_max") };
    if (!judgePicker.value) return { text: t("evaluation.reason_judge") };
    if (ev.mode === "question" && !questionInput.value.trim()) return { text: t("evaluation.reason_question") };
    return null;
  }

  async function renderForm() {
    await rememberModels();
    const set = data.sets.find((candidate) => candidate.id === setSelect.value);
    setField.hidden = ev.mode !== "set";
    questionField.hidden = ev.mode !== "question";
    setSummary.textContent = plural("evaluation.set_list", set.questions.length, { count: set.questions.length });
    setList.replaceChildren(...set.questions.map((question) => element("li", "", question)));

    formNotes.replaceChildren();
    const judge = modelOf(judgePicker.value);
    if (judge && typeof judge.params_active_b === "number" && judge.params_active_b < 4) {
      formNotes.append(ctx.states.notice(t("evaluation.judge_weak"), { tone: "warning" }));
    }
    const cloud = [...chosenTags(), judgePicker.value].map(modelOf).filter((model) => model?.origin === "cloud");
    if (cloud.length) {
      const names = [...new Set(cloud.map((model) => model.name))].join(", ");
      formNotes.append(ctx.states.notice(t("evaluation.cloud_warning", { names }), { tone: "warning" }));
    }

    const blocker = launchBlocker();
    launch.disabled = Boolean(blocker);
    launchReason.replaceChildren();
    launchReason.hidden = !blocker;
    if (blocker) {
      launchReason.append(document.createTextNode(`${blocker.text}${blocker.link ? " : " : ""}`));
      if (blocker.link) launchReason.append(baseLink);
      launch.setAttribute("aria-describedby", launchReason.id);
    } else {
      launch.removeAttribute("aria-describedby");
    }
  }

  for (const radio of modes.querySelectorAll("input")) {
    radio.addEventListener("change", () => {
      ev.mode = radio.value;
      renderForm();
    });
  }
  for (const control of [questionInput, setSelect]) control.addEventListener("input", renderForm);
  modelsPicker.addEventListener("wl-model-change", renderForm);
  judgePicker.addEventListener("wl-model-change", renderForm);
  const unsubscribeBase = subscribeBase(() => renderForm());

  // --- Étapes ------------------------------------------------------------------------------
  function laneState(lane, kind) {
    const value = lane[kind];
    if (value === "done") return "done";
    if (value === "running") return "doing";
    if (value === "timeout" || value === "failed") return "failed";
    if (value === "cancelled") return "stopped";
    return "todo";
  }

  function stepStates() {
    const ended = ["ok", "cancelled", "error", "interrupted"].includes(ev.status);
    const stopped = ended && ev.status !== "ok";
    const lanes = ev.lanes;
    const finished = (lane) => ["done", "timeout", "failed", "cancelled"].includes(lane.answer);
    let answers = "todo";
    if (lanes.length && lanes.every(finished)) answers = lanes.every((lane) => ["timeout", "failed"].includes(lane.answer)) ? "failed" : "done";
    else if (lanes.some((lane) => lane.answer !== "waiting")) answers = "doing";
    let judge = "todo";
    const judged = (lane) => lane.judge === "done" || ["timeout", "failed", "cancelled"].includes(lane.answer);
    if (lanes.length && lanes.every(judged)) judge = "done";
    else if (lanes.some((lane) => lane.judge !== "waiting")) judge = "doing";
    const states = { search: ev.search, answers, judge };
    if (stopped) for (const key of Object.keys(states)) if (states[key] === "doing" || states[key] === "todo") states[key] = "stopped";
    return states;
  }

  const stepText = (state) => t(`evaluation.state_${state}`);

  function laneList(kind) {
    const list = element("ul", "eval-lane-list");
    for (const lane of ev.lanes) {
      let state = laneState(lane, kind);
      let text = stepText(state);
      if (kind === "answer" && lane.answer === "timeout") text = t("evaluation.lane_timeout");
      if (kind === "judge" && ["timeout", "failed"].includes(lane.answer)) {
        state = "failed";
        text = t("evaluation.state_failed");
      }
      const item = element("li", "eval-lane");
      item.dataset.state = state;
      item.append(element("span", "eval-lane-name", `${lane.name} : `), element("span", "eval-lane-state", text));
      list.append(item);
    }
    return list;
  }

  function renderSteps() {
    stepsSection.hidden = ev.status === "idle";
    if (ev.status === "idle") return;
    const states = stepStates();
    const open = panel.root.open;
    const make = (key, label, extra = []) => {
      const item = element("li", "eval-step");
      item.dataset.state = states[key];
      const head = element("p", "eval-step-head");
      head.append(element("strong", "eval-step-name", label), element("span", "eval-step-state", stepText(states[key])));
      item.append(head, ...extra);
      return item;
    };
    const searchExtra = [];
    if (ev.extracts.length) {
      const toggle = element("button", "btn eval-extracts-toggle", t(open ? "evaluation.hide_extracts" : "evaluation.view_extracts"));
      toggle.type = "button";
      toggle.setAttribute("aria-expanded", String(open));
      toggle.addEventListener("click", () => {
        panel.root.open = !panel.root.open;
      });
      const found = element("span", "help", plural("evaluation.extracts_found", ev.extracts.length, { count: ev.extracts.length }));
      const row = element("p", "eval-step-extra");
      row.append(found, toggle);
      searchExtra.push(row);
    }
    steps.replaceChildren(
      make("search", t("evaluation.step_search"), searchExtra),
      make("answers", t("evaluation.step_answers"), [laneList("answer")]),
      make("judge", t("evaluation.step_judge"), [laneList("judge")]),
    );
    panel.root.hidden = ev.extracts.length === 0;
  }
  panel.root.addEventListener("toggle", renderSteps);

  // --- Résultats : tableau -----------------------------------------------------------------
  function pendingText(lane, metric) {
    if (ev.status === "cancelled") return { reason: t("evaluation.not_scored_stopped") };
    if (ev.status === "interrupted" || ev.status === "error") return { reason: t("evaluation.not_scored_interrupted") };
    if (["timeout", "failed"].includes(lane.answer)) return { reason: t("evaluation.lane_timeout") };
    const doing = lane.judge === "running" || lane.answer === "running";
    return { pending: t(doing ? "evaluation.pending_doing" : "evaluation.pending_todo"), doing };
  }

  function scoreCell(lane, metric) {
    const cell = element("td", "eval-cell");
    cell.dataset.metric = metric;
    const result = lane.scores[metric];
    if (result && typeof result.score === "number") {
      const button = element("button", "eval-score", `${formatNumber(result.score)}/100`);
      button.type = "button";
      button.dataset.key = `${lane.tag}|${metric}`;
      button.setAttribute("aria-haspopup", "true");
      button.setAttribute("aria-expanded", String(detail?.tag === lane.tag && detail?.metric === metric));
      button.setAttribute(
        "aria-label",
        t("evaluation.score_label", { score: `${formatNumber(result.score)}/100`, metric: t(`evaluation.metric_${metric}`), model: lane.name }),
      );
      button.addEventListener("click", () => openDetail(lane.tag, metric));
      cell.append(button);
      if (result.n_questions) {
        const unscored = result.n_unscored ? ` (${plural("evaluation.unscored", result.n_unscored, { count: result.n_unscored })})` : "";
        cell.append(element("span", "help eval-cell-note", `${t("evaluation.of_questions", { count: result.n_questions })}${unscored}`));
      }
      return cell;
    }
    if (result) {
      cell.append(ctx.states.scoreValue(null, result.reason));
      return cell;
    }
    const pending = pendingText(lane, metric);
    if (pending.reason) cell.append(ctx.states.scoreValue(null, pending.reason));
    else cell.append(element("span", `eval-pending${pending.doing ? " is-doing" : ""}`, pending.pending));
    return cell;
  }

  function measureCell(lane, kind) {
    const cell = element("td", "eval-cell");
    if (lane.metrics) {
      if (kind === "rate") cell.append(document.createTextNode(formatRate(lane.metrics.tps)));
      else cell.append(ctx.states.co2Value(lane.metrics.co2));
    } else if (["timeout", "failed", "cancelled"].includes(lane.answer)) {
      cell.append(element("span", "eval-pending", t("evaluation.no_answer")));
    } else {
      cell.append(element("span", `eval-pending${lane.answer === "running" ? " is-doing" : ""}`, t(lane.answer === "running" ? "evaluation.pending_doing" : "evaluation.pending_todo")));
    }
    return cell;
  }

  function buildTable() {
    const table = element("table", "docs-table eval-table");
    table.append(element("caption", "sr-only", t("evaluation.results_title")));
    const head = element("tr");
    const header = (label, help) => {
      const cell = element("th");
      cell.scope = "col";
      const wrap = element("span", "eval-head");
      wrap.append(element("span", "", label));
      if (help) wrap.append(helpToggle(label, help));
      cell.append(wrap);
      return cell;
    };
    head.append(
      header(t("evaluation.col_model")),
      ...METRICS.map((metric) => header(t(`evaluation.col_${metric}`), t(`evaluation.help_${metric}`))),
      header(t("evaluation.col_rate")),
      header(t("evaluation.col_co2")),
    );
    const thead = element("thead");
    thead.append(head);
    const tbody = element("tbody");
    for (const lane of ev.lanes) {
      const row = element("tr", "eval-row");
      row.dataset.lane = lane.tag;
      const name = element("th", "eval-model");
      name.scope = "row";
      const badge = document.createElement("wl-badge");
      badge.setAttribute("kind", lane.origin === "cloud" ? "cloud" : "local");
      const label = element("span", "eval-model-line");
      label.append(element("span", "eval-model-name", lane.name), badge);
      name.append(label);
      row.append(name, ...METRICS.map((metric) => scoreCell(lane, metric)), measureCell(lane, "rate"), measureCell(lane, "co2"));
      tbody.append(row);
    }
    table.append(thead, tbody);
    const wrap = element("div", "docs-table-wrap");
    wrap.setAttribute("role", "region");
    wrap.setAttribute("aria-label", t("evaluation.results_title"));
    wrap.tabIndex = 0;
    wrap.append(table);
    return wrap;
  }

  // --- Résultats : matrice (composant commun js/components/charts.js, UX-DR14) ----------------
  // Débit en échelle logarithmique : un modèle cloud à 365 tokens/s écraserait les locaux.
  function buildMatrix() {
    const points = ev.lanes.filter((lane) => typeof lane.scores.faithfulness?.score === "number" && lane.metrics && typeof lane.metrics.tps === "number");
    const missing = ev.lanes.filter((lane) => !points.includes(lane));
    const co2Text = (lane) => (lane.metrics.co2?.mg === null ? t("co2.unmeasurable") : formatCo2(lane.metrics.co2.mg));
    const desc = `${t("evaluation.matrix_desc")} ${points
      .map((lane) => t("evaluation.matrix_point", { name: lane.name, score: formatNumber(lane.scores.faithfulness.score), rate: formatRate(lane.metrics.tps), co2: co2Text(lane) }))
      .join(" ; ")}.`;
    return bubbleMatrix({
      title: t("evaluation.matrix_title"),
      desc,
      points: points.map((lane) => ({ name: lane.name, x: lane.metrics.tps, y: lane.scores.faithfulness.score, mg: lane.metrics.co2?.mg ?? null })),
      x: { label: t("evaluation.axis_x"), log: true, min: 5, max: 500, ticks: [10, 30, 100, 300] },
      y: { label: t("evaluation.axis_y"), max: 100, ticks: [0, 25, 50, 75, 100] },
      size: { title: t("evaluation.legend_size"), format: (mg) => formatCo2(mg), unmeasurable: t("evaluation.legend_unmeasurable") },
      seeTable: { label: t("evaluation.see_table"), onClick: () => setView("table", { focus: true }) },
      missing: missing.length ? t("evaluation.unplotted", { names: missing.map((lane) => lane.name).join(", ") }) : null,
      className: "eval",
    });
  }

  function setView(next, { focus = false } = {}) {
    view_ = next;
    viewSwitch.select(next, { silent: true, focus });
    renderResults();
  }

  // --- Résultats : détail d'un score -------------------------------------------------------
  function verdictList(verdicts) {
    const list = element("ol", "eval-claims");
    for (const item of verdicts) {
      const kind = VERDICT[item.verdict] ?? "unsupported";
      const row = element("li", "eval-claim");
      row.dataset.verdict = kind;
      const head = element("p", "eval-claim-head");
      head.append(icon(VERDICT_ICON[kind]), element("strong", "eval-verdict", t(`evaluation.verdict_${kind}`)));
      row.append(head, element("p", "eval-claim-text", item.claim));
      const source = item.support ? ev.extracts.find((candidate) => candidate.n === item.support) : null;
      row.append(
        element(
          "p",
          "help eval-claim-support",
          source ? t("evaluation.support", { document: source.document, page: source.page }) : t("evaluation.no_support"),
        ),
      );
      if (source) row.append(element("blockquote", "eval-claim-quote", source.passage ?? source.text));
      list.append(row);
    }
    return list;
  }

  function claimsSummary(verdicts) {
    const count = (word) => verdicts.filter((item) => item.verdict === word).length;
    const parts = [
      plural("evaluation.supported", count("appuyée"), { count: count("appuyée") }),
      ...(count("non appuyée") ? [plural("evaluation.unsupported", count("non appuyée"), { count: count("non appuyée") })] : []),
      ...(count("contredite") ? [plural("evaluation.contradicted", count("contredite"), { count: count("contredite") })] : []),
    ];
    return `${plural("evaluation.claims", verdicts.length, { count: verdicts.length })} : ${parts.join(", ")}`;
  }

  function extractNames(numbers) {
    const names = numbers.map((n) => ev.extracts.find((candidate) => candidate.n === n)).filter(Boolean);
    return names.length ? names.map((source) => `[${source.n}] ${source.document}, page ${source.page}`) : [t("evaluation.none")];
  }

  function buildDetail() {
    const lane = ev.lanes.find((candidate) => candidate.tag === detail.tag);
    const result = lane.scores[detail.metric];
    const metricName = t(`evaluation.col_${detail.metric}`);
    const section = element("section", "eval-detail");
    section.setAttribute("aria-labelledby", `${uid}-detail-title`);
    const heading = element("h3", "eval-detail-title", t("evaluation.detail_heading", { model: lane.name, metric: metricName }));
    heading.id = `${uid}-detail-title`;
    heading.tabIndex = -1;
    const close = element("button", "btn eval-detail-close", t("evaluation.detail_close"));
    close.type = "button";
    close.addEventListener("click", closeDetail);
    const head = element("div", "eval-detail-head");
    head.append(heading, close);
    section.append(head);
    section.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        closeDetail();
      }
    });
    section.append(element("p", "eval-detail-score", `${formatNumber(result.score)}/100`));

    if (result.by_question) {
      const unscored = result.n_unscored ? ` (${plural("evaluation.unscored", result.n_unscored, { count: result.n_unscored })})` : "";
      section.append(element("p", "help", `${t("evaluation.of_questions", { count: result.n_questions })}${unscored}`));
      const list = element("ol", "eval-by-question");
      result.by_question.forEach((item, index) => {
        const row = element("li", "eval-question-row");
        row.append(element("span", "eval-question-text", item.question));
        row.append(
          item.score === null
            ? element("span", "help", t("evaluation.question_unscored", { reason: item.reason }))
            : element("strong", "", `${formatNumber(item.score)}/100`),
        );
        if (index === 0 && detail.metric === "faithfulness" && result.verdicts) {
          const more = element("details", "eval-first");
          more.append(element("summary", "", t("evaluation.first_question_verdicts")), element("p", "help", claimsSummary(result.verdicts)), verdictList(result.verdicts));
          row.append(more);
        }
        list.append(row);
      });
      section.append(element("h4", "eval-detail-sub", t("evaluation.per_question")), list);
      return section;
    }

    if (detail.metric === "faithfulness" && result.verdicts) {
      section.append(element("p", "eval-claims-summary", claimsSummary(result.verdicts)), verdictList(result.verdicts));
    } else {
      if (result.reason) section.append(element("p", "eval-reason-text", result.reason));
      if (detail.metric === "relevance" && result.questions) {
        const list = element("ul", "eval-found");
        for (const question of result.questions) list.append(element("li", "", question));
        section.append(element("h4", "eval-detail-sub", t("evaluation.questions_found")), list);
      }
      if (detail.metric === "context_precision" && result.useful) {
        const useless = ev.extracts.map((source) => source.n).filter((n) => !result.useful.includes(n));
        const block = (title, numbers) => {
          const list = element("ul", "eval-found");
          for (const line of extractNames(numbers)) list.append(element("li", "", line));
          return [element("h4", "eval-detail-sub", title), list];
        };
        section.append(...block(t("evaluation.useful_extracts"), result.useful), ...block(t("evaluation.useless_extracts"), useless));
      }
    }
    return section;
  }

  function openDetail(tag, metric) {
    detail = { tag, metric };
    renderResults();
    detailHost.querySelector(".eval-detail-title")?.focus();
  }

  function closeDetail() {
    const key = detail ? `${detail.tag}|${detail.metric}` : null;
    detail = null;
    renderResults();
    if (key) resultsBody.querySelector(`.eval-score[data-key="${CSS.escape(key)}"]`)?.focus();
  }

  function renderResults() {
    const active = document.activeElement;
    const keep = active?.dataset?.key && resultsSection.contains(active) ? active.dataset.key : null;
    const started = ev.status !== "idle" && ev.lanes.length > 0;
    resultsSection.hidden = !started;
    if (!started) return;
    judgeBadge.hidden = false;
    viewSwitch.root.hidden = false;
    resultsBody.replaceChildren(view_ === "matrix" ? buildMatrix() : buildTable());
    detailHost.replaceChildren(...(detail ? [buildDetail()] : []));

    resultsNotes.replaceChildren();
    const notEvaluated = ev.lanes.filter((lane) => METRICS.every((metric) => lane.scores[metric] && lane.scores[metric].score === null));
    const ended = ["ok", "cancelled", "error", "interrupted"].includes(ev.status);
    if (ev.status === "cancelled") resultsNotes.append(ctx.states.notice(t("evaluation.partial"), { tone: "warning" }));
    if (ev.status === "interrupted") resultsNotes.append(ctx.states.notice(t("evaluation.interrupted"), { tone: "warning" }));
    if (notEvaluated.length && ended) {
      resultsNotes.append(ctx.states.notice(plural("evaluation.not_evaluated_note", notEvaluated.length, { count: notEvaluated.length }), { tone: "warning" }));
    }
    if (keep) resultsBody.querySelector(`[data-key="${CSS.escape(keep)}"]`)?.focus();
  }

  function render() {
    renderSteps();
    renderResults();
    renderForm();
  }

  // --- Flux du run -------------------------------------------------------------------------
  const laneOf = (tag) => ev.lanes.find((lane) => lane.tag === tag);
  const forward = (_data, envelope) => status.feed(envelope);

  const handlers = {
    "*": (_data, envelope) => {
      lastSeq = envelope.seq;
    },
    run_started: (payload, envelope) => {
      ev.search = "doing";
      forward(payload, envelope);
      status.setStage("retrieving", { label: t("evaluation.stage_search") });
      render();
    },
    lane_status: (payload) => {
      const lane = laneOf(payload.lane);
      if (!lane) return;
      if (payload.status === "waiting") lane.answer = "waiting";
      else if (["loading", "generating"].includes(payload.status)) lane.answer = "running";
      else if (["timeout", "failed", "cancelled"].includes(payload.status)) lane.answer = payload.status;
      else if (payload.status === "judging") {
        lane.judge = "running";
        status.setStage("judging");
      } else if (payload.status === "done") lane.judge = "done";
      render();
    },
    sources: (payload) => {
      ev.extracts = payload.sources;
      ev.search = "done";
      panel.setSources(payload.sources);
      status.setStage("generating", { label: t("evaluation.stage_answers") });
      render();
    },
    metrics: (payload) => {
      const lane = laneOf(payload.lane);
      if (!lane) return;
      lane.metrics = payload;
      lane.answer = "done";
      render();
    },
    eval_metric: (payload) => {
      const lane = laneOf(payload.lane);
      if (!lane) return;
      const { lane: _lane, metric, ...rest } = payload;
      lane.scores[metric] = rest;
      render();
    },
    run_ended: (payload, envelope) => {
      forward(payload, envelope);
      finish(payload);
    },
  };

  function snapshot() {
    return {
      id: ev.id,
      finished_at: new Date().toISOString(),
      mode: ev.mode,
      question: ev.question,
      set_id: ev.setId,
      judge: ev.judge,
      lanes: structuredClone(ev.lanes),
      extracts: structuredClone(ev.extracts),
    };
  }

  function finish(payload) {
    ev.status = payload.status ?? "error";
    attachment?.close();
    attachment = null;
    run = null;
    if (payload.error) error.error = payload.error;
    if (ev.status === "ok") {
      ev.finishedAt = new Date().toISOString();
      store.set((state) => ({ ragEvals: { ...(state.ragEvals ?? {}), [ev.id]: snapshot() } }));
      ctx.announce(t("evaluation.done_announce"));
      const link = element("a", "", t("evaluation.reopen_link"));
      link.href = `#/documents/evaluation/${ev.id}`;
      const note = ctx.states.notice(`${t("evaluation.saved")} `, { tone: "success" });
      note.append(link);
      notices.replaceChildren(note);
    }
    render();
  }

  function follow(simRun, { after = 0 } = {}) {
    run = simRun;
    lastSeq = after;
    ev.id = simRun.id;
    ev.status = "running";
    status.runId = simRun.id;
    attachment = simRun.attach(handlers, { after });
    render();
  }

  // --- Lancer ------------------------------------------------------------------------------
  async function start(options = {}) {
    if (ev.status === "running") return null;
    await rememberModels();
    error.error = null;
    notices.replaceChildren();
    if (launchBlocker()) return null;
    const tags = chosenTags();
    const models = tags.map(modelOf);
    const judge = modelOf(judgePicker.value);
    // Ce que `POST /api/rag/eval/runs` refuserait avant de créer le run.
    for (const model of [...models, judge]) {
      const refused = sim.precheck({ origin: model.origin, kind: "eval", model });
      if (!refused) continue;
      if (refused.code === "run_busy") {
        const other = sim.get(refused.detail.run_id);
        const spec = other.options.vars?.spec;
        ev.mode = spec.mode;
        ev.question = spec.question ?? "";
        ev.setId = spec.set_id ?? ev.setId;
        ev.judge = { tag: spec.judge, name: spec.names[spec.judge] };
        ev.lanes = spec.models.map((tag) => newLane({ tag, name: spec.names[tag], origin: spec.origins[tag] }));
        ev.extracts = [];
        ev.search = "todo";
        detail = null;
        notices.replaceChildren(ctx.states.joinedNotice());
        follow(other);
        return run;
      }
      error.error = refused; // les réglages restent tels quels
      return null;
    }
    const spec = {
      mode: ev.mode,
      question: ev.mode === "question" ? questionInput.value.trim() : null,
      set_id: ev.mode === "set" ? setSelect.value : null,
      judge: judge.tag,
      models: tags,
      overrides: options.overrides ?? null,
      timeouts: options.timeouts ?? [],
      names: Object.fromEntries([...models, judge].map((model) => [model.tag, model.name])),
      origins: Object.fromEntries([...models, judge].map((model) => [model.tag, model.origin])),
    };
    const outcomes = new Map(tags.map((tag) => [tag, outcomeFor(data, tag, spec)]));
    const events = buildEvents(data, spec, outcomes, extracts, { loaded });
    ev.mode = spec.mode;
    ev.question = spec.question ?? "";
    ev.setId = spec.set_id ?? ev.setId;
    ev.judge = { tag: judge.tag, name: judge.name };
    ev.lanes = models.map(newLane);
    ev.extracts = [];
    ev.search = "todo";
    detail = null;
    view_ = "table";
    panel.clear();
    panel.root.open = false;
    viewSwitch.select("table", { silent: true });
    // Événements construits à l'exécution (nombre de modèles et mode libres), rejoués tels quels.
    const simRun = sim.play({ kind: "eval", events }, null, {
      vars: { spec }, // entrée de la commande, relue par un autre onglet (409 rejoint)
      kind: "eval",
      origin: models.some((model) => model.origin === "cloud") ? "cloud" : "local",
      module: "eval",
      speed: options.speed,
    });
    follow(simRun);
    return simRun;
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    start();
  });

  error.addEventListener("wl-error-action", async (event) => {
    const id = event.detail.id;
    if (id === "retry") {
      error.error = null;
      start();
    } else if (id === "allow_cloud") {
      store.set({ allowCloud: true });
      error.error = null;
    } else if (id === "use_local") {
      const defaults = await modelDefaults("arena", false).catch(() => ({ tags: [] }));
      modelsPicker.values = defaults.tags;
      error.error = null;
    } else if (id === "smaller") {
      const suggested = error.error?.detail?.suggested_model;
      const model = suggested ? await findModel(suggested) : null;
      if (model) judgePicker.value = model.tag;
      setMaquette({ ramGuard: false });
      error.error = null;
      notices.replaceChildren(ctx.states.notice(t("evaluation.smaller", { name: model?.name ?? suggested ?? "" }), { tone: "success" }));
    } else if (id === "unload") {
      setMaquette({ ramGuard: false });
      error.error = null;
      notices.replaceChildren(ctx.states.notice(t("evaluation.unloaded"), { tone: "success" }));
    }
  });

  // --- Écran masqué puis revu (reprise par `?after=<seq>`) --------------------------------
  const visibility = new MutationObserver(() => {
    if (host.hidden === wasHidden) return;
    wasHidden = host.hidden;
    if (wasHidden) {
      attachment?.close();
      attachment = null;
    } else if (run) {
      attachment = run.attach(handlers, { after: lastSeq });
    }
  });
  visibility.observe(host, { attributes: true, attributeFilter: ["hidden"] });

  // --- Résultat conservé (route avec `run_id`) --------------------------------------------
  async function loadSnapshot(id) {
    const live = store.get().ragEvals?.[id];
    if (live) return live;
    const stored = data.runs[id];
    if (!stored) return null;
    const spec = { mode: stored.mode, question: stored.question, set_id: stored.set_id, overrides: stored.overrides, timeouts: [] };
    const lanes = [];
    for (const tag of stored.models) {
      const model = await findModel(tag);
      const outcome = outcomeFor(data, tag, spec);
      lanes.push({ ...newLane(model), answer: "done", judge: "done", metrics: outcome.metrics, scores: outcome.scores });
    }
    const judge = await findModel(stored.judge);
    return {
      id,
      finished_at: stored.finished_at,
      mode: stored.mode,
      question: stored.question,
      set_id: stored.set_id,
      judge: { tag: judge.tag, name: judge.name },
      lanes,
      extracts,
    };
  }

  async function showSaved(id) {
    const saved = await loadSnapshot(id);
    settings.hidden = true;
    if (!saved) {
      recap.hidden = false;
      recap.replaceChildren(
        ctx.states.errorBox("run_not_found", {
          detail: { run_id: id },
          vars: { what: t("evaluation.not_found_what"), new_label: t("evaluation.new_eval"), new_href: "#/documents/evaluation" },
        }),
      );
      return;
    }
    Object.assign(ev, {
      id: saved.id,
      status: "ok",
      mode: saved.mode,
      question: saved.question ?? "",
      setId: saved.set_id ?? ev.setId,
      judge: saved.judge,
      lanes: saved.lanes,
      extracts: saved.extracts,
      search: "done",
      finishedAt: saved.finished_at,
    });
    panel.setSources(ev.extracts);
    const title = element("h2", "", t("evaluation.reopened_title"));
    const lines = element("ul", "eval-recap-list");
    const set = data.sets.find((candidate) => candidate.id === ev.setId);
    lines.append(
      element("li", "", t("evaluation.reopened_date", { date: `${formatDate(saved.finished_at)} ${formatTime(saved.finished_at)}` })),
      element("li", "", ev.mode === "set" ? t("evaluation.reopened_set", { set: set.label }) : t("evaluation.reopened_question", { question: ev.question })),
      element("li", "", t("evaluation.reopened_judge", { judge: saved.judge.name })),
      element("li", "", t("evaluation.reopened_models", { models: ev.lanes.map((lane) => lane.name).join(", ") })),
    );
    const again = element("a", "btn", t("evaluation.new_eval"));
    again.href = "#/documents/evaluation";
    recap.replaceChildren(title, lines, element("p", "help", t("evaluation.reopened_note")), again);
    recap.hidden = false;
    render();
  }

  view = {
    host,
    modelsPicker,
    judgePicker,
    questionInput,
    launch,
    panel,
    error,
    status,
    start,
    get ev() {
      return ev;
    },
    get run() {
      return run;
    },
    get detail() {
      return detail;
    },
    whenPickersReady: () =>
      waitUntil(() => (modelsPicker.values.length > 0 || modelsPicker.querySelector("wl-error:not([hidden])")) && (judgePicker.value || judgePicker.querySelector("wl-error:not([hidden])")), 5000),
    setMode(mode) {
      const radio = modes.querySelector(`input[value="${mode}"]`);
      radio.checked = true;
      ev.mode = mode;
      renderForm();
    },
    setQuestion(text) {
      questionInput.value = text;
      renderForm();
    },
    chooseSet(id) {
      setSelect.value = id;
      renderForm();
    },
    setView,
    refresh: renderForm,
    markLoaded() {
      for (const tag of chosenTags()) loaded.add(tag);
    },
    openDetail,
    openExtracts() {
      panel.root.open = true;
    },
    // Un run lancé depuis un autre onglet (409) : joué, mais non suivi par cet écran.
    async startElsewhere(tags) {
      const models = await Promise.all(tags.map(findModel));
      const judge = await findModel("qwen3.6:7b");
      const spec = {
        mode: "question",
        question: data.default_question,
        set_id: null,
        judge: judge.tag,
        models: tags,
        overrides: null,
        timeouts: [],
        names: Object.fromEntries([...models, judge].map((model) => [model.tag, model.name])),
        origins: Object.fromEntries([...models, judge].map((model) => [model.tag, model.origin])),
      };
      const outcomes = new Map(tags.map((tag) => [tag, outcomeFor(data, tag, spec)]));
      return sim.play({ kind: "eval", events: buildEvents(data, spec, outcomes, extracts, { loaded: new Set(tags) }) }, null, {
        vars: { spec },
        kind: "eval",
        origin: "local",
        module: "eval",
      });
    },
  };

  if (runId) {
    await showSaved(runId);
  } else {
    questionInput.value = "";
    render();
  }
  return () => {
    view = null;
    unsubscribeBase();
    visibility.disconnect();
    guard.dispose?.();
    attachment?.close();
  };
}

// --- Scénarios ----------------------------------------------------------------------------

// Repart de l'état d'ouverture, pose la base attendue, attend les sélecteurs, applique `setup`.
async function fresh(ctx, { base = "complet", setup = () => {}, pickers = true } = {}) {
  await ctx.reset();
  await setBasePreset(base);
  setup();
  await waitUntil(() => view !== null);
  if (pickers) await view.whenPickersReady();
}

const untilDone = (simRun) => simRun?.done ?? Promise.resolve();

async function filled(ctx, options = {}) {
  await fresh(ctx, options);
  view.setQuestion((await ctx.data("evaluation.json")).default_question);
}

async function runToEnd(ctx, options = {}, startOptions = {}) {
  await filled(ctx, options);
  const simRun = await view.start(startOptions);
  await untilDone(simRun);
  return simRun;
}

export const scenarios = [
  {
    id: "formulaire",
    label: "Formulaire prêt : modèles et juge par défaut, « Saisissez une question »",
    routes: ["evaluation"],
    run: (ctx) => fresh(ctx),
  },
  {
    id: "jeu-de-questions",
    label: "Choix d'un jeu de questions fictif (8 questions)",
    routes: ["evaluation"],
    async run(ctx) {
      await fresh(ctx);
      view.setMode("set");
      view.chooseSet("atelier");
    },
  },
  {
    id: "base-vide",
    label: "Base vide : « Importez des documents pour évaluer » et le lien",
    routes: ["evaluation"],
    async run(ctx) {
      await filled(ctx, { base: "vide" });
    },
  },
  {
    id: "aucun-modele",
    label: "Aucun modèle choisi : « Choisissez au moins un modèle »",
    routes: ["evaluation"],
    async run(ctx) {
      await filled(ctx);
      view.modelsPicker.values = [];
    },
  },
  {
    id: "juge-peu-fiable",
    label: "Juge sous 4 milliards de paramètres actifs : « Note peu fiable »",
    routes: ["evaluation"],
    async run(ctx) {
      await filled(ctx);
      view.judgePicker.value = "gemma4:1b";
    },
  },
  {
    id: "cloud-autorise",
    label: "Cloud autorisé : modèles cloud évalués, les extraits quittent le poste (avertissement), CO₂ « estimé » et « non mesurable »",
    routes: ["evaluation"],
    async run(ctx) {
      await filled(ctx, { setup: () => ctx.store.set({ allowCloud: true }) });
      await waitUntil(() => view.modelsPicker.knows("gpt-5-mini") && view.modelsPicker.knows("claude-haiku-4-5"));
      view.modelsPicker.values = ["qwen3.5:2b", "gpt-5-mini", "claude-haiku-4-5"];
      await untilDone(await view.start());
    },
  },
  {
    id: "evaluation-en-cours",
    label: "Évaluation en cours : étapes nommées, scores au fil de l'eau",
    routes: ["evaluation"],
    async run(ctx) {
      await filled(ctx);
      view.markLoaded();
      await view.start({ speed: 2 });
      await waitUntil(() => view.ev.lanes.some((lane) => lane.scores.faithfulness));
    },
  },
  {
    id: "voir-les-extraits",
    label: "« Voir les extraits » : les 4 extraits communs, fournis à tous les modèles",
    routes: ["evaluation"],
    async run(ctx) {
      await runToEnd(ctx);
      view.openExtracts();
      await waitUntil(() => view.panel.root.open);
    },
  },
  {
    id: "evaluation-terminee",
    label: "Évaluation terminée : tableau complet, résultat conservé",
    routes: ["evaluation"],
    run: (ctx) => runToEnd(ctx),
  },
  {
    id: "detail-fidelite",
    label: "Détail de la fidélité : « 7 affirmations : 6 appuyées, 1 non appuyée » et l'extrait d'appui",
    routes: ["evaluation"],
    async run(ctx) {
      await runToEnd(ctx);
      view.openDetail("qwen3.5:2b", "faithfulness");
    },
  },
  {
    id: "detail-precision-contexte",
    label: "Détail de la précision du contexte : extraits jugés utiles et inutiles",
    routes: ["evaluation"],
    async run(ctx) {
      await runToEnd(ctx);
      view.openDetail("gemma4:1b", "context_precision");
    },
  },
  {
    id: "matrice",
    label: "Matrice : fidélité × débit, CO₂ en taille, légende de taille",
    routes: ["evaluation"],
    async run(ctx) {
      await runToEnd(ctx);
      view.setView("matrix");
    },
  },
  {
    id: "jeu-termine",
    label: "Jeu de 8 questions terminé : score moyen, « sur 8 questions (1 non évaluée) »",
    routes: ["evaluation"],
    async run(ctx) {
      await fresh(ctx);
      view.setMode("set");
      view.chooseSet("atelier");
      await untilDone(await view.start());
    },
  },
  {
    id: "detail-jeu",
    label: "Détail d'un jeu de questions : un score par question, verdicts de la première",
    routes: ["evaluation"],
    async run(ctx) {
      await fresh(ctx);
      view.setMode("set");
      view.chooseSet("atelier");
      await untilDone(await view.start());
      view.openDetail("qwen3.5:2b", "faithfulness");
    },
  },
  {
    id: "non-evalue",
    label: "« non évalué » avec sa raison, jamais 0 : réponse vide et sortie du juge invalide",
    routes: ["evaluation"],
    async run(ctx) {
      await filled(ctx);
      await untilDone(
        await view.start({
          overrides: { "gemma4:1b": { all: "réponse vide" }, "lfm2.5:1.2b": { relevance: "sortie du juge invalide" } },
        }),
      );
    },
  },
  {
    id: "modele-delai-depasse",
    label: "Un modèle dépasse le délai : « délai dépassé » dans les étapes, non évalué, les autres continuent",
    routes: ["evaluation"],
    async run(ctx) {
      await runToEnd(ctx, {}, { timeouts: ["lfm2.5:1.2b"] });
    },
  },
  {
    id: "arret",
    label: "Arrêter pendant l'évaluation : résultats partiels, rien à 0",
    routes: ["evaluation"],
    async run(ctx) {
      await filled(ctx);
      view.markLoaded();
      const simRun = await view.start({ speed: 2 });
      await waitUntil(() => view.ev.lanes.some((lane) => lane.scores.faithfulness));
      await view.status.cancel();
      await untilDone(simRun);
    },
  },
  {
    id: "reprise-au-retour",
    label: "Aller sur l'Accueil pendant l'évaluation, puis revenir : reprise sans perte",
    routes: ["evaluation"],
    async run(ctx) {
      await filled(ctx);
      view.markLoaded();
      const simRun = await view.start({ speed: 2 });
      await waitUntil(() => view.ev.extracts.length > 0);
      await ctx.navigate("/");
      await pause(1500);
      await ctx.navigate("/documents/evaluation");
      await untilDone(simRun);
    },
  },
  {
    id: "rejoint-409",
    label: "Une évaluation tourne déjà (autre onglet) : 409 rejoint",
    routes: ["evaluation"],
    async run(ctx) {
      await filled(ctx);
      await view.startElsewhere(["qwen3.5:2b", "gemma4:1b"]);
      await pause(400);
      await view.start();
      await waitUntil(() => view.run !== null);
    },
  },
  {
    id: "erreur-ollama-arrete",
    label: "Ollama arrêté : bandeau, le lancement est refusé avec la marche à suivre",
    routes: ["evaluation"],
    async run(ctx) {
      await filled(ctx, { setup: () => setOllamaDown(true) });
      await view.start();
    },
  },
  {
    id: "garde-fou-memoire",
    label: "Garde-fou mémoire : besoin chiffré, deux issues, réglages gardés",
    routes: ["evaluation"],
    async run(ctx) {
      await filled(ctx, { setup: () => setMaquette({ ramGuard: true }) });
      await view.start();
    },
  },
  {
    id: "connexion-perdue",
    label: "Connexion perdue pendant l'évaluation, puis reprise sans doublon",
    routes: ["evaluation"],
    async run(ctx) {
      await filled(ctx);
      view.markLoaded();
      const simRun = await view.start();
      await waitUntil(() => view.ev.extracts.length > 0);
      simRun.cut(3000);
      await pause(1500);
      await untilDone(simRun);
      await waitUntil(() => ctx.store.get().connection.status === "open");
    },
  },
  {
    id: "serveur-redemarre",
    label: "Le serveur redémarre pendant l'évaluation : « Interrompu », résultats partiels",
    routes: ["evaluation"],
    async run(ctx) {
      await filled(ctx);
      view.markLoaded();
      const simRun = await view.start({ speed: 2 });
      await waitUntil(() => view.ev.lanes.some((lane) => lane.metrics));
      sim.restartServer();
      await untilDone(simRun);
    },
  },
  {
    id: "resultat-rouvert",
    label: "Résultat rouvert depuis son adresse : « non évalué » avec sa raison, sans relancer de modèle",
    async run(ctx) {
      await ctx.reset();
      await setBasePreset("complet");
      await ctx.navigate("/documents/evaluation/run-eval-demo");
      await waitUntil(() => view !== null && view.ev.status === "ok");
    },
  },
  {
    id: "resultat-introuvable",
    label: "Adresse d'une évaluation qui n'existe plus : « Évaluation introuvable »",
    async run(ctx) {
      await ctx.reset();
      await ctx.navigate("/documents/evaluation/run-eval-inconnue");
      await waitUntil(() => view !== null && view.host.querySelector('wl-error[data-code="run_not_found"]'));
    },
  },
];
