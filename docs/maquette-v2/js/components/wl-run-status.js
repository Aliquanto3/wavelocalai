// Repris de la branche feat/v2-ecran-chat (story 1.10) ; flux et annulation : js/sim/sim.js.
// <wl-run-status> : étape nommée d'un run, chronomètre local, bouton Arrêter (UX-DR8, AD-6, AD-20).
//
// `el.runId = "<id>"` (ou l'attribut `run-id`) suit un run par le client SSE unique : « Chargement
// du modèle en mémoire… » (`model_loading`), « Génération… » (`model_loaded`, puis `token`), puis
// l'état final (`run_ended`). Le chronomètre est le seul chiffre calculé ici (AD-20) : il part de
// l'horodatage de `run_started` et s'arrête à `run_ended`. Le bouton Arrêter et la touche Échap
// appellent `POST /api/runs/{id}/cancel` ; le run se termine par son propre `run_ended`.
//
// Événement : `wl-run-ended` (`detail.status`, `detail.error`). Un flux n'est ouvert que pour le
// run suivi et se ferme au retrait du composant de la page. Sans Shadow DOM.
//
// Mode piloté (attribut `driven`) : l'écran lit déjà le flux du run (le dernier `seq` d'un run est
// unique dans le store, deux lecteurs s'écarteraient les événements) ; il passe chaque enveloppe à
// `feed(envelope)`, et `abandon()` dit que le flux est perdu. Aucun flux n'est ouvert ici.
// La touche Échap n'agit que si le composant est à l'écran (un écran gardé en mémoire est masqué).
//
// Étapes nommées tirées du flux (piloté ou non) : `retrieval_step` → « Recherche des extraits… »
// (selon `data.step`), `step` → « Réflexion… » ou « Appel de l'outil … », `approval_required` →
// « En attente de votre validation », `lane_status: judging`, `judge_score`, `eval_metric` →
// « Notation des réponses… ». L'écran peut nommer l'étape lui-même : `setStage(stage, {tool, step,
// agent, label})` (`agent` préfixe « Rédacteur : … », `label` remplace le texte de l'étape).
// Pilotage complet sans enveloppe (agents) : `begin(ts)`, `markStopping()`, `finish(status)`,
// `reset()` ; `stage` rend l'étape courante. Attribut `no-stop` : ni bouton Arrêter ni Échap ;
// propriété `onStop` : fonction appelée par Arrêter et Échap à la place de l'annulation du run.
// Le chronomètre suit la vitesse du simulateur (réglage « vitesse » de la maquette).

import { element } from "../core/dom.js";
import { formatDuration } from "../core/format.js";
import { t } from "../core/i18n.js";
import { store } from "../core/store.js";
import { sim } from "../sim/sim.js";
import "./wl-error.js";

const STAGE_TEXT = {
  starting: "components.run_status.starting",
  loading: "components.run_status.loading",
  generating: "components.run_status.generating",
  thinking: "components.run_status.thinking",
  tool: "components.run_status.tool",
  waiting: "components.run_status.waiting",
  retrieving: "components.run_status.retrieving",
  judging: "components.run_status.judging",
  stopping: "components.run_status.stopping",
  ok: "components.run_status.ok",
  cancelled: "components.run_status.cancelled",
  error: "components.run_status.error",
  interrupted: "components.run_status.interrupted",
};
const FINAL = new Set(["ok", "cancelled", "error", "interrupted"]);
const RETRIEVAL_STEPS = new Set(["search", "hypothetical", "verify", "rerank"]);
const TICK_MS = 250;
const speedOf = () => store.get().maquette.speed || 1;

export class WlRunStatus extends HTMLElement {
  static observedAttributes = ["run-id"];

