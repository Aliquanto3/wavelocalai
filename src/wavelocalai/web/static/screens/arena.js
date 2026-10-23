// Arène, `#/arene/comparer` (UX-DR20, AD-6, AD-9, AD-14, AD-20) : une même question sur 2 à 4
// modèles, une colonne par modèle qui se remplit au fil du flux, avec son statut en texte.
//
// - Un seul lecteur du flux du run racine : cet écran (`connectRun`). Il distribue chaque événement
//   (`lane_status`, `token`, `metrics`, `retry`) à la colonne de sa `lane` (le tag du modèle).
//   Le serveur publie tout sur la racine (AD-5) ; les colonnes se créent depuis `run_started`.
// - L'écran reste en mémoire quand on va ailleurs (le routeur le masque) : masqué, il ferme son flux
//   en gardant le dernier `seq` ; de retour, il rouvre par `?after=<seq>`, sans perte ni doublon.
// - `409 run_busy` : le run actif est rejoint (rejoué depuis le début) s'il est une Arène.
//   `#/arene/comparer/<run_id>` suit de même un run existant, ou dit « Résultat introuvable »
//   (`arena-reopen.js`) ; la liste des comparaisons précédentes est `arena-history.js`.
// - Notation (story 3.3) : le panneau « Critères de notation » (`arena-judge.js`) envoie `judge` et
//   `criteria` ; sans juge, Lancer est désactivé (« Choisissez un juge ») et le résumé dit le juge
//   (`arena-summary.js`). L'événement `judge` dit sa fiabilité, `judge_score` pose la note /100 (ou
//   « Non évalué » et sa raison) dans la colonne. Classement, matrice, tableau : `arena-results.js`.
// - Actions d'une comparaison terminée (story 3.6, `arena-actions.js`) : « Relancer » et « Modifier la
//   question » reprennent sa configuration dans le formulaire (`wl-arena-reuse`), « Effacer » vide
//   l'écran (`wl-arena-erased`).
// - Sous 768 px, une colonne à la fois (onglets par modèle) ; sinon toutes, avec défilement
//   horizontal, en-têtes collants et un mode focus par colonne ; « Arrêter ce modèle » (story 9.2,
//   `wl-lane-stop`) arrête une seule lane, notée, à la différence du bandeau « Arrêter » du run.
// - `allow_cloud` du store accompagne chaque commande ; le brouillon vit dans `localStorage` seul.

import { api, ApiError } from "../core/api.js";
import { element, moduleTitle } from "../core/dom.js";
import { saveDraft } from "../core/drafts.js";
import { formatClock } from "../core/format.js";
import { t } from "../core/i18n.js";
import { onSmallerModel, swapModel } from "../core/ram-guard.js";
import { screenTabs } from "../core/screen-tabs.js";
import { connectRun } from "../core/sse.js";
import { store } from "../core/store.js";
import { reuseConfig } from "./arena-actions.js";
import { buildForm, envelopeOf, forgetErased, launchReasonOf, noLocalNotice } from "./arena-form.js";
import { historyView } from "./arena-history.js";
import { judgeInfo, scoreAnnouncer } from "./arena-judge.js";
import { judgeBannerView } from "./arena-judge-banner.js";
import { reopenView } from "./arena-reopen.js";
import { resultsView } from "./arena-results.js";
import { showRunAddress, stopFailure, stopLaneFailure } from "./arena-run.js";
import { judgeRow, modelsRow, summaryView } from "./arena-summary.js";
import { moveTab } from "./arena-tabs.js";

const DRAFT = "arena";
const TERMINAL = new Set(["done", "timeout", "failed", "cancelled", "interrupted"]);
const NARROW = "(max-width: 767px)";
const TICK_MS = 250;
let counter = 0;

