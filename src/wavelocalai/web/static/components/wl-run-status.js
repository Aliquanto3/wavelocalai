// <wl-run-status> : étape nommée d'un run, chronomètre local, bouton Arrêter (UX-DR8, AD-6, AD-20).
//
// `el.runId = "<id>"` (ou l'attribut `run-id`) suit un run par le client SSE unique : « Chargement
// du modèle en mémoire… » (`model_loading`), « Génération… » (`model_loaded`, puis `token`), puis
// l'état final (`run_ended`). Un run de RAG commence par « Recherche des extraits… » (attribut
// `first-stage="retrieving"`) ou, pour HyDE, par « Rédaction d'une réponse hypothétique… »
// (`first-stage="hypothesizing"`), jusqu'à `sources` ; `retrieval_step`, publié à la fin de chaque
// étape, dit la suivante : la recherche, et pour Self-RAG, après chaque recherche, « Vérification de
// la pertinence… ». Quand un reranker local est là, l'étape `search` porte `reranking: true` : le
// serveur annonce ainsi que « Reclassement… » commence (le front ne devine rien). Le chronomètre est le seul chiffre calculé ici (AD-20) : il part de
// l'horodatage de `run_started` et s'arrête à `run_ended`. Le bouton Arrêter et la touche Échap
// appellent `POST /api/runs/{id}/cancel` ; le run se termine par son propre `run_ended`.
//
// Événement : `wl-run-ended` (`detail.status`, `detail.error`). Un flux n'est ouvert que pour le
// run suivi et se ferme au retrait du composant de la page. Sans Shadow DOM.
//
// Pendant `model_loading` (étape « loading »), une phrase prévient que le premier appel est plus
// long (UX-DR17, « Premier chargement lent ») ; elle disparaît dès que le modèle est chargé.
//
// Mode piloté (attribut `driven`) : l'écran lit déjà le flux du run (le dernier `seq` d'un run est
// unique dans le store, deux lecteurs s'écarteraient les événements) ; il passe chaque enveloppe à
// `feed(envelope)`, et `abandon()` dit que le flux est perdu. Aucun flux n'est ouvert ici.
// La touche Échap n'agit que si le composant est à l'écran (un écran gardé en mémoire est masqué).
// En mode piloté, l'écran annonce lui-même la fin du run : l'état final s'affiche sans être annoncé
// (une seule annonce polie à la fin, UX-DR10). Les changements d'étape restent annoncés.

import { api, ApiError } from "../core/api.js";
import { element } from "../core/dom.js";
import { formatDuration } from "../core/format.js";
import { t } from "../core/i18n.js";
import { connectRun } from "../core/sse.js";
import "./wl-error.js";

const STAGE_TEXT = {
  starting: "components.run_status.starting",
  retrieving: "components.run_status.retrieving",
  hypothesizing: "components.run_status.hypothesizing",
  verifying: "components.run_status.verifying",
  reranking: "components.run_status.reranking",
  loading: "components.run_status.loading",
  generating: "components.run_status.generating",
  stopping: "components.run_status.stopping",
  ok: "components.run_status.ok",
  cancelled: "components.run_status.cancelled",
  error: "components.run_status.error",
  interrupted: "components.run_status.interrupted",
};
const TICK_MS = 250;
const FIRST_STAGES = ["retrieving", "hypothesizing"]; // valeurs de l'attribut `first-stage`

// Étape qui suit une étape de recherche terminée : Self-RAG note les extraits après chaque
// recherche, tout le reste continue de chercher (la réponse hypothétique de HyDE vient d'être
// rédigée, la question reformulée ou vectorisée) jusqu'à `sources`.
// Un reclassement annoncé (`search` avec `reranking`) se dit pendant qu'il tourne ; son étape
// `rerank` terminée, la suite est celle de la stratégie.
function stageAfter(step) {
  if (step?.step === "search" && step.reranking) return "reranking";
  const searched = step?.step === "search" || step?.step === "rerank";
  return step?.strategy === "self_rag" && searched ? "verifying" : "retrieving";
}

export class WlRunStatus extends HTMLElement {
  static observedAttributes = ["run-id"];

  #runId = null;
  #stream = null;
  #stage = "starting";
  #final = null; // { status, error } une fois le run terminé
  #startMs = null;
  #endMs = null;
  #timer = null;
  #cancelling = false;
  #dom = null;
  #onKeydown = (event) => {
    if (event.key === "Escape" && !event.defaultPrevented && this.running && !this.closest("[hidden]")) {
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
    const firstLoad = element("p", "help wl-run-first-load", t("components.run_status.first_load"));
    firstLoad.hidden = true;
    this.className = "wl-run-status";
    const line = element("div", "wl-run-line");
    line.append(stage, timer, stop, hint);
    this.replaceChildren(line, firstLoad, error);
    this.#dom = { stage, timer, stop, hint, firstLoad, error };
  }

