// Arène, `#/arene/comparer` (UX-DR20, AD-6, AD-9, AD-14, AD-20) : une même question sur 2 à 4
// modèles, une colonne par modèle qui se remplit au fil du flux, avec son statut en texte.
//
// - Un seul lecteur du flux du run racine : cet écran (`connectRun`). Il distribue chaque événement
//   (`lane_status`, `token`, `metrics`, `retry`) à la colonne de sa `lane` (le tag du modèle).
//   Le serveur publie tout sur la racine (AD-5) ; les colonnes se créent depuis `run_started`.
// - L'écran reste en mémoire quand on va ailleurs (le routeur le masque) : masqué, il ferme son flux
//   en gardant le dernier `seq` ; de retour, il rouvre par `?after=<seq>`, sans perte ni doublon.
// - `409 run_busy` : le run actif est rejoint (rejoué depuis le début) s'il est une Arène.
//   `#/arene/comparer/<run_id>` suit de même un run existant. La notation (statut `judging`) est
//   seulement affichée en statut ; la note et les critères sont la story 3.3, le classement la 3.4.
// - Sous 768 px, une colonne à la fois (onglets par modèle) ; sinon toutes, avec défilement
//   horizontal et en-têtes collants, et un mode focus par colonne.
// - `allow_cloud` du store accompagne chaque commande ; le brouillon de la question vit dans
//   `localStorage` seulement (`core/drafts.js`).

import { api, ApiError } from "../core/api.js";
import { element } from "../core/dom.js";
import { loadDraft, saveDraft } from "../core/drafts.js";
import { formatClock } from "../core/format.js";
import { t } from "../core/i18n.js";
import { screenTabs } from "../core/screen-tabs.js";
import { connectRun } from "../core/sse.js";
import { store } from "../core/store.js";

const DRAFT = "arena";
const MIN_MODELS = 2;
const MAX_MODELS = 4;
const SCENARIOS = ["popularize", "extract", "summarize", "translate"];
const TERMINAL = new Set(["done", "timeout", "failed", "cancelled", "interrupted"]);
const NARROW = "(max-width: 767px)";
const TICK_MS = 250;
let counter = 0;

function envelopeOf(error) {
  if (error instanceof ApiError && error.envelope) return error.envelope;
  return { code: "internal", message: t("arena.start_failed") };
}

