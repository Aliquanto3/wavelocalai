// Évaluation de la qualité, `#/documents/evaluation[/<run_id>]` (UX-DR11, UX-DR13, UX-DR14, UX-DR29, AD-6,
// AD-7, AD-9, AD-14, AD-20) : noter la fidélité, la pertinence et la précision du contexte des réponses de
// 1 à 4 modèles à une question ou à un jeu de questions, sur les mêmes extraits de la base documentaire.
//
// - Un seul lecteur du flux du run racine : cet écran (`connectRun`). Il range chaque événement dans
//   `eval-model.js` (aucun calcul de note : le serveur donne chaque note et chaque moyenne) puis
//   redessine, au plus une fois par image, les étapes (`eval-steps.js`), le tableau et la matrice
//   (`eval-results.js`) et le détail ouvert (`eval-detail.js`).
// - L'écran reste en mémoire quand on va ailleurs (le routeur le masque) : masqué, il ferme son flux en
//   gardant le dernier `seq` ; de retour, il le rouvre par `?after=<seq>`, sans perte ni doublon.
// - Rouvrir (`#/documents/evaluation/<run_id>`) rejoue le flux enregistré, sans relancer de modèle
//   (`eval-reopen.js` lit d'abord l'instantané : identifiant inconnu ou évaluation effacée). À
//   `run_ended`, l'instantané règle ce que le flux a dit (moyennes, `partial`, notes non produites).
//   Une évaluation arrêtée garde son résultat partiel (D-28), titré, ses cellules en « non évalué ».
// - `409 run_busy` : le run actif est rejoint s'il est une évaluation. `409 rag_base_empty` : l'erreur du
//   serveur s'affiche. `allow_cloud` du store accompagne chaque commande.
// - Les questions saisies ne vivent que dans le brouillon `localStorage` (`core/drafts.js`).

import { api, ApiError } from "../core/api.js";
import { element, icon, moduleTitle } from "../core/dom.js";
import { formatClock, plural } from "../core/format.js";
import { t } from "../core/i18n.js";
import { onSmallerModel, swapModel } from "../core/ram-guard.js";
import { screenTabs } from "../core/screen-tabs.js";
import { connectRun } from "../core/sse.js";
import { store } from "../core/store.js";
import "../components/wl-badge.js";
import "../components/wl-error.js";
import { readSettled } from "./arena-snapshot.js";
import { detailView } from "./eval-detail.js";
import { envelopeOf, formView } from "./eval-form.js";
import { historyView } from "./eval-history.js";
import { createModel } from "./eval-model.js";
import { reopenView } from "./eval-reopen.js";
import { resultsView } from "./eval-results.js";
import { stepsView } from "./eval-steps.js";

const TICK_MS = 250;
const EVENTS = [
  "run_started",
  "eval_questions",
  "judge",
  "lane_status",
  "sources",
  "eval_answer",
  "metrics",
  "eval_metric",
];
let counter = 0;

