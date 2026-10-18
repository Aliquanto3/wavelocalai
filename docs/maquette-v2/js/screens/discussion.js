// Discussion, `#/documents` (UX-DR8, UX-DR10, UX-DR11, UX-DR17, UX-DR19, UX-DR23, stories 4.4 à 4.8) :
// écran de l'Assistant documentaire, à l'état livré. Repris du Chat libre (js/screens/chat-libre.js),
// branché sur le simulateur (js/sim/sim.js, run `rag`).
//
// - En-tête « N documents · M extraits », sélecteur de modèle sur le défaut `rag` (et sa raison),
//   « Réglages avancés » repliés (stratégie, nombre d'extraits, reclassement), champ « Posez une
//   question à vos documents ».
// - Les sources arrivent AVANT le premier token (événement `sources`) et remplissent le panneau
//   (à droite dès 1 024 px, dessous et replié en deçà). `retrieval_step` nomme l'étape en cours
//   dans `wl-run-status` ; le pied de réponse ajoute « Recherche » et « Génération ».
// - Citations : seuls les marqueurs [n] confirmés par l'événement `citations` deviennent des boutons ;
//   les survoler ou les focaliser met la source en évidence, et inversement ; un clic ouvre l'extrait.
//   Sans `citations`, le texte du modèle reste tel quel : le front ne fabrique aucun marqueur.
// - Masqué (on change d'écran), l'écran détache son flux ; au retour il reprend après le dernier `seq`.
// - Commande refusée avant le run (comme un 4xx) : `run_busy` rejoint le run actif ; `ram_guard`,
//   `ollama_down`, `cloud_not_allowed` affichent l'erreur et gardent la question dans le champ.
//
// Contournements locaux (composants communs manquants) : `wl-run-status` ne connaît pas
// `retrieval_step` (on réécrit le libellé de son étape), `wl-chat-thread` n'a pas de pied « Recherche /
// Génération » (on l'ajoute après `end()`), `wl-source-panel` est dans documents-commun.js.

import { errorEnvelope } from "../core/errors.js";
import { element } from "../core/dom.js";
import { formatDuration } from "../core/format.js";
import { plural, t } from "../core/i18n.js";
import { setMaquette, store } from "../core/store.js";
import { findModel, modelDefaults } from "../sim/modeles.js";
import { sim } from "../sim/sim.js";
import { setOllamaDown } from "../sim/systeme.js";
import {
  baseCounts,
  chunksLabel,
  createSourcePanel,
  documentsLabel,
  ensureBase,
  getBase,
  pause,
  prepare,
  setBasePreset,
  subscribeBase,
  updateBase,
  waitUntil,
} from "./documents-commun.js";

let counter = 0;
let view = null; // l'instance montée, pour les scénarios

const STRATEGIES = ["naive", "hyde", "self_rag"];

function metricNode(label, value) {
  const node = document.createElement("wl-metric");
  node.setAttribute("label", label);
  node.setAttribute("value", value);
  return node;
}