export function mount(host, params = {}) {
  const uid = `arena-${++counter}`;

  // --- Formulaire ------------------------------------------------------------------------
  const questionLabel = element("label", "chat-input-label", t("arena.question"));
  const question = element("textarea", "chat-input arena-question");
  question.id = `${uid}-question`;
  question.rows = 3;
  questionLabel.htmlFor = question.id;
  question.value = loadDraft(DRAFT) || t("arena.scenario.popularize.prompt");

  const scenarios = element("fieldset", "arena-scenarios");
  scenarios.append(element("legend", "", t("arena.scenarios")));
  const scenarioRow = element("div", "arena-scenario-row");
  for (const id of SCENARIOS) {
    const button = element("button", "btn", t(`arena.scenario.${id}.label`));
    button.type = "button";
    button.addEventListener("click", () => {
      question.value = t(`arena.scenario.${id}.prompt`);
      saveDraft(DRAFT, question.value);
      render();
      question.focus();
    });
    scenarioRow.append(button);
  }
  scenarios.append(scenarioRow, element("p", "help", t("arena.scenarios_help")));

  const picker = document.createElement("wl-model-picker");
  picker.setAttribute("purpose", "arena");
  picker.setAttribute("multi", "");
  picker.setAttribute("label", t("arena.models"));
  const execution = element("p", "help arena-execution", t("arena.execution"));

  const launch = element("button", "btn arena-launch", t("arena.launch"));
  launch.type = "submit";
  launch.setAttribute("aria-describedby", `${uid}-reason`);
  const reason = element("p", "help arena-reason");
  reason.id = `${uid}-reason`;
  const actions = element("div", "chat-actions arena-actions");
  actions.append(launch, reason);
  const form = element("form", "arena-form");
  form.append(questionLabel, question, scenarios, picker, execution, actions);

  const notice = element("p", "chat-notice");
  notice.setAttribute("role", "status");
  notice.hidden = true;
  const error = document.createElement("wl-error");
  error.setAttribute("alert", "");

  // --- Bandeau, question posée, colonnes -----------------------------------------------
  const bannerText = element("p", "arena-banner-text");
  const stop = element("button", "btn arena-stop", t("components.run_status.stop"));
  stop.type = "button";
  stop.setAttribute("aria-keyshortcuts", "Escape");
  const hint = element("span", "help", t("components.run_status.stop_hint"));
  const banner = element("div", "arena-banner");
  banner.hidden = true;
  banner.append(bannerText, stop, hint);

  const asked = element("p", "arena-asked");
  asked.hidden = true;
  const tabs = element("div", "arena-tabs");
  tabs.setAttribute("role", "tablist");
  tabs.setAttribute("aria-label", t("arena.tabs"));
  tabs.hidden = true;
  const lanesEl = element("div", "arena-lanes");
  lanesEl.setAttribute("role", "region");
  lanesEl.setAttribute("aria-label", t("arena.lanes"));
  lanesEl.tabIndex = 0; // une zone qui défile se lit au clavier
  lanesEl.hidden = true;
  const live = element("div", "sr-only");
  live.setAttribute("role", "status");
  live.setAttribute("aria-live", "polite");
  live.setAttribute("aria-atomic", "true");

  host.replaceChildren(
    element("h1", "", t("screens.arena-compare")),
    screenTabs("arena", "arena-compare"),
    element("p", "lead", t("arena.lead")),
    form,
    notice,
    error,
    banner,
    asked,
    tabs,
    lanesEl,
    live,
  );

  // --- État ------------------------------------------------------------------------------
  const lanes = new Map(); // tag -> { el, tab }
  let activeTab = null;
  let runId = null; // le run suivi, tant qu'il n'est pas terminé
  let stream = null;
  let pending = false; // commande envoyée, réponse du serveur attendue
  let startMs = null;
  let endMs = null;
  let ticker = null;
  let finalState = null; // ok | cancelled | interrupted une fois le run terminé
  let stopping = false;
  let wasHidden = host.hidden;
  const narrow = window.matchMedia(NARROW);

  const running = () => runId !== null;
  const count = () => ({
    done: [...lanes.values()].filter(({ el }) => TERMINAL.has(el.status)).length,
    total: lanes.size,
  });

  function announce(text) {
    live.textContent = ""; // vider puis remplir : un même texte est de nouveau annoncé
    requestAnimationFrame(() => {
      live.textContent = text;
    });
  }

  function launchReason() {
    if (running() || pending) return t("arena.busy");
    const n = picker.values.length;
    if (n < MIN_MODELS) return t("arena.need_models");
    if (n > MAX_MODELS) return t("arena.too_many");
    if (!question.value.trim()) return t("arena.need_question");
    return "";
  }

  function render() {
    const why = launchReason();
    launch.disabled = why !== "";
    reason.textContent = why;
    reason.hidden = why === "";
  }

  function elapsed() {
    if (startMs === null) return 0;
    return Math.max(0, ((endMs ?? Date.now()) - startMs) / 1000);
  }

  function renderBanner() {
    banner.hidden = lanes.size === 0 && !running();
    const state = stopping && running() ? "stopping" : (finalState ?? "running");
    const text = t(`arena.banner.${state}`, { ...count(), clock: formatClock(elapsed()) });
    if (bannerText.textContent !== text) bannerText.textContent = text;
    stop.hidden = !running();
    stop.disabled = stopping;
    hint.hidden = !running();
  }

  function startTicker() {
    ticker ??= setInterval(renderBanner, TICK_MS);
  }

  function stopTicker() {
    clearInterval(ticker);
    ticker = null;
  }

  // --- Colonnes --------------------------------------------------------------------------
  function clearLanes() {
    lanes.clear();
    lanesEl.replaceChildren();
    tabs.replaceChildren();
    lanesEl.hidden = true;
    delete lanesEl.dataset.focus;
    asked.hidden = true;
    activeTab = null;
  }

  function tabLabel(tag) {
    const entry = lanes.get(tag);
    return `${entry.name} · ${t(`components.lane.status.${entry.el.status}`)}`;
  }

  function addLane(tag, index) {
    const fiche = picker.modelFor(tag);
    const el = document.createElement("wl-arena-lane");
    el.id = `${uid}-lane-${index}`;
    el.setup({ tag, name: fiche?.name ?? tag, origin: fiche?.origin ?? "unknown" });
    const tab = element("button", "arena-tab");
    tab.type = "button";
    tab.id = `${uid}-tab-${index}`;
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-controls", el.id);
    tab.addEventListener("click", () => selectTab(tag, true));
    tab.addEventListener("keydown", (event) => onTabKey(event, tag));
    lanes.set(tag, { el, tab, name: fiche?.name ?? tag });
    lanesEl.append(el);
    tabs.append(tab);
  }

  function buildLanes(tags) {
    clearLanes();
    tags.forEach(addLane);
    lanesEl.style.setProperty("--lanes", String(tags.length));
    lanesEl.dataset.count = String(tags.length);
    lanesEl.hidden = false;
    activeTab = tags[0] ?? null;
    layout();
  }

  function updateTab(tag) {
    const entry = lanes.get(tag);
    if (entry) entry.tab.textContent = tabLabel(tag);
  }

  function selectTab(tag, focus = false) {
    activeTab = tag;
    layout();
    if (focus) lanes.get(tag)?.tab.focus();
  }

  function onTabKey(event, tag) {
    const order = [...lanes.keys()];
    const at = order.indexOf(tag);
    const moves = { ArrowRight: 1, ArrowLeft: -1 };
    let next = null;
    if (event.key in moves) next = order[(at + moves[event.key] + order.length) % order.length];
    else if (event.key === "Home") next = order[0];
    else if (event.key === "End") next = order[order.length - 1];
    if (next === null) return;
    event.preventDefault();
    selectTab(next, true);
  }

  // Étroit : onglets, une colonne à la fois ; large : toutes les colonnes, en groupes.
  function layout() {
    const tabbed = narrow.matches && lanes.size > 0;
    tabs.hidden = !tabbed;
    for (const [tag, { el, tab }] of lanes) {
      const selected = tag === activeTab;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      tab.textContent = tabLabel(tag);
      if (tabbed) {
        el.setAttribute("role", "tabpanel");
        el.setAttribute("aria-labelledby", tab.id);
        el.removeAttribute("aria-label");
      } else {
        el.setAttribute("role", "group");
        el.removeAttribute("aria-labelledby");
      }
      el.hidden = tabbed && !selected;
    }
  }

  lanesEl.addEventListener("wl-lane-focus", (event) => {
    const { on, tag } = event.detail;
    for (const [other, { el }] of lanes) {
      const focused = on && other === tag;
      el.setFocus(focused);
      el.classList.toggle("is-focus", focused);
    }
    if (on) lanesEl.dataset.focus = tag;
    else delete lanesEl.dataset.focus;
  });

  // --- Flux ------------------------------------------------------------------------------
  const laneOf = (data) => lanes.get(data?.lane)?.el ?? null;

  function finish(state) {
    for (const { el } of lanes.values()) el.interrupt(); // aucune colonne sans état final
    for (const tag of lanes.keys()) updateTab(tag);
    finalState = state;
    runId = null;
    stream = null;
    stopping = false;
    stopTicker();
    renderBanner();
    render();
    const { done, total } = count();
    announce(t(`arena.announce.${state}`, { done, total }));
  }

  const handlers = {
    run_started: (data, envelope) => {
      if (data?.kind !== "arena") {
        // Le run rejoint n'est pas une Arène (un chat en cours) : on le dit, sans le suivre.
        stream?.close();
        stream = null;
        runId = null;
        clearLanes();
        notice.textContent = t("arena.other_run");
        notice.hidden = false;
        render();
        return;
      }
      const tags = Array.isArray(data.models) ? data.models : [];
      if (tags.join("|") !== [...lanes.keys()].join("|")) buildLanes(tags);
      const started = Date.parse(envelope.ts);
      startMs = Number.isNaN(started) ? Date.now() : Math.min(started, Date.now());
      startTicker();
      renderBanner();
    },
    question: (data) => {
      asked.replaceChildren(element("strong", "", `${t("arena.asked")} : `), data?.text ?? "");
      asked.hidden = false;
    },
    lane_status: (data) => {
      const el = laneOf(data);
      if (!el) return;
      el.setStatus(data.status, data.error ?? null);
      updateTab(data.lane);
      renderBanner();
    },
    token: (data) => laneOf(data)?.token(data.text, data.channel),
    retry: (data) => laneOf(data)?.retry(data.reason),
    metrics: (data) => laneOf(data)?.metrics(data),
    run_ended: (data, envelope) => {
      const ended = Date.parse(envelope.ts);
      endMs = Number.isNaN(ended) ? Date.now() : ended;
      startMs ??= endMs;
      const status = data?.status;
      finish(status === "ok" ? "ok" : status === "cancelled" ? "cancelled" : "interrupted");
    },
  };

  function openStream(id) {
    stream?.close({ keepSeq: true });
    stream = connectRun(id, handlers, ({ status }) => {
      // Run inconnu ou serveur muet après plusieurs essais, sans `run_ended` : on le dit.
      if (status === "failed" && running()) {
        if (lanes.size === 0) {
          error.error = { code: "run_unknown", message: t("arena.run_unknown") };
          runId = null;
          stream = null;
          render();
        } else {
          endMs = Date.now();
          finish("interrupted");
        }
      }
    });
  }

  function follow(id) {
    runId = id;
    startMs = null;
    endMs = null;
    finalState = null;
    stopping = false;
    if (!host.hidden) openStream(id); // masqué : le flux s'ouvrira au retour (AD-6)
    render();
    renderBanner();
  }

  // --- Actions ---------------------------------------------------------------------------
  async function submit() {
    if (launchReason()) return;
    const models = picker.values;
    notice.hidden = true;
    error.error = null;
    pending = true; // pas de second envoi (bouton ni Entrée) pendant la requête
    render();
    try {
      const started = await api.startArena({
        models,
        prompt: question.value,
        allow_cloud: store.get().allowCloud,
      });
      buildLanes(models);
      lanesEl.hidden = false;
      asked.replaceChildren(element("strong", "", `${t("arena.asked")} : `), question.value);
      asked.hidden = false;
      follow(started.run_id);
      announce(t("arena.announce.started", { count: models.length }));
    } catch (failure) {
      const busy = failure instanceof ApiError ? failure.envelope : null;
      if (failure.status === 409 && busy?.code === "run_busy" && busy.detail?.run_id) {
        // Un calcul tourne déjà : on le rejoint (si c'est une Arène), sans erreur affichée.
        clearLanes();
        notice.textContent = t("arena.joined");
        notice.hidden = false;
        follow(busy.detail.run_id);
      } else {
        error.error = envelopeOf(failure);
      }
    } finally {
      pending = false;
      render();
    }
  }

  async function cancel() {
    if (!running() || stopping) return;
    const id = runId;
    stopping = true;
    stop.disabled = true;
    renderBanner();
    try {
      await api.cancelRun(id);
    } catch (failure) {
      if (id !== runId) return;
      stopping = false;
      error.error = {
        code: "internal",
        message:
          failure instanceof ApiError && failure.envelope
            ? failure.envelope.message
            : t("components.run_status.cancel_failed"),
      };
      renderBanner();
    }
  }

  const onKeydown = (event) => {
    if (event.key === "Escape" && !event.defaultPrevented && running() && !host.hidden) {
      event.preventDefault();
      cancel();
    }
  };
  document.addEventListener("keydown", onKeydown);
  stop.addEventListener("click", cancel);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submit();
  });
  question.addEventListener("input", () => {
    saveDraft(DRAFT, question.value);
    render();
  });
  picker.addEventListener("wl-model-change", render);
  narrow.addEventListener("change", layout);

  // --- Écran masqué puis revu ------------------------------------------------------------
  const visibility = new MutationObserver(() => {
    if (host.hidden === wasHidden) return;
    wasHidden = host.hidden;
    if (wasHidden) {
      for (const { el } of lanes.values()) el.suspend();
      stream?.close({ keepSeq: true });
      stream = null;
    } else {
      for (const { el } of lanes.values()) el.resume();
      if (running()) openStream(runId);
    }
  });
  visibility.observe(host, { attributes: true, attributeFilter: ["hidden"] });

  render();
  if (params.run_id) follow(params.run_id);
  return () => {
    visibility.disconnect();
    document.removeEventListener("keydown", onKeydown);
    narrow.removeEventListener("change", layout);
    stopTicker();
    stream?.close();
    stream = null;
  };
}