export function mount(host, params = {}) {
  const uid = `arena-${++counter}`;

  // --- Formulaire (story 9.7 : grille à deux colonnes, `arena-form.js`) ------------------
  const { form, question, scenarios, picker, execution, judging, launch, reason, actions } = buildForm(
    uid,
    DRAFT,
    () => render(),
  );

  const noLocal = noLocalNotice();

  // Pendant l'exécution, la configuration est remplacée par ce résumé (D-16), jusqu'à `run_ended`.
  const summary = summaryView(uid);

  const notice = element("p", "chat-notice");
  notice.setAttribute("role", "status");
  notice.hidden = true;
  const error = document.createElement("wl-error");
  error.setAttribute("alert", "");

  // --- Bandeau, question posée, colonnes -----------------------------------------------
  const bannerText = element("p", "arena-banner-text");
  bannerText.tabIndex = -1; // reçoit le focus quand Arrêter ou le résumé se retire à la fin
  const stop = element("button", "btn arena-stop", t("components.run_status.stop"));
  stop.type = "button";
  stop.setAttribute("aria-keyshortcuts", "Escape");
  const hint = element("span", "help", t("components.run_status.stop_hint"));
  const banner = element("div", "arena-banner");
  banner.hidden = true;
  banner.append(bannerText, stop, hint);

  const asked = element("p", "arena-asked");
  asked.hidden = true;
  const info = judgeInfo();
  const progress = judgeBannerView(); // bandeau du juge, au-dessus des colonnes (story 9.3)
  const tabs = element("div", "arena-tabs");
  tabs.setAttribute("role", "tablist");
  tabs.setAttribute("aria-label", t("arena.tabs"));
  tabs.hidden = true;
  const lanesEl = element("div", "arena-lanes");
  lanesEl.setAttribute("role", "region");
  lanesEl.setAttribute("aria-label", t("arena.lanes"));
  lanesEl.tabIndex = 0; // une zone qui défile se lit au clavier
  lanesEl.hidden = true;
  const results = resultsView(uid, lanesEl); // classement, matrice, tableau, verdict et actions
  const history = historyView(uid, (tag) => picker.modelFor(tag)?.name);
  const reopen = reopenView(uid, (id) => follow(id));
  const live = element("div", "sr-only");
  live.setAttribute("role", "status");
  live.setAttribute("aria-live", "polite");
  live.setAttribute("aria-atomic", "true");
  const scoreLive = scoreAnnouncer();

  host.replaceChildren(
    moduleTitle("swords", "arena", t("screens.arena-compare")),
    screenTabs("arena", "arena-compare"),
    element("p", "lead", t("arena.lead")),
    reopen.el,
    noLocal.el,
    form,
    summary.el,
    notice,
    error,
    banner,
    asked,
    info.el,
    progress.el,
    tabs,
    lanesEl,
    results.el,
    history.el,
    live,
    scoreLive.el,
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
  let finalState = null; // ok | cancelled | error | interrupted une fois le run terminé
  let stopping = false;
  let stopHadFocus = false; // Arrêter avait le focus avant d'être désactivé (il le perd alors)
  let wasHidden = host.hidden;
  let askedText = ""; // la question du run suivi (événement `question`), pour le résumé
  let askedCriteria = []; // les critères de la question (vide : ceux du serveur)
  let judgeFlags = { single_judge: false, unreliable: false }; // fiabilité des notes (`judge`)
  let runJudge = null; // le juge du run suivi : { name, origin }, ou { none: true } (résumé)
  const narrow = window.matchMedia(NARROW);

  const running = () => runId !== null;
  const count = () => ({ done: [...lanes.values()].filter(({ el }) => TERMINAL.has(el.status)).length, total: lanes.size });

  function announce(text) {
    live.textContent = ""; // vider puis remplir : un même texte est de nouveau annoncé
    requestAnimationFrame(() => {
      live.textContent = text;
    });
  }

  // Aucun modèle local prêt (Ollama arrêté compris : les modèles connus sont listés indisponibles).
  const noLocalReady = () => picker.localReadyCount === 0;
  const launchReason = launchReasonOf({ busy: () => running() || pending, picker, question, judging });

  // Les lignes du résumé affiché pendant l'exécution : question, modèles, juge (D-16).
  const summaryRows = [
    () => [t("arena.summary.question"), askedText],
    () => modelsRow(lanes),
    () => judgeRow(runJudge),
  ];

  // Écran de configuration, ou résumé tant que le run n'a pas dit `run_ended` (D-16). Le focus suit
  // la partie qui se retire : titre du résumé, ou bandeau (à défaut la question) au retour.
  function renderMode() {
    const showSummary = running();
    const leaving = showSummary ? form : summary.el;
    const lost = !leaving.hidden && leaving.contains(document.activeElement);
    form.hidden = showSummary;
    summary.el.hidden = !showSummary;
    asked.hidden = showSummary || askedText === "";
    info.hold(showSummary);
    if (showSummary) summary.render(summaryRows);
    if (lost) focusAfter(showSummary ? summary.title : null);
  }

  const focusAfter = (target) => (target ?? (banner.hidden ? question : bannerText)).focus();

  // Ollama arrêté garde le message du sélecteur ; pendant un run, le résumé a la place.
  function renderNoLocal() {
    const missing = noLocalReady() && picker.ollamaUp && !running();
    noLocal.el.hidden = !missing;
    const cloud = store.get().allowCloud ? "on" : "off";
    if (missing) noLocal.text.textContent = t(`arena.no_local_cloud_${cloud}`);
  }

  function render() {
    const why = launchReason();
    launch.disabled = why !== "";
    reason.textContent = why;
    reason.hidden = why === "";
    renderNoLocal();
    renderMode();
  }

  const elapsed = () => (startMs === null ? 0 : Math.max(0, ((endMs ?? Date.now()) - startMs) / 1000));

  function renderBanner() {
    banner.hidden = lanes.size === 0 && !running();
    const state = stopping && running() ? "stopping" : (finalState ?? "running");
    const text = t(`arena.banner.${state}`, { ...count(), clock: formatClock(elapsed()) });
    if (bannerText.textContent !== text) bannerText.textContent = text;
    stop.hidden = !running();
    stop.disabled = stopping;
    hint.hidden = !running();
  }

  const startTicker = () => (ticker ??= setInterval(renderBanner, TICK_MS));

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
    askedText = "";
    activeTab = null;
    askedCriteria = [];
    judgeFlags = { single_judge: false, unreliable: false };
    runJudge = null;
    info.clear();
    progress.reset();
    scoreLive.clear();
    results.reset();
  }

  function setAsked(text) {
    askedText = text;
    asked.replaceChildren(element("strong", "", `${t("arena.asked")}\u00a0: `), text);
    renderMode();
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
    el.setJudge(judgeFlags);
    const tab = element("button", "arena-tab");
    tab.type = "button";
    tab.id = `${uid}-tab-${index}`;
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-controls", el.id);
    tab.addEventListener("click", () => selectTab(tag, true));
    tab.addEventListener("keydown", (event) => moveTab(event, [...lanes.keys()], tag, (next) => selectTab(next, true)));
    lanes.set(tag, { el, tab, name: fiche?.name ?? tag, origin: fiche?.origin ?? "unknown" });
    lanesEl.append(el);
    tabs.append(tab);
  }

  // Colonnes d'une comparaison rouverte créées avant la liste des modèles : identifiant, puis nom.
  function nameLanes() {
    for (const [tag, entry] of lanes) {
      const fiche = picker.modelFor(tag);
      if (!fiche || (entry.name === fiche.name && entry.origin === fiche.origin)) continue;
      Object.assign(entry, { name: fiche.name, origin: fiche.origin });
      entry.el.setup({ tag, name: fiche.name, origin: fiche.origin });
      updateTab(tag);
    }
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

  // Étroit : onglets, une colonne à la fois ; large : toutes les colonnes, en groupes.
  function layout() {
    const tabbed = narrow.matches && lanes.size > 0;
    tabs.hidden = !tabbed;
    // Onglets : pas de mode focus (son bouton est masqué), sinon l'onglet choisi pourrait être caché.
    if (tabbed && lanesEl.dataset.focus) setFocus(false, null);
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

  function setFocus(on, tag) {
    for (const [other, { el }] of lanes) {
      const focused = on && other === tag;
      el.setFocus(focused);
      el.classList.toggle("is-focus", focused);
    }
    if (on) lanesEl.dataset.focus = tag;
    else delete lanesEl.dataset.focus;
  }

  lanesEl.addEventListener("wl-lane-focus", (event) => setFocus(event.detail.on, event.detail.tag));

  // --- Flux ------------------------------------------------------------------------------
  const laneOf = (data) => lanes.get(data?.lane)?.el ?? null;

  function finish(state) {
    const stopFocused = stopHadFocus || stop === document.activeElement; // Arrêter va se masquer
    for (const { el } of lanes.values()) el.interrupt(); // aucune colonne sans état final
    for (const tag of lanes.keys()) updateTab(tag);
    finalState = state;
    results.end(state, runId); // le classement se fige, l'instantané est lu
    if (state !== "interrupted") showRunAddress(runId); // flux perdu : le run peut durer, on n'y touche pas
    history.refresh();
    runId = null;
    stream = null;
    stopping = false;
    stopTicker();
    progress.end(); // story 9.3 : l'horloge du juge s'arrête avec le run
    renderBanner();
    render();
    if (stopFocused) focusAfter(null);
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
      renderMode();
    },
    question: (data) => {
      setAsked(data?.text ?? "");
      askedCriteria = Array.isArray(data?.criteria) ? data.criteria : [];
    },
    judge: (data) => {
      judgeFlags = { single_judge: data?.single_judge === true, unreliable: data?.unreliable === true };
      for (const { el } of lanes.values()) el.setJudge(judgeFlags);
      const name = data?.model
        ? (judging.picker.modelFor(data.model)?.name ?? picker.modelFor(data.model)?.name ?? data.model)
        : "";
      runJudge = data?.model ? { name, origin: data.origin } : { none: true };
      info.show(data, { name, criteria: askedCriteria });
      progress.setJudge(data, name);
      renderMode();
    },
    judge_progress: (data) => (progress.progress(data, (tag) => lanes.get(tag)?.name), laneOf(data)?.setJudgeProgress(data.phase)), // story 9.3
    judge_score: (data) => {
      const entry = lanes.get(data?.lane);
      progress.score(data); // story 9.3 : le bandeau du juge
      if (!entry) return;
      entry.el.setScore(data);
      scoreLive.add(entry.name, entry.el.score, judgeFlags.unreliable);
    },
    lane_status: (data) => {
      const el = laneOf(data);
      if (!el) return;
      if (data.run_id) el.setRunId(data.run_id); // « Arrêter ce modèle » (story 9.2)
      el.setStatus(data.status, data.error ?? null, data.stopped_reason ?? null);
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
      if (status === "error") {
        // Échec de l'orchestration (AD-5) : la cause du serveur est dite, pas un simple « interrompu ».
        error.error = data?.error ?? { code: "internal", message: t("arena.run_failed") };
      }
      finish(["ok", "cancelled", "error"].includes(status) ? status : "interrupted");
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
    stopHadFocus = false;
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
    const refocus = document.activeElement === launch; // désactivé pendant la requête, il le perd
    pending = true; // pas de second envoi (bouton ni Entrée) pendant la requête
    render();
    try {
      const command = {
        models,
        prompt: question.value,
        criteria: judging.criteria(),
        allow_cloud: store.get().allowCloud,
      };
      const chosenJudge = judging.chosen(); // lu avant l'envoi ; absent : le défaut du serveur
      if (chosenJudge) command.judge = chosenJudge.tag;
      const started = await api.startArena(command);
      buildLanes(models);
      lanesEl.hidden = false;
      setAsked(question.value);
      runJudge = chosenJudge; // le résumé le dit jusqu'à l'événement `judge`
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
      if (running()) summary.title.focus(); // Lancer s'est retiré avec le formulaire
      else if (refocus) launch.focus();
    }
  }

  async function cancel() {
    if (!running() || stopping) return;
    const id = runId;
    stopHadFocus = stop === document.activeElement;
    stopping = true;
    stop.disabled = true;
    renderBanner();
    const failed = await stopFailure(id);
    if (failed === null || id !== runId) return;
    stopping = false;
    const refocus = stopHadFocus;
    stopHadFocus = false;
    error.error = { code: "internal", message: failed };
    renderBanner();
    if (refocus) stop.focus(); // de nouveau actif : il reprend le focus
  }

  lanesEl.addEventListener("wl-lane-stop", async ({ detail: { runId: laneRunId } }) => {
    const failed = laneRunId && (await stopLaneFailure(laneRunId));
    if (failed) error.error = { code: "internal", message: failed };
  });

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
  const unwatchSmaller = onSmallerModel(host, (tag, source) => {
    announce(t("arena.model_changed", swapModel(picker, source.closest("wl-arena-lane")?.tag, tag)));
    render(); // garde-fou mémoire : le modèle proposé remplace celui de la colonne en échec
  });
  picker.addEventListener("wl-model-change", render);
  for (const type of ["wl-model-change", "wl-models-loaded"]) judging.picker.addEventListener(type, render);
  picker.addEventListener("wl-models-loaded", () => (render(), history.render(), nameLanes())); // un modèle local est-il prêt ?
  host.addEventListener("wl-arena-reuse", (event) => reuseConfig(event.detail, { question, picker, judging, launchReason, submit }));
  host.addEventListener("wl-arena-erased", (event) => {
    clearLanes(); forgetErased(question, event.detail?.prompt); // ni à l'écran ni en brouillon
    renderBanner();
    history.refresh(t("arena.actions.erased"));
    focusAfter(null);
  });
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

  const unwatchCloud = store.select((state) => state.allowCloud, render); // rend tout de suite
  history.refresh();
  if (params.run_id) reopen.open(params.run_id);
  return () => {
    unwatchCloud();
    unwatchSmaller();
    visibility.disconnect();
    document.removeEventListener("keydown", onKeydown);
    narrow.removeEventListener("change", layout);
    stopTicker(); progress.reset(); // aucun minuteur après l'écran, celui du juge compris (story 9.3)
    stream?.close();
    stream = null;
  };
}