  #runId = null;
  #stream = null;
  #stage = "starting";
  #vars = {};
  #final = null; // { status, error } une fois le run terminé
  #startMs = null;
  #endMs = null;
  #timer = null;
  #cancelling = false;
  #dom = null;
  #onKeydown = (event) => {
    if (event.key === "Escape" && !event.defaultPrevented && this.running && !this.noStop && !this.closest("[hidden]")) {
      event.preventDefault();
      this.cancel();
    }
  };

  connectedCallback() {
    this.#build();
    document.addEventListener("keydown", this.#onKeydown);
    if (this.#runId) this.#start();
    else this.#render();
  }

  disconnectedCallback() {
    document.removeEventListener("keydown", this.#onKeydown);
    this.#teardown();
  }

  attributeChangedCallback(name, _old, value) {
    if (name === "run-id") this.runId = value;
  }

  get runId() {
    return this.#runId;
  }

  set runId(id) {
    const next = id || null;
    if (next === this.#runId) return;
    this.#teardown();
    this.#runId = next;
    this.#reset();
    if (this.#dom && next) this.#start();
    else if (this.#dom) this.#render();
  }

  // Le run suivi n'est pas terminé.
  get running() {
    return this.#runId !== null && this.#final === null;
  }

  #build() {
    if (this.#dom) return;
    const stage = element("p", "wl-run-stage");
    stage.setAttribute("role", "status");
    stage.tabIndex = -1;
    const timer = element("span", "wl-run-timer");
    timer.setAttribute("role", "timer");
    timer.setAttribute("aria-label", t("components.run_status.elapsed"));
    const stop = element("button", "btn wl-run-stop", t("components.run_status.stop"));
    stop.type = "button";
    stop.setAttribute("aria-keyshortcuts", "Escape");
    stop.addEventListener("click", () => this.cancel());
    const hint = element("span", "help wl-run-hint", t("components.run_status.stop_hint"));
    const error = document.createElement("wl-error");
    error.setAttribute("alert", "");
    this.classList.add("wl-run-status");
    const line = element("div", "wl-run-line");
    line.append(stage, timer, stop, hint);
    this.replaceChildren(line, error);
    this.#dom = { stage, timer, stop, hint, error };
  }

  #reset() {
    this.#stage = "starting";
    this.#vars = {};
    this.#final = null;
    this.#startMs = null;
    this.#endMs = null;
    this.#cancelling = false;
    if (this.#dom) this.#dom.error.error = null;
  }

  #teardown() {
    this.#stream?.close();
    this.#stream = null;
    clearInterval(this.#timer);
    this.#timer = null;
  }

  // Les événements qui font avancer l'étape, que le flux soit ouvert ici ou par l'écran (`feed`).
  #handlers = {
    run_started: (_data, envelope) => {
      if (this.#runId === null || this.#final) {
        // Pilotage sans `runId` (agents), ou nouveau run dans le même composant.
        this.#runId = envelope.run_id ?? "pilote";
        this.#reset();
      }
      const started = Date.parse(envelope.ts);
      this.#startMs = Number.isNaN(started) ? Date.now() : Math.min(started, Date.now());
      this.#timer ??= setInterval(() => this.#renderTimer(), TICK_MS);
      this.#render();
    },
    model_loading: () => this.#setStage("loading"),
    model_loaded: () => this.#setStage("generating"),
    token: () => this.#setStage("generating"),
    retrieval_step: (data) => this.#setStage("retrieving", { step: data?.step }),
    step: (data) => {
      if (data?.duration_s !== null && data?.duration_s !== undefined) return; // fin d'étape
      if (data?.kind === "think") this.#setStage("thinking");
      else if (data?.kind === "tool_call") this.#setStage("tool", { tool: data.tool ?? "" });
      else if (data?.kind === "answer") this.#setStage("generating");
    },
    approval_required: () => this.#setStage("waiting"),
    approval_resolved: () => this.#setStage("thinking"),
    lane_status: (data) => {
      if (data?.status === "judging") this.#setStage("judging");
    },
    judge_score: () => this.#setStage("judging"),
    eval_metric: () => this.#setStage("judging"),
    run_ended: (data, envelope) => this.#end(data ?? {}, envelope),
  };

  get noStop() {
    return this.hasAttribute("no-stop");
  }

  // Étape courante (`starting`, `thinking`, `ok`…).
  get stage() {
    return this.#stage;
  }

  // L'écran nomme l'étape (voir l'en-tête) ; sans effet avant le début ou après la fin du run.
  setStage(stage, vars = {}) {
    if (this.#runId === null) return;
    this.#setStage(Object.hasOwn(STAGE_TEXT, stage) ? stage : "generating", vars);
  }

  // Pilotage sans enveloppe : début du run (horodatage ISO), arrêt demandé, fin, remise à zéro.
  begin(ts = new Date().toISOString()) {
    this.#build();
    this.#teardown();
    this.#runId = null;
    this.#handlers.run_started({}, { ts });
  }

  markStopping() {
    if (!this.running || this.#cancelling) return;
    if (document.activeElement === this.#dom.stop) this.#dom.stage.focus();
    this.#cancelling = true;
    this.#stage = "stopping";
    this.#vars = {};
    this.#render();
  }

  finish(status, error = null) {
    if (this.#runId === null || this.#final) return;
    this.#end({ status, error }, { ts: new Date().toISOString() });
  }

  reset() {
    this.#teardown();
    this.#runId = null;
    this.#reset();
    if (this.#dom) this.#render();
  }

  get driven() {
    return this.hasAttribute("driven");
  }

  // Mode piloté : une enveloppe `{type, data, ts…}` du flux que l'écran lit.
  feed(envelope) {
    if (!this.driven || !envelope || !Object.hasOwn(this.#handlers, envelope.type)) return;
    this.#handlers[envelope.type](envelope.data, envelope);
  }

  // Maquette : affiche une étape figée sans flux (« en cours », « terminé », « arrêté »…), pour le
  // catalogue des états et les scénarios. `seconds` fixe le chronomètre.
  preview(stage, seconds = 0) {
    this.#teardown();
    this.#runId = "apercu";
    this.#reset();
    const now = Date.now();
    this.#startMs = now - seconds * 1000;
    const final = ["ok", "cancelled", "error", "interrupted"].includes(stage);
    if (final) {
      this.#endMs = now;
      this.#final = { status: stage, error: null };
    }
    this.#stage = stage;
    if (!final) this.#timer = setInterval(() => this.#renderTimer(), TICK_MS);
    this.#render();
  }

  // Flux abandonné (run inconnu, ou serveur muet après plusieurs essais) sans `run_ended` :
  // l'état n'est plus suivi, on le dit au lieu de laisser « Génération… » et Arrêter.
  abandon() {
    if (this.#runId !== null && !this.#final) this.#end({ status: "interrupted" }, {});
  }

  #start() {
    this.#render();
    if (this.driven) return;
    this.#stream = sim.attach(this.#runId, this.#handlers);
  }

  #setStage(stage, vars = {}) {
    if (this.#final || this.#cancelling) return;
    if (this.#stage === stage && JSON.stringify(this.#vars) === JSON.stringify(vars)) return;
    this.#stage = stage;
    this.#vars = vars;
    this.#render();
  }

  #end(data, envelope) {
    const ended = Date.parse(envelope.ts);
    this.#endMs = Number.isNaN(ended) ? Date.now() : ended;
    this.#startMs ??= this.#endMs;
    clearInterval(this.#timer);
    this.#timer = null;
    const status = FINAL.has(data.status) ? data.status : "error";
    this.#final = { status, error: data.error ?? null };
    this.#stage = status;
    this.#vars = {};
    const hadFocus = [this.#dom.stop, this.#dom.stage].includes(document.activeElement);
    this.#render();
    if (hadFocus) this.#dom.stage.focus(); // le bouton disparaît : le focus ne se perd pas
    this.dispatchEvent(
      new CustomEvent("wl-run-ended", { bubbles: true, detail: { status, error: this.#final.error } }),
    );
  }

  // Arrêter : demande l'annulation ; l'état final arrive par le flux (`run_ended`).
  async cancel() {
    if (!this.running || this.#cancelling) return;
    if (typeof this.onStop === "function") {
      this.onStop(); // l'écran arrête le run et appelle markStopping()
      return;
    }
    const runId = this.#runId;
    this.#cancelling = true;
    this.#stage = "stopping";
    // Le bouton passe en `disabled` : le focus va sur l'étape au lieu de se perdre.
    if (document.activeElement === this.#dom.stop) this.#dom.stage.focus();
    this.#render();
    try {
      await sim.cancel(runId);
    } catch (error) {
      if (runId !== this.#runId || this.#final) return;
      this.#cancelling = false;
      this.#stage = "generating";
      this.#dom.error.error =
        error?.envelope
          ? error.envelope
          : { code: "internal", message: t("components.run_status.cancel_failed") };
      this.#render();
    }
  }

  // Secondes simulées : temps réel multiplié par la vitesse du simulateur.
  #elapsedSeconds() {
    if (this.#startMs === null) return 0;
    const end = this.#endMs ?? Date.now();
    return Math.max(0, Math.floor(((end - this.#startMs) / 1000) * speedOf()));
  }

  #stageText() {
    const vars = this.#vars;
    let text = vars.label;
    if (!text && this.#stage === "retrieving" && RETRIEVAL_STEPS.has(vars.step)) {
      text = t(`components.run_status.retrieval.${vars.step}`);
    }
    text ||= t(STAGE_TEXT[this.#stage], vars);
    if (vars.agent && !FINAL.has(this.#stage)) text = t("components.run_status.with_agent", { agent: vars.agent, text });
    return text;
  }

  #renderTimer() {
    this.#dom.timer.textContent = formatDuration(this.#elapsedSeconds());
  }

  #render() {
    const { stage, stop, hint, error } = this.#dom;
    this.hidden = this.#runId === null;
    stage.textContent = this.#stageText();
    this.dataset.stage = this.#stage;
    this.#renderTimer();
    const running = this.running;
    stop.hidden = !running || this.noStop;
    stop.disabled = this.#cancelling;
    hint.hidden = !running || this.noStop;
    const failure = this.#final?.error;
    if (failure && !error.error) error.error = failure;
    error.hidden = !error.error;
  }
}

if (!customElements.get("wl-run-status")) customElements.define("wl-run-status", WlRunStatus);