export async function mount(host, ctx) {
  await prepare();
  const uid = `discussion-${++counter}`;
  const [data] = await Promise.all([ctx.data("discussion.json"), ensureBase()]);

  // --- Structure -------------------------------------------------------------------------
  const guard = ctx.states.ollamaGuard();

  const summaryText = element("strong", "docs-summary-count");
  const baseLink = element("a", "docs-summary-link", t("discussion.base_link"));
  baseLink.href = "#/documents/base";
  const summary = element("p", "docs-summary");
  summary.append(summaryText, baseLink);
  const indexingNote = element("p", "help docs-indexing-note");

  const picker = document.createElement("wl-model-picker");
  picker.setAttribute("purpose", "rag");
  picker.setAttribute("label", t("components.picker.label"));
  const cloudNote = element("div", "docs-cloud-note");

  // Réglages avancés (repliés) : stratégie, nombre d'extraits, reclassement.
  const strategy = element("select", "docs-select");
  strategy.id = `${uid}-strategy`;
  for (const key of STRATEGIES) {
    const option = element("option", "", t(`discussion.strategy_${key}`));
    option.value = key;
    strategy.append(option);
  }
  const strategyLabel = element("label", "docs-field-label", t("discussion.strategy"));
  strategyLabel.htmlFor = strategy.id;
  const strategyHelp = element("p", "help", t("discussion.strategy_help"));
  strategyHelp.id = `${uid}-strategy-help`;
  strategy.setAttribute("aria-describedby", strategyHelp.id);
  const topK = element("input", "docs-number");
  topK.type = "number";
  topK.id = `${uid}-topk`;
  Object.assign(topK, { min: "1", max: "5", step: "1" });
  const topKLabel = element("label", "docs-field-label", t("discussion.top_k"));
  topKLabel.htmlFor = topK.id;
  const topKHelp = element("p", "help", t("discussion.top_k_help"));
  topKHelp.id = `${uid}-topk-help`;
  topK.setAttribute("aria-describedby", topKHelp.id);
  const rerankLine = element("p", "docs-rerank");
  const advanced = element("details", "docs-advanced");
  const advancedBody = element("div", "docs-advanced-body");
  const strategyField = element("div", "docs-field");
  strategyField.append(strategyLabel, strategy, strategyHelp);
  const topKField = element("div", "docs-field");
  topKField.append(topKLabel, topK, topKHelp);
  advancedBody.append(strategyField, topKField, rerankLine);
  advanced.append(element("summary", "", t("discussion.advanced")), advancedBody);

  const settings = element("div", "docs-chat-settings");
  const pickerColumn = element("div", "docs-chat-picker");
  pickerColumn.append(picker, cloudNote);
  settings.append(pickerColumn, advanced);

  const emptyBase = element("div", "docs-empty");
  const empty = element("p", "help docs-chat-empty", t("discussion.empty_thread"));
  const thread = document.createElement("wl-chat-thread");
  const status = document.createElement("wl-run-status");
  status.setAttribute("driven", "");
  const firstLoad = element("p", "help docs-chat-first-load", t("discussion.first_load"));
  firstLoad.hidden = true;
  const notices = element("div", "docs-chat-notices");
  const error = document.createElement("wl-error");
  error.setAttribute("alert", "");
  const panel = createSourcePanel({ prefix: "docs.sources" });
  panel.root.classList.add("docs-chat-sources");

  const input = element("textarea", "docs-input");
  input.id = `${uid}-message`;
  input.rows = 3;
  input.setAttribute("aria-describedby", `${uid}-keys`);
  const inputLabel = element("label", "docs-input-label", t("discussion.question"));
  inputLabel.htmlFor = input.id;
  const keys = element("p", "help", t("discussion.keys"));
  keys.id = `${uid}-keys`;
  const send = element("button", "btn btn-primary", t("discussion.send"));
  send.type = "submit";
  const clear = element("button", "btn", t("discussion.clear"));
  clear.type = "button";
  const actions = element("div", "docs-actions");
  actions.append(send, clear);
  const reason = element("p", "help docs-chat-reason");
  reason.id = `${uid}-reason`;
  const composer = element("form", "docs-chat-composer");
  composer.append(inputLabel, input, keys, actions, reason);

  const layout = element("div", "docs-chat-layout");
  layout.append(empty, thread, status, firstLoad, notices, error, panel.root, composer);

  host.replaceChildren(
    element("h1", "", ctx.route.title),
    ctx.tabs(),
    element("p", "lead", t("discussion.lead")),
    guard,
    summary,
    indexingNote,
    settings,
    emptyBase,
    layout,
  );

  // --- État ------------------------------------------------------------------------------
  let run = null;
  let attachment = null;
  let lastSeq = 0;
  let answer = null;
  let current = null; // la réponse en cours : { tag, name, origin, text, thought, sources, citations, metrics }
  let displayed = null; // la réponse dont le panneau montre les sources
  let lastMessage = "";
  let dirty = false; // réglages avancés modifiés ici : la Base documentaire ne les écrase plus
  const answers = [];
  const loaded = new Set();
  let wasHidden = host.hidden;

  const running = () => run !== null;

  function readSettings() {
    const value = Number(topK.value);
    return { strategy: strategy.value, top_k: Number.isFinite(value) ? Math.min(5, Math.max(1, Math.round(value))) : 3 };
  }

  function syncSettings(base) {
    if (!dirty) {
      strategy.value = base.settings.strategy;
      topK.value = String(base.settings.top_k);
    }
    rerankLine.textContent = base.reranker.available
      ? t("discussion.rerank_on", { model: base.reranker.model })
      : t("discussion.rerank_off", { reason: base.reranker.reason });
  }

  function render() {
    const base = getBase();
    const counts = baseCounts(base);
    const hasDocs = counts.documents > 0;
    const hasThread = !thread.empty;
    summaryText.textContent = `${documentsLabel(counts.documents)} · ${chunksLabel(counts.chunks)}`;
    indexingNote.hidden = counts.indexing === 0;
    if (counts.indexing) indexingNote.textContent = plural("discussion.indexing", counts.indexing, { count: counts.indexing });
    syncSettings(base);

    // Base sans document prêt : un message mène à la Base documentaire (UX-DR17).
    const blocked = !hasDocs && !hasThread;
    emptyBase.hidden = !blocked;
    if (blocked) {
      emptyBase.replaceChildren(
        counts.indexing
          ? ctx.states.emptyState({ title: t("discussion.indexing_only_title"), text: t("discussion.indexing_only_text"), level: 2, iconName: "info" })
          : ctx.states.emptyState({
              title: t("discussion.empty_title"),
              text: t("discussion.empty_text"),
              action: { label: t("discussion.empty_action"), href: "#/documents/base" },
              level: 2,
              iconName: "description",
            }),
      );
    }
    empty.hidden = blocked || hasThread;
    thread.hidden = blocked;
    panel.root.hidden = blocked;

    const busy = running();
    send.disabled = busy || !hasDocs;
    clear.disabled = busy;
    clear.hidden = !hasThread;
    const note = !hasDocs ? t("discussion.needs_base") : busy && hasThread ? t("discussion.busy_reason") : "";
    reason.textContent = note;
    reason.hidden = !note;
    if (note) send.setAttribute("aria-describedby", reason.id);
    else send.removeAttribute("aria-describedby");
  }

  function say(text, tone = "info") {
    notices.replaceChildren(ctx.states.notice(text, { tone }));
  }

  function updateCloudNote() {
    const model = picker.selected;
    cloudNote.replaceChildren();
    if (model?.origin === "cloud") cloudNote.append(ctx.states.notice(t("discussion.cloud_warning", { name: model.name }), { tone: "warning" }));
  }

  // wl-run-status ne connaît pas `retrieval_step` : on réécrit le libellé de son étape.
  function setStage(text) {
    const node = status.querySelector(".wl-run-stage");
    if (node && node.textContent !== text) node.textContent = text;
  }

  function ensureAnswer(tag) {
    if (!answer) {
      const name = current?.name ?? tag ?? "";
      answer = thread.beginAnswer({ name, origin: current?.origin ?? "unknown" });
      current ??= { tag, name, origin: "unknown", text: "", thought: "", sources: [], citations: [] };
      current.node = answer;
      answers.push(current);
    }
    return answer;
  }

  // --- Sources et citations --------------------------------------------------------------
  function markers(record) {
    return [...(record?.node?.body.querySelectorAll(".docs-cite") ?? [])];
  }

  function showSources(record) {
    if (displayed === record) return;
    displayed = record;
    panel.setSources(record.sources);
    for (const other of answers) other.showButton?.setAttribute("aria-pressed", String(other === record));
  }

  function highlight(record, n) {
    panel.highlight(n);
    for (const marker of markers(record)) marker.classList.toggle("is-linked", n !== null && Number(marker.dataset.n) === n);
  }

  // Inverse : survoler ou focaliser une source met ses marqueurs en évidence.
  panel.onLink = (n) => {
    for (const marker of markers(displayed)) marker.classList.toggle("is-linked", n !== null && Number(marker.dataset.n) === n);
  };

  // Seuls les marqueurs confirmés par `citations` deviennent des boutons.
  function decorate(record) {
    const valid = new Map((record.citations ?? []).map((citation) => [citation.marker, citation.n]));
    if (!valid.size || !record.node) return;
    const walker = document.createTreeWalker(record.node.body, NodeFilter.SHOW_TEXT);
    const texts = [];
    while (walker.nextNode()) texts.push(walker.currentNode);
    for (const node of texts) {
      const parts = node.data.split(/(\[\d+\])/);
      if (parts.length === 1) continue;
      const fragment = document.createDocumentFragment();
      for (const part of parts) {
        const found = /^\[(\d+)\]$/.exec(part);
        const n = found ? valid.get(Number(found[1])) : undefined;
        const source = n === undefined ? null : record.sources.find((candidate) => candidate.n === n);
        if (!source) {
          if (part) fragment.append(part);
          continue;
        }
        // Nom accessible : le texte visible « [1] » d'abord, puis la source (WCAG 2.5.3).
        const marker = element("button", "docs-cite", part);
        marker.type = "button";
        marker.dataset.n = String(n);
        marker.append(element("span", "sr-only", ` ${t("discussion.cite_label", { n, document: source.document, page: source.page })}`));
        const enter = () => {
          showSources(record);
          highlight(record, n);
        };
        const leave = () => highlight(record, null);
        marker.addEventListener("mouseenter", enter);
        marker.addEventListener("mouseleave", leave);
        marker.addEventListener("focus", enter);
        marker.addEventListener("blur", leave);
        marker.addEventListener("click", () => {
          showSources(record);
          panel.open(n);
        });
        fragment.append(marker);
      }
      node.replaceWith(fragment);
    }
  }

  // Pied de réponse : « Recherche » et « Génération » à part (UX-DR23), puis les sources de cette réponse.
  function completeAnswer(record, finalStatus) {
    const result = record.metrics;
    if (result && finalStatus === "ok") {
      if (typeof result.search_s === "number") record.node.foot.append(metricNode(t("discussion.search"), formatDuration(result.search_s)));
      if (typeof result.eval_s === "number") record.node.foot.append(metricNode(t("discussion.generation"), formatDuration(result.eval_s)));
    }
    decorate(record);
    if (record.sources.length) {
      const button = element("button", "btn docs-show-sources", t("discussion.show_sources"));
      button.type = "button";
      button.setAttribute("aria-label", t("discussion.show_sources_for", { name: record.name }));
      button.setAttribute("aria-pressed", String(displayed === record));
      button.addEventListener("click", () => showSources(record));
      record.showButton = button;
      record.node.foot.append(button);
    }
    // Le bouton ne sert qu'à partir de la deuxième réponse : avec une seule, le panneau la montre déjà.
    for (const other of answers) if (other.showButton) other.showButton.hidden = answers.length < 2;
  }

  function finish(finalStatus, payload = {}) {
    ensureAnswer(null).end({ status: finalStatus });
    firstLoad.hidden = true;
    if (payload.error) error.error = payload.error;
    completeAnswer(current, finalStatus);
    attachment?.close();
    run = null;
    attachment = null;
    answer = null;
    current = null;
    render();
  }

  // --- Flux ------------------------------------------------------------------------------
  const forward = (_data, envelope) => status.feed(envelope);
  const handlers = {
    "*": (_data, envelope) => {
      lastSeq = envelope.seq;
    },
    run_started: (payload, envelope) => {
      ensureAnswer(Array.isArray(payload?.models) ? payload.models[0] : null);
      forward(payload, envelope);
    },
    retrieval_step: (payload) => setStage(t(`discussion.step_${payload.step}`)),
    sources: (payload) => {
      ensureAnswer(null);
      current.sources = payload.sources;
      displayed = current;
      panel.setSources(payload.sources);
      setStage(t("components.run_status.generating"));
    },
    model_loading: (payload, envelope) => {
      firstLoad.hidden = false;
      forward(payload, envelope);
    },
    model_loaded: (payload, envelope) => {
      firstLoad.hidden = true;
      loaded.add(payload.tag);
      forward(payload, envelope);
    },
    token: (payload, envelope) => {
      ensureAnswer(payload?.lane).token(payload?.text, payload?.channel);
      if (payload?.channel === "thought") current.thought += payload.text;
      else current.text += payload.text;
      forward(payload, envelope);
    },
    citations: (payload) => {
      ensureAnswer(null);
      current.citations = payload.citations;
    },
    metrics: (payload) => {
      ensureAnswer(payload?.lane).metrics(payload);
      current.metrics = payload;
    },
    run_ended: (payload, envelope) => {
      forward(payload, envelope);
      finish(payload?.status ?? "error", payload ?? {});
    },
  };

  function follow(simRun, { after = 0 } = {}) {
    run = simRun;
    lastSeq = after;
    status.runId = simRun.id;
    attachment = simRun.attach(handlers, { after });
    render();
  }

  // --- Actions ---------------------------------------------------------------------------
  function varsFor(model, options = {}) {
    const now = readSettings();
    const chosen = options.strategy ?? now.strategy;
    const base = getBase();
    const sources = data.sources.slice(0, now.top_k);
    const withCitations = options.citations !== false && sources.length >= 3;
    const key = data.metrics[model.tag] ? model.tag : model.origin === "cloud" ? "gpt-5-mini" : "default_local";
    const metrics = { lane: model.tag, ...data.metrics[key], origin: model.origin };
    return {
      tag: model.tag,
      strategy: chosen,
      plain: chosen !== "hyde",
      hyde: chosen === "hyde",
      self_rag: chosen === "self_rag",
      rerank: base.reranker.available,
      top_k: now.top_k,
      sources,
      loading: model.origin === "local" && !loaded.has(model.tag),
      load_s: metrics.load_s,
      thought_on: Boolean(model.reasoning),
      thought: model.reasoning ? data.answer.thought : "",
      answer: withCitations ? data.answer.text : data.answer.text_plain,
      has_citations: withCitations,
      citations: withCitations ? data.citations : [],
      tps: metrics.tps,
      metrics,
      error: options.error
        ? errorEnvelope(options.error, { detail: model.provider_name ? { provider: model.provider, provider_name: model.provider_name } : {} })
        : null,
    };
  }

  async function submit(options = {}) {
    if (running()) return null;
    if (baseCounts(getBase()).documents === 0) {
      input.focus();
      return null;
    }
    const message = input.value;
    if (!message.trim()) {
      input.focus();
      return null;
    }
    error.error = null;
    notices.replaceChildren();
    const model = picker.selected;
    if (!model) {
      error.error = { code: "no_model", message: t("discussion.no_model"), action: t("discussion.no_model_action") };
      return null;
    }
    // Ce que `POST /api/rag/runs` refuserait avant de créer le run.
    const refused = sim.precheck({ origin: model.origin, kind: "rag", model });
    if (refused?.code === "run_busy") {
      const other = sim.get(refused.detail.run_id);
      const joined = (await findModel(other.options.vars?.tag)) ?? model;
      current = { tag: joined.tag, name: joined.name, origin: joined.origin, text: "", thought: "", sources: [], citations: [] };
      say(t("discussion.joined"));
      follow(other);
      return run;
    }
    if (refused) {
      error.error = refused; // la question reste dans le champ (garde-fou mémoire compris)
      return null;
    }
    lastMessage = message;
    thread.addUserMessage(message);
    input.value = "";
    current = { tag: model.tag, name: model.name, origin: model.origin, text: "", thought: "", sources: [], citations: [] };
    answer = thread.beginAnswer({ name: model.name, origin: model.origin });
    current.node = answer;
    answers.push(current);
    panel.clear();
    displayed = null;
    const simRun = sim.play(options.script ?? "discussion-reponse", null, {
      vars: varsFor(model, options),
      kind: "rag",
      origin: model.origin,
      module: "rag",
      speed: options.speed,
    });
    follow(simRun);
    return simRun;
  }

  function clearConversation() {
    if (running()) return;
    thread.clear();
    answers.length = 0;
    displayed = null;
    panel.clear();
    status.runId = null;
    error.error = null;
    say(t("discussion.cleared"), "success");
    render();
    input.focus();
  }

  composer.addEventListener("submit", (event) => {
    event.preventDefault();
    submit();
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      submit();
    }
  });
  clear.addEventListener("click", clearConversation);
  for (const field of [strategy, topK]) field.addEventListener("input", () => (dirty = true));
  picker.addEventListener("wl-model-change", updateCloudNote);

  error.addEventListener("wl-error-action", async (event) => {
    const id = event.detail.id;
    if (id === "retry") {
      error.error = null;
      if (!input.value) input.value = lastMessage;
      submit();
    } else if (id === "allow_cloud") {
      store.set({ allowCloud: true });
      error.error = null;
      say(t("states.cloud_allowed"), "success");
    } else if (id === "use_local" || id === "choose_other") {
      const defaults = await modelDefaults("rag", false).catch(() => ({ tags: [] }));
      if (defaults.tags[0]) picker.value = defaults.tags[0];
      error.error = null;
    } else if (id === "smaller") {
      const suggested = error.error?.detail?.suggested_model;
      const model = suggested ? await findModel(suggested) : null;
      if (model) picker.value = model.tag;
      setMaquette({ ramGuard: false });
      error.error = null;
      say(t("discussion.smaller", { name: model?.name ?? suggested ?? "" }), "success");
    } else if (id === "unload") {
      setMaquette({ ramGuard: false });
      error.error = null;
      say(t("discussion.unloaded"), "success");
    }
  });

  // --- Écran masqué puis revu (reprise par `?after=<seq>`) --------------------------------
  const visibility = new MutationObserver(() => {
    if (host.hidden === wasHidden) return;
    wasHidden = host.hidden;
    if (wasHidden) {
      thread.suspend();
      attachment?.close();
      attachment = null;
    } else {
      thread.resume();
      if (running()) attachment = run.attach(handlers, { after: lastSeq });
    }
  });
  visibility.observe(host, { attributes: true, attributeFilter: ["hidden"] });
  const unsubscribe = subscribeBase(() => render());

  view = {
    host,
    picker,
    input,
    thread,
    status,
    panel,
    advanced,
    topK,
    error,
    submit,
    get run() {
      return run;
    },
    get answerText() {
      return current?.text ?? "";
    },
    get stage() {
      return status.querySelector(".wl-run-stage")?.textContent ?? "";
    },
    whenPickerReady: () => waitUntil(() => picker.selected !== null || picker.querySelector("wl-error:not([hidden])"), 5000),
    setStrategy(value) {
      strategy.value = value;
      dirty = true;
    },
    // Un run lancé depuis un autre onglet (409) : joué, mais non suivi par cet écran.
    startElsewhere(model) {
      return sim.play("discussion-reponse", null, { vars: varsFor(model), kind: "rag", origin: model.origin, module: "rag" });
    },
    // Conversation rouverte (GET /api/conversations/{id}) : rendue d'un coup, sans flux.
    reopen() {
      const first = data.sources.slice(0, 3);
      const turns = [
        { question: data.default_question, text: data.answer.text, sources: first, citations: data.citations, thought: data.answer.thought },
        { question: data.second_question, ...data.conversation.second_answer, thought: "" },
      ];
      for (const turn of turns) {
        thread.addUserMessage(turn.question);
        const record = { tag: "qwen3.6:7b", name: "Qwen 3.6 7B", origin: "local", text: turn.text, thought: turn.thought, sources: turn.sources, citations: turn.citations };
        record.node = thread.beginAnswer({ name: record.name, origin: record.origin });
        if (turn.thought) record.node.token(turn.thought, "thought");
        record.node.token(turn.text, "answer");
        record.metrics = { lane: record.tag, ...data.metrics["qwen3.6:7b"] };
        record.node.metrics(record.metrics);
        record.node.end({ status: "ok" });
        answers.push(record);
        completeAnswer(record, "ok");
      }
      showSources(answers[answers.length - 1]);
      say(t("discussion.reopened"));
      render();
    },
    focusMarker(n) {
      markers(answers[answers.length - 1]).find((marker) => Number(marker.dataset.n) === n)?.focus();
    },
  };

  syncSettings(getBase());
  render();
  updateCloudNote();
  return () => {
    view = null;
    unsubscribe();
    visibility.disconnect();
    guard.dispose?.();
    attachment?.close();
  };
}