export function mount(host, params = {}) {
  const uid = `eval-${++counter}`;
  const model = createModel();
  const nameOf = (tag) => form.picker.modelFor(tag)?.name ?? form.judge.modelFor(tag)?.name ?? tag;
  const originOf = (tag) => form.picker.modelFor(tag)?.origin ?? form.judge.modelFor(tag)?.origin ?? "unknown";

  // --- Structure -------------------------------------------------------------------------
  const form = formView(uid);
  const notice = element("p", "chat-notice");
  notice.setAttribute("role", "status");
  notice.hidden = true;
  const error = document.createElement("wl-error");
  error.setAttribute("alert", "");

  const bannerText = element("p", "eval-banner-text");
  bannerText.tabIndex = -1;
  const stop = element("button", "btn eval-stop", t("components.run_status.stop"));
  stop.type = "button";
  stop.setAttribute("aria-keyshortcuts", "Escape");
  const hint = element("span", "help", t("components.run_status.stop_hint"));
  const banner = element("div", "eval-banner");
  banner.hidden = true;
  banner.append(bannerText, stop, hint);

  const asked = element("section", "eval-asked");
  asked.hidden = true;
  const judgeLine = element("div", "eval-judge-info");
  judgeLine.hidden = true;

  const steps = stepsView(uid, nameOf);
  const detail = detailView(uid, { scoreText: (score) => `${score}/100` });
  const results = resultsView(uid, {
    nameOf,
    originOf,
    onOpen: (target) => openDetail(target),
  });
  const run = element("div", "eval-run");
  run.hidden = true;
  run.append(steps.el, results.el, detail.el);
  const past = historyView(uid, (tag) => form.picker.modelFor(tag)?.name);
  const reopen = reopenView(uid, (id) => follow(id));
  const live = element("div", "sr-only");
  live.setAttribute("role", "status");
  live.setAttribute("aria-live", "polite");
  live.setAttribute("aria-atomic", "true");

  host.replaceChildren(
    moduleTitle("description", "docs", t("screens.documents-evaluation")),
    screenTabs("documents", "documents-evaluation"),
    element("p", "lead", t("evaluation.lead")),
    reopen.el,
    form.el,
    notice,
    error,
    banner,
    asked,
    judgeLine,
    run,
    past.el,
    live,
  );

  // --- État ------------------------------------------------------------------------------
  let runId = null; // le run suivi, tant qu'il n'est pas terminé
  let stream = null;
  let pending = false; // commande envoyée, réponse du serveur attendue
  let startMs = null;
  let endMs = null;
  let ticker = null;
  let finalState = null;
  let stopping = false;
  let stopHadFocus = false;
  let frame = 0;
  let ticket = 0; // une lecture tardive d'un run précédent n'écrase pas le courant
  let wasHidden = host.hidden;

  const running = () => runId !== null;
  form.setBusy(() => running() || pending);

  function announce(text) {
    live.textContent = ""; // vider puis remplir : un même texte est de nouveau annoncé
    requestAnimationFrame(() => {
      live.textContent = text;
    });
  }

  // --- Rendu -----------------------------------------------------------------------------
  function elapsed() {
    if (startMs === null) return 0;
    return Math.max(0, ((endMs ?? Date.now()) - startMs) / 1000);
  }

  function renderBanner() {
    banner.hidden = !running() && finalState === null;
    const state = stopping && running() ? "stopping" : (finalState ?? "running");
    const text = t(`evaluation.banner.${state}`, { clock: formatClock(elapsed()) });
    if (bannerText.textContent !== text) bannerText.textContent = text;
    stop.hidden = !running();
    stop.disabled = stopping;
    hint.hidden = !running();
  }

  function renderAsked() {
    const questions = model.state.questions;
    asked.hidden = questions.length === 0;
    if (!questions.length) return;
    if (questions.length === 1) {
      const line = element("p", "eval-asked-line");
      line.append(element("strong", "", `${t("evaluation.asked")} : `), questions[0]);
      asked.replaceChildren(line);
      return;
    }
    const details = element("details", "eval-asked-set");
    details.append(element("summary", "", `${t("evaluation.asked_set")} : ${plural("evaluation.summary.questions", questions.length)}`));
    const list = element("ol", "eval-asked-list");
    list.append(...questions.map((text) => element("li", "", text)));
    details.append(list);
    const open = asked.querySelector("details")?.open ?? false;
    details.open = open;
    asked.replaceChildren(details);
  }

  function renderJudge() {
    const data = model.state.judge;
    judgeLine.hidden = !data;
    if (!data) return;
    const parts = [];
    const alertLine = (iconName, text) => {
      const line = element("p", "eval-judge-alert");
      line.setAttribute("role", "status");
      line.append(icon(iconName), element("span", "", text));
      return line;
    };
    if (!data.model) {
      parts.push(alertLine("warning", t("evaluation.judge_none")));
    } else {
      const who = element("p", "eval-judge-who");
      const kind = document.createElement("wl-badge");
      kind.setAttribute("kind", ["local", "cloud"].includes(data.origin) ? data.origin : "unknown");
      who.append(t("evaluation.judge_current", { name: nameOf(data.model) }), " ", kind);
      parts.push(who);
      if (data.unreliable) parts.push(alertLine("warning", t("evaluation.judge_unreliable")));
      if (model.lanes.includes(data.model)) parts.push(alertLine("info", t("evaluation.judge_is_evaluated")));
    }
    judgeLine.replaceChildren(...parts);
  }

  function render() {
    form.refresh();
    form.el.hidden = running();
    const showRun = model.lanes.length > 0;
    run.hidden = !showRun;
    renderAsked();
    renderJudge();
    steps.render(model);
    results.render(model);
    detail.refresh(model);
    renderBanner();
  }

  function schedule() {
    if (!frame) {
      frame = requestAnimationFrame(() => {
        frame = 0;
        render();
      });
    }
  }

  const clearRun = () => {
    ticket += 1; // la lecture de l'instantané d'un run précédent ne s'applique plus (revue 7.3)
    cancelAnimationFrame(frame);
    frame = 0;
    model.reset();
    steps.reset();
    results.reset();
    detail.hide({ restoreFocus: false });
    results.setOpen(null);
    asked.replaceChildren();
    asked.hidden = true;
    judgeLine.replaceChildren();
    judgeLine.hidden = true;
    run.hidden = true;
    finalState = null;
    startMs = null;
    endMs = null;
  };

  // --- Détail ----------------------------------------------------------------------------
  function describe({ lane, metric }) {
    return t("evaluation.detail.heading", { name: nameOf(lane), metric: t(`evaluation.results.col_${metric}`) });
  }

  function openDetail(target) {
    const same = detail.target && detail.target.lane === target.lane && detail.target.metric === target.metric;
    if (same) return closeDetail();
    detail.show(target, model, describe);
    results.setOpen({ lane: target.lane, metric: target.metric });
    return undefined;
  }

  function closeDetail() {
    detail.hide();
    results.setOpen(null);
  }

  detail.onClose(closeDetail);
  detail.el.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && detail.open) {
      event.preventDefault();
      event.stopPropagation(); // Échap ferme le détail, pas l'évaluation
      closeDetail();
    }
  });

  // --- Flux ------------------------------------------------------------------------------
  async function finish(state) {
    const stopFocused = stopHadFocus || stop === document.activeElement;
    const id = runId;
    finalState = state;
    runId = null;
    stream = null;
    stopping = false;
    clearInterval(ticker);
    ticker = null;
    const mine = ++ticket;
    const snapshot = id ? await readSettled(id, () => mine === ticket) : null;
    if (mine !== ticket) return;
    if (snapshot) model.applySnapshot(snapshot);
    cancelAnimationFrame(frame);
    frame = 0;
    render();
    past.refresh();
    if (stopFocused) bannerText.focus(); // Arrêter s'est masqué
    announce(t(`evaluation.announce.${state}`));
  }

  const handlers = Object.fromEntries(
    EVENTS.map((type) => [
      type,
      (data, envelope) => {
        if (type === "run_started") {
          if (data?.kind !== "eval") {
            // Le run rejoint n'est pas une évaluation : on le dit, sans le suivre.
            stream?.close();
            stream = null;
            runId = null;
            clearRun();
            notice.textContent = t("evaluation.other_run");
            notice.hidden = false;
            render();
            return;
          }
          const started = Date.parse(envelope.ts);
          startMs = Number.isNaN(started) ? Date.now() : Math.min(started, Date.now());
          ticker ??= setInterval(renderBanner, TICK_MS);
        }
        model.apply(type, data);
        schedule();
      },
    ]),
  );
  handlers.run_ended = (data, envelope) => {
    const ended = Date.parse(envelope.ts);
    endMs = Number.isNaN(ended) ? Date.now() : ended;
    startMs ??= endMs;
    if (data?.status === "error") {
      error.error = data?.error ?? { code: "internal", message: t("evaluation.run_failed") };
    }
    model.apply("run_ended", data);
    finish(["ok", "cancelled", "error"].includes(data?.status) ? data.status : "interrupted");
  };

  function openStream(id) {
    stream?.close({ keepSeq: true });
    stream = connectRun(id, handlers, ({ status }) => {
      // Run inconnu ou serveur muet après plusieurs essais, sans `run_ended` : on le dit.
      if (status === "failed" && running()) {
        if (model.lanes.length === 0) {
          error.error = { code: "run_unknown", message: t("evaluation.run_unknown") };
          runId = null;
          stream = null;
          render();
        } else {
          endMs = Date.now();
          model.apply("run_ended", { status: "interrupted" });
          finish("interrupted");
        }
      }
    });
  }

  function follow(id) {
    clearRun();
    runId = id;
    stopping = false;
    stopHadFocus = false;
    if (!host.hidden) openStream(id); // masqué : le flux s'ouvrira au retour (AD-6)
    render();
  }

  // --- Actions ---------------------------------------------------------------------------
  async function submit() {
    if (form.reason()) return;
    const models = form.models();
    const questions = form.questions();
    notice.hidden = true;
    error.error = null;
    reopen.hide();
    const refocus = document.activeElement === form.launch;
    pending = true;
    render();
    try {
      const command = { questions, models, allow_cloud: store.get().allowCloud };
      const chosen = form.chosenJudge();
      if (chosen) command.judge = chosen.tag;
      const started = await api.startEval(command);
      past.refresh();
      follow(started.run_id);
      announce(t("evaluation.announce.started", { count: models.length }));
    } catch (failure) {
      const busy = failure instanceof ApiError ? failure.envelope : null;
      if (failure.status === 409 && busy?.code === "run_busy" && busy.detail?.run_id) {
        clearRun();
        notice.textContent = t("evaluation.joined");
        notice.hidden = false;
        follow(busy.detail.run_id);
      } else {
        error.error = envelopeOf(failure);
        if (busy?.code === "rag_base_empty") readBase();
      }
    } finally {
      pending = false;
      render();
      if (running()) bannerText.focus(); // Lancer s'est retiré avec le formulaire
      else if (refocus) form.launch.focus();
    }
  }

  async function cancel() {
    if (!running() || stopping) return;
    const id = runId;
    stopHadFocus = stop === document.activeElement;
    stopping = true;
    stop.disabled = true;
    renderBanner();
    try {
      await api.cancelRun(id);
    } catch (failure) {
      if (id !== runId) return;
      stopping = false;
      const refocus = stopHadFocus;
      stopHadFocus = false;
      error.error = {
        code: "internal",
        message:
          failure instanceof ApiError && failure.envelope
            ? failure.envelope.message
            : t("components.run_status.cancel_failed"),
      };
      renderBanner();
      if (refocus) stop.focus();
    }
  }

  async function readBase() {
    try {
      const data = await api.documents();
      form.setBase(data?.totals?.documents ?? null);
    } catch {
      form.setBase(null); // base illisible : le serveur refusera, avec son message
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
  form.el.addEventListener("submit", (event) => {
    event.preventDefault();
    submit();
  });
  form.el.addEventListener("input", () => form.refresh());
  form.el.addEventListener("wl-eval-change", () => form.refresh());
  for (const picker of [form.picker, form.judge]) {
    picker.addEventListener("wl-model-change", () => form.refresh());
    picker.addEventListener("wl-models-loaded", () => (form.refresh(), past.render(), schedule()));
  }
  const unwatchSmaller = onSmallerModel(host, (tag, source) => {
    const lane = source.closest("[data-lane]")?.dataset.lane;
    announce(t("evaluation.model_changed", swapModel(form.picker, lane, tag)));
    form.refresh(); // garde-fou mémoire : le modèle proposé remplace celui qui a échoué
  });

  // --- Écran masqué puis revu ------------------------------------------------------------
  const visibility = new MutationObserver(() => {
    if (host.hidden === wasHidden) return;
    wasHidden = host.hidden;
    if (wasHidden) {
      stream?.close({ keepSeq: true });
      stream = null;
    } else {
      readBase();
      if (running()) openStream(runId);
    }
  });
  visibility.observe(host, { attributes: true, attributeFilter: ["hidden"] });

  const unwatchCloud = store.select((state) => state.allowCloud, () => form.refresh());
  readBase();
  past.refresh();
  render();
  if (params.run_id) reopen.open(params.run_id);
  else {
    // Une évaluation en cours (flux système) est rejointe : quitter son adresse ne la perd pas.
    const active = (store.get().runsActive ?? []).find((r) => r?.kind === "eval" && r.run_id);
    if (active) {
      notice.textContent = t("evaluation.joined");
      notice.hidden = false;
      follow(active.run_id);
    }
  }
  return () => {
    unwatchCloud();
    unwatchSmaller();
    visibility.disconnect();
    document.removeEventListener("keydown", onKeydown);
    cancelAnimationFrame(frame);
    clearInterval(ticker);
    stream?.close();
    stream = null;
  };
}