  #reset() {
    // `first-stage` : un run qui cherche d'abord (RAG) dit « Recherche des extraits… » (ou, pour
    // HyDE, « Rédaction d'une réponse hypothétique… ») dès son démarrage, jusqu'à `sources`.
    const first = this.getAttribute("first-stage");
    this.#stage = FIRST_STAGES.includes(first) ? first : "starting";
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
      const started = Date.parse(envelope.ts);
      this.#startMs = Number.isNaN(started) ? Date.now() : Math.min(started, Date.now());
      this.#timer ??= setInterval(() => this.#renderTimer(), TICK_MS);
      this.#render();
    },
    retrieval_step: (data) => this.#setStage(stageAfter(data)),
    sources: () => this.#setStage("generating"),
    model_loading: () => this.#setStage("loading"),
    model_loaded: () => this.#setStage("generating"),
    token: () => this.#setStage("generating"),
    run_ended: (data, envelope) => this.#end(data ?? {}, envelope),
  };

  get driven() {
    return this.hasAttribute("driven");
  }

  // Mode piloté : une enveloppe `{type, data, ts…}` du flux que l'écran lit.
  feed(envelope) {
    if (!this.driven || !envelope || !Object.hasOwn(this.#handlers, envelope.type)) return;
    this.#handlers[envelope.type](envelope.data, envelope);
  }

  // Flux abandonné (run inconnu, ou serveur muet après plusieurs essais) sans `run_ended` :
  // l'état n'est plus suivi, on le dit au lieu de laisser « Génération… » et Arrêter.
  abandon() {
    if (this.#runId !== null && !this.#final) this.#end({ status: "interrupted" }, {});
  }

  #start() {
    this.#render();
    if (this.driven) return;
    this.#stream = connectRun(this.#runId, this.#handlers, ({ status }) => {
      if (status === "failed") this.abandon();
    });
  }

  #setStage(stage) {
    if (this.#final || this.#cancelling || this.#stage === stage) return;
    this.#stage = stage;
    this.#render();
  }

  #end(data, envelope) {
    const ended = Date.parse(envelope.ts);
    this.#endMs = Number.isNaN(ended) ? Date.now() : ended;
    this.#startMs ??= this.#endMs;
    clearInterval(this.#timer);
    this.#timer = null;
    const status = Object.hasOwn(STAGE_TEXT, data.status) ? data.status : "error";
    this.#final = { status, error: data.error ?? null };
    this.#stage = status;
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
    const runId = this.#runId;
    this.#cancelling = true;
    this.#stage = "stopping";
    // Le bouton passe en `disabled` : le focus va sur l'étape au lieu de se perdre.
    if (document.activeElement === this.#dom.stop) this.#dom.stage.focus();
    this.#render();
    try {
      await api.cancelRun(runId);
    } catch (error) {
      if (runId !== this.#runId || this.#final) return;
      this.#cancelling = false;
      this.#stage = "generating";
      this.#dom.error.error =
        error instanceof ApiError && error.envelope
          ? error.envelope
          : { code: "internal", message: t("components.run_status.cancel_failed") };
      this.#render();
    }
  }

  #elapsedSeconds() {
    if (this.#startMs === null) return 0;
    const end = this.#endMs ?? Date.now();
    return Math.max(0, Math.floor((end - this.#startMs) / 1000));
  }

  #renderTimer() {
    this.#dom.timer.textContent = formatDuration(this.#elapsedSeconds());
  }

  #render() {
    const { stage, stop, hint, firstLoad, error } = this.#dom;
    this.hidden = this.#runId === null;
    // L'étape est une région `status` : une réécriture du même texte serait annoncée de nouveau.
    stage.setAttribute("aria-live", this.driven && this.#final ? "off" : "polite");
    const text = t(STAGE_TEXT[this.#stage]);
    if (stage.textContent !== text) stage.textContent = text;
    this.dataset.stage = this.#stage;
    this.#renderTimer();
    const running = this.running;
    stop.hidden = !running;
    stop.disabled = this.#cancelling;
    hint.hidden = !running;
    firstLoad.hidden = !(running && this.#stage === "loading");
    const failure = this.#final?.error;
    if (failure && !error.error) error.error = failure;
    error.hidden = !error.error;
  }
}

if (!customElements.get("wl-run-status")) customElements.define("wl-run-status", WlRunStatus);