// --- Scénarios ----------------------------------------------------------------------------

// Repart de l'état d'ouverture, pose la base attendue, attend le sélecteur, applique `setup`.
async function fresh(ctx, { base = "complet", setup = () => {} } = {}) {
  await ctx.reset();
  await setBasePreset(base);
  setup();
  await waitUntil(() => view !== null);
  await view.whenPickerReady();
}

async function choose(tag) {
  await waitUntil(() => view.picker.knows(tag), 5000);
  view.picker.value = tag;
}

async function ask(ctx, { model, question, ...options } = {}) {
  if (model) await choose(model);
  const data = await ctx.data("discussion.json");
  view.input.value = question ?? data.default_question;
  return view.submit(options);
}

const untilTokens = (count = 80) => waitUntil(() => view.answerText.length >= count);
const untilDone = (simRun) => simRun?.done ?? Promise.resolve();

export const scenarios = [
  {
    id: "base-vide",
    label: "Base vide : un message mène à la Base documentaire",
    run: (ctx) => fresh(ctx, { base: "vide" }),
  },
  {
    id: "aucun-message",
    label: "Base prête, aucun message (12 documents, 340 extraits)",
    run: (ctx) => fresh(ctx),
  },
  {
    id: "question-avec-sources",
    label: "Question, premier chargement, réponse et « 3 sources utilisées » (Flow 2)",
    async run(ctx) {
      await fresh(ctx, { base: "atelier" });
      await untilDone(await ask(ctx));
    },
  },
  {
    id: "ouvrir-une-source",
    label: "Ouvrir la source 1 : le paragraphe de la note, passage surligné (Flow 2)",
    async run(ctx) {
      await fresh(ctx, { base: "atelier" });
      await untilDone(await ask(ctx));
      view.panel.open(1);
      await waitUntil(() => view.panel.root.querySelector(".docs-source-mark"));
    },
  },
  {
    id: "recherche-en-cours",
    label: "Recherche des extraits en cours : les sources ne sont pas encore là",
    async run(ctx) {
      await fresh(ctx);
      await ask(ctx, { speed: 0.03 });
      await waitUntil(() => view.stage.startsWith("Recherche"));
    },
  },
  {
    id: "reponse-en-cours",
    label: "Réponse en cours : sources déjà affichées, débit provisoire, Arrêter",
    async run(ctx) {
      await fresh(ctx);
      await ask(ctx);
      await untilTokens(120);
    },
  },
  {
    id: "premier-chargement-lent",
    label: "Premier chargement lent du modèle (8 à 26 s), sources déjà affichées",
    async run(ctx) {
      await fresh(ctx, { setup: () => setMaquette({ slowLoad: true }) });
      await ask(ctx);
      await waitUntil(() => view.status.dataset.stage === "loading");
    },
  },
  {
    id: "citations",
    label: "Citations vérifiées : [1] focalisé met la source 1 en évidence",
    async run(ctx) {
      await fresh(ctx, { base: "atelier" });
      await untilDone(await ask(ctx));
      view.focusMarker(1);
      await waitUntil(() => view.panel.root.querySelector(".docs-source.is-linked"));
    },
  },
  {
    id: "sans-citations",
    label: "Sans événement « citations » : aucun marqueur dans la réponse",
    async run(ctx) {
      await fresh(ctx, { base: "atelier" });
      await untilDone(await ask(ctx, { citations: false }));
    },
  },
  {
    id: "strategie-hyde",
    label: "Stratégie « Réponse hypothétique d'abord » : « Rédaction d'une réponse hypothétique… »",
    async run(ctx) {
      await fresh(ctx);
      view.advanced.open = true;
      view.setStrategy("hyde");
      await ask(ctx, { speed: 0.1 });
      await waitUntil(() => view.stage.startsWith("Rédaction"));
    },
  },
  {
    id: "strategie-self-rag",
    label: "Stratégie « Vérification de la pertinence » : réponse terminée",
    async run(ctx) {
      await fresh(ctx);
      view.advanced.open = true;
      view.setStrategy("self_rag");
      await untilDone(await ask(ctx));
    },
  },
  {
    id: "reclassement-indisponible",
    label: "Réglages avancés ouverts : « Reclassement indisponible » avec sa raison",
    async run(ctx) {
      await fresh(ctx);
      view.advanced.open = true;
    },
  },
  {
    id: "reclassement-actif",
    label: "Reclassement actif : étape « Reclassement… » avant les sources",
    async run(ctx) {
      await fresh(ctx);
      updateBase((base) => {
        base.reranker.available = true;
      });
      view.advanced.open = true;
      await ask(ctx, { speed: 0.2 });
      await waitUntil(() => view.stage.startsWith("Reclassement"));
    },
  },
  {
    id: "nombre-d-extraits",
    label: "Nombre d'extraits à 5 : cinq sources, dont deux « éloignée »",
    async run(ctx) {
      await fresh(ctx);
      view.advanced.open = true;
      view.topK.value = "5";
      view.topK.dispatchEvent(new Event("input"));
      await untilDone(await ask(ctx));
    },
  },
  {
    id: "arret",
    label: "Arrêter pendant la génération : partiel gardé, sources gardées, « Arrêté »",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await ask(ctx);
      await untilTokens(100);
      await view.status.cancel();
      await untilDone(simRun);
    },
  },
  {
    id: "reponse-cloud",
    label: "Modèle cloud : les extraits quittent le poste (avertissement), CO₂ « estimé »",
    async run(ctx) {
      await fresh(ctx, { setup: () => ctx.store.set({ allowCloud: true }) });
      await untilDone(await ask(ctx, { model: "gpt-5-mini" }));
    },
  },
  {
    id: "conversation-rouverte",
    label: "Conversation rouverte : deux réponses, une source dont le document est supprimé",
    async run(ctx) {
      await fresh(ctx);
      view.reopen();
    },
  },
  {
    id: "indexation-en-cours",
    label: "Un document est encore en cours d'indexation : il n'est pas interrogé",
    async run(ctx) {
      await fresh(ctx, { base: "indexation" });
    },
  },
  {
    id: "reprise-au-retour",
    label: "Aller sur l'Accueil pendant la réponse, puis revenir : reprise sans perte",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await ask(ctx);
      await untilTokens(60);
      await ctx.navigate("/");
      await pause(1500);
      await ctx.navigate("/documents");
      await untilDone(simRun);
    },
  },
  {
    id: "rejoint-409",
    label: "Une réponse tourne déjà (autre onglet) : 409 rejoint",
    async run(ctx) {
      await fresh(ctx);
      const model = await findModel("qwen3.5:2b");
      view.startElsewhere(model);
      await pause(400);
      await ask(ctx);
      await untilTokens(40);
    },
  },
  {
    id: "erreur-ollama-arrete",
    label: "Ollama arrêté : bandeau et erreur à l'envoi, question gardée",
    async run(ctx) {
      await fresh(ctx, { setup: () => setOllamaDown(true) });
      await ask(ctx, { model: "qwen3.5:2b" });
    },
  },
  {
    id: "garde-fou-memoire",
    label: "Garde-fou mémoire : question gardée, besoin chiffré, deux issues",
    async run(ctx) {
      await fresh(ctx, { setup: () => setMaquette({ ramGuard: true }) });
      await ask(ctx, { model: "qwen3.6:7b" });
    },
  },
  {
    id: "cloud-non-autorise",
    label: "Modèle cloud choisi, cloud désactivé : « Autoriser le cloud »",
    async run(ctx) {
      await fresh(ctx);
      ctx.store.set({ allowCloud: true });
      await choose("gpt-5-mini");
      view.input.value = (await ctx.data("discussion.json")).default_question;
      ctx.store.set({ allowCloud: false });
      await view.submit();
    },
  },
  {
    id: "cloud-autorise",
    label: "Cloud désactivé puis activé : « Autoriser le cloud » cliqué, le message le confirme",
    async run(ctx) {
      await fresh(ctx);
      ctx.store.set({ allowCloud: true });
      await choose("gpt-5-mini");
      view.input.value = (await ctx.data("discussion.json")).default_question;
      ctx.store.set({ allowCloud: false });
      await view.submit();
      await waitUntil(() => view.error.querySelector('[data-action="allow_cloud"]'));
      view.error.querySelector('[data-action="allow_cloud"]').click();
      await waitUntil(() => ctx.store.get().allowCloud);
    },
  },
  {
    id: "erreur-cloud-injoignable",
    label: "Fournisseur cloud injoignable après la recherche : sources gardées, erreur nommée",
    async run(ctx) {
      await fresh(ctx, { setup: () => ctx.store.set({ allowCloud: true }) });
      await untilDone(await ask(ctx, { model: "claude-haiku-4-5", script: "discussion-erreur", error: "cloud_unreachable" }));
    },
  },
  {
    id: "aucun-modele",
    label: "Aucun modèle de conversation installé",
    async run(ctx) {
      await fresh(ctx, { setup: () => setMaquette({ noLocalModel: true }) });
    },
  },
  {
    id: "connexion-perdue",
    label: "Connexion perdue pendant la réponse, puis reprise sans doublon",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await ask(ctx);
      await untilTokens(60);
      simRun.cut(4000);
      await pause(1500);
      await untilDone(simRun);
      await waitUntil(() => ctx.store.get().connection.status === "open");
    },
  },
  {
    id: "serveur-redemarre",
    label: "Le serveur redémarre pendant la réponse : « Interrompu »",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await ask(ctx);
      await untilTokens(60);
      sim.restartServer();
      await untilDone(simRun);
    },
  },
];
