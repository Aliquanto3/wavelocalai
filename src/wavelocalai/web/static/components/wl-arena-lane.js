// <wl-arena-lane> : une colonne de l'Arène (UX-DR20, AD-20). En-tête collant (nom, badge d'origine,
// statut en texte et icône, mode focus), puis la réponse du modèle, qui se remplit au fil du flux.
//
//   lane.setup({ tag, name, origin })      avant l'insertion dans la page
//   lane.setStatus(status, error, stoppedReason)   `lane_status` : waiting, loading, generating,
//                                          judging, done, timeout, failed, cancelled (interrupted :
//                                          flux perdu) ; `stoppedReason` (story 9.2, `max_tokens`,
//                                          `loop` ou `user`) accompagne un `done` arrêté avant sa
//                                          fin naturelle : note sous le statut, icône en `--color-risk`.
//   lane.setRunId(runId)                   l'identifiant de la feuille (`lane_status.run_id`), pour
//                                          le bouton « Arrêter ce modèle » (`wl-lane-stop`, bulle)
//   lane.token(text, channel)  lane.retry(reason)  lane.metrics(data)
//   lane.setJudge({ single_judge, unreliable })   l'événement `judge` : fiabilité des notes
//   lane.name  lane.origin  lane.status  lane.score  lane.result   lus par le classement (story 3.4) ;
//                                          chaque changement de statut, de note ou de mesures émet
//                                          `wl-lane-change` (bulle), jamais à chaque token
//   lane.setScore({ score, reason })       `judge_score` : note /100 et sa raison, ou « Non évalué »
//                                          avec sa raison (`score` nul : jamais 0). Une colonne qui
//                                          finit en `timeout`, `failed`, `cancelled` ou `interrupted`
//                                          n'a pas de `judge_score` : elle dit « Non évalué » et pourquoi.
//
// La réponse est un `wl-chat-thread` muet (une seule annonce de fin, faite par l'écran) : rendu
// Markdown, débit provisoire puis mesures du serveur (premier token compris). Le thread ne
// démarre qu'à la prise de la place du modèle : une colonne qui attend ne compte pas de durée.
// Un statut final termine la réponse ; un modèle qui n'a rien généré (arrêté en attente) n'a pas
// de réponse. Le chiffre affiché est celui du serveur (AD-20). Sans Shadow DOM.

import { element, icon } from "../core/dom.js";
import { formatDelay } from "../core/format.js";
import { t } from "../core/i18n.js";
import "./wl-badge.js";
import "./wl-chat-thread.js";
import "./wl-error.js";

const STATUS_ICON = {
  waiting: "hourglass-empty",
  loading: "sync",
  generating: "edit",
  judging: "gavel",
  done: "check",
  timeout: "timer",
  failed: "error",
  cancelled: "block",
  interrupted: "warning",
};
// Statut de lane -> statut de fin d'une réponse du fil (qui sait « Arrêté », « Échec »…).
const END_STATUS = {
  done: "ok",
  judging: "ok",
  timeout: "timeout",
  failed: "error",
  cancelled: "cancelled",
  interrupted: "interrupted",
};
const STARTED = new Set(["loading", "generating"]);
const FINAL = new Set(["timeout", "failed", "cancelled", "interrupted"]); // un statut final ne change plus
const IN_PROGRESS = new Set(["waiting", "loading", "generating"]); // « Arrêter ce modèle » : pas en notation
let counter = 0;

function badgeKind(origin) {
  return ["local", "cloud"].includes(origin) ? origin : "unknown";
}

// « non évalué : réponse vide » -> « Réponse vide » : l'étiquette « Non évalué » le dit déjà.
export function reasonText(reason) {
  const text = String(reason ?? "")
    .replace(/^\s*non évalué\s*:\s*/i, "")
    .trim();
  return text ? text[0].toLocaleUpperCase("fr-FR") + text.slice(1) : "";
}

export class WlArenaLane extends HTMLElement {
  #uid = `wl-lane-${++counter}`;
  #info = { tag: "", name: "", origin: "unknown" };
  #status = "waiting";
  #stoppedReason = null; // `max_tokens` | `loop` | `user` (story 9.2), posé par `setStatus`
  #answer = null;
  #ended = false;
  #result = null;
  #score = null; // { score, reason } du `judge_score`
  #judge = { single: false, unreliable: false };
  #dom = null;
  #runId = null; // identifiant de la feuille (`lane_status.run_id`, story 9.2)

  // L'écran le pose depuis `lane_status.run_id` : le bouton « Arrêter ce modèle » en a besoin.
  setRunId(runId) {
    this.#runId = runId || null;
    if (this.#dom) this.#renderStop();
  }

  setup({ tag, name, origin }) {
    this.#info = { tag, name: name || tag, origin: origin || "unknown" };
    if (this.#dom) {
      this.#renderHead();
      this.dispatchEvent(new CustomEvent("wl-lane-rename", { bubbles: true })); // le classement relit le nom
    }
  }

  get tag() {
    return this.#info.tag;
  }

  get status() {
    return this.#status;
  }

  get name() {
    return this.#info.name;
  }

  // L'origine mesurée (événement `metrics`) prime sur celle du sélecteur.
  get origin() {
    return this.#result?.origin ?? this.#info.origin;
  }

  // Les mesures du serveur (événement `metrics`), ou `null` tant qu'il n'en a pas publié.
  get result() {
    return this.#result;
  }

  #changed() {
    this.dispatchEvent(new CustomEvent("wl-lane-change", { bubbles: true }));
  }

  get thread() {
    return this.#dom.thread;
  }

  connectedCallback() {
    this.#build();
  }

  #build() {
    if (this.#dom) return;
    this.className = "wl-arena-lane";
    this.setAttribute("role", "group");

    const name = element("h2", "wl-lane-name");
    const badge = document.createElement("wl-badge");
    const status = element("p", "wl-lane-status");
    const statusIcon = icon(STATUS_ICON.waiting);
    const statusText = element("span", "wl-lane-status-text");
    status.append(statusIcon, statusText);
    const focus = element("button", "btn wl-lane-focus");
    focus.type = "button";
    focus.setAttribute("aria-pressed", "false");
    focus.append(icon("open-in-full"), element("span", "", t("components.lane.focus")));
    focus.addEventListener("click", () => {
      const on = focus.getAttribute("aria-pressed") !== "true";
      this.dispatchEvent(new CustomEvent("wl-lane-focus", { bubbles: true, detail: { on, tag: this.tag } }));
    });
    const stop = element("button", "btn wl-lane-stop", t("components.lane.stop_model"));
    stop.type = "button";
    stop.hidden = true;
    stop.addEventListener("click", () => {
      stop.disabled = true; // un seul envoi : le statut final le masquera
      this.dispatchEvent(
        new CustomEvent("wl-lane-stop", { bubbles: true, detail: { tag: this.tag, runId: this.#runId } }),
      );
    });
    const title = element("div", "wl-lane-title");
    title.append(name, badge);
    const head = element("div", "wl-lane-head");
    head.append(title, status, stop, focus);

    const scoreBox = element("div", "wl-lane-score");
    scoreBox.hidden = true;
    const note = element("p", "wl-lane-note");
    note.hidden = true;
    const error = document.createElement("wl-error");
    error.setAttribute("alert", "");
    const thread = document.createElement("wl-chat-thread");
    thread.setAttribute("silent", "");
    thread.id = `${this.#uid}-thread`;
    const expand = element("button", "btn wl-lane-expand", t("components.lane.expand"));
    expand.type = "button";
    expand.hidden = true;
    expand.setAttribute("aria-controls", thread.id);
    expand.addEventListener("click", () => {
      const open = !this.classList.contains("is-expanded");
      this.classList.toggle("is-expanded", open);
      expand.textContent = t(open ? "components.lane.collapse" : "components.lane.expand");
      if (!open) thread.scrollToEnd();
    });

    this.replaceChildren(head, scoreBox, note, error, thread, expand);
    thread.querySelector("[role=log]")?.setAttribute(
      "aria-label",
      t("components.lane.label", { model: this.#info.name }),
    );
    this.#dom = {
      name,
      badge,
      statusIcon,
      statusText,
      status,
      stop,
      focus,
      scoreBox,
      note,
      error,
      thread,
      expand,
    };
    this.#renderHead();
    this.#renderStatus();
    this.#renderScore();
    this.#renderStop();
  }

  // Visible tant que la lane est en cours ; désactivé tant que sa feuille (`setRunId`) n'est pas
  // connue (la commande ne peut pas encore la désigner).
  #renderStop() {
    this.#dom.stop.hidden = !IN_PROGRESS.has(this.#status);
    this.#dom.stop.disabled = !this.#runId;
  }

  // La note du juge, ou « Non évalué » avec sa raison (jamais 0). Un statut final sans note
  // (délai, échec, arrêt, flux perdu) dit pourquoi la réponse n'est pas évaluée.
  #renderScore() {
    const { scoreBox } = this.#dom;
    let shown = this.#score;
    if (!shown && FINAL.has(this.#status)) {
      shown = { score: null, reason: t(`components.lane.not_evaluated_status.${this.#status}`) };
    }
    scoreBox.hidden = !shown;
    if (!shown) {
      scoreBox.replaceChildren();
      return;
    }
    const scored = typeof shown.score === "number";
    scoreBox.dataset.scored = String(scored);
    const label = element("p", "wl-score-label", t("components.lane.score_label"));
    const line = element("p", "wl-score-line");
    if (scored) {
      line.append(element("span", "wl-score-value", String(shown.score)), element("span", "wl-score-max", "/100"));
    } else {
      line.append(element("span", "wl-score-none", t("components.lane.not_evaluated")));
    }
    const parts = [label, line];
    if (scored) {
      const flags = element("p", "wl-score-flags");
      const single = document.createElement("wl-badge");
      single.setAttribute("kind", "single-judge");
      flags.append(single);
      if (this.#judge.unreliable) {
        const weak = document.createElement("wl-badge");
        weak.setAttribute("kind", "unreliable");
        flags.append(weak);
      }
      parts.push(flags);
    }
    const reason = reasonText(shown.reason);
    if (reason) parts.push(element("p", "wl-score-reason", reason));
    scoreBox.replaceChildren(...parts);
  }

  // `judge` : « un seul juge » et « note peu fiable » accompagnent les notes (jamais « non évalué »).
  setJudge({ single_judge: single = false, unreliable = false } = {}) {
    this.#judge = { single: single === true, unreliable: unreliable === true };
    if (this.#dom) this.#renderScore();
  }

  setScore(data) {
    const score = Number.isInteger(data?.score) && data.score >= 0 && data.score <= 100 ? data.score : null;
    this.#score = { score, reason: data?.reason ?? "" };
    if (this.#dom) this.#renderScore();
    this.#changed();
  }

  get score() {
    return this.#score;
  }

  #renderHead() {
    const { name, badge } = this.#dom;
    name.textContent = this.#info.name;
    badge.setAttribute("kind", badgeKind(this.#result?.origin ?? this.#info.origin));
    this.setAttribute("aria-label", t("components.lane.label", { model: this.#info.name }));
    this.dataset.tag = this.#info.tag;
  }

  #renderStatus(error = null) {
    const { statusIcon, statusText, note, error: errorBox } = this.#dom;
    const status = this.#status;
    this.dataset.status = status;
    // Arrêt avant la fin naturelle (story 9.2, maquette résultats, story 9.6) : la ligne de statut
    // dit « Arrêté : … » (icône `block` seule en `--color-risk`, texte en encre gras, jamais
    // « Terminé » ni « Échec ») ; `[data-stopped-reason]` porte la couleur de l'icône (`arena.css`).
    const stopped = status === "done" ? this.#stoppedReason : null;
    statusText.textContent = stopped
      ? t(`components.lane.stopped.${stopped}`)
      : t(`components.lane.status.${status}`);
    statusIcon
      .querySelector("use")
      .setAttribute("href", `/static/icons.svg#i-${stopped ? "block" : STATUS_ICON[status]}`);
    if (stopped) this.dataset.stoppedReason = stopped;
    else delete this.dataset.stoppedReason;
    if (status === "timeout") {
      // « Délai dépassé (120 s) » : le délai réel, celui du serveur (`detail.timeout_s`).
      const seconds = error?.detail?.timeout_s;
      note.textContent =
        typeof seconds === "number" && Number.isFinite(seconds)
          ? t("components.lane.timeout_note_delay", { seconds: formatDelay(seconds) })
          : t("components.lane.timeout_note");
      note.hidden = false;
      errorBox.error = null;
    } else if (status === "failed" && error) {
      errorBox.error = error;
      note.hidden = true;
    } else if (!["timeout", "failed"].includes(status)) {
      note.hidden = true;
      errorBox.error = null;
    }
  }

  // Le mode focus de cette colonne (l'écran le pose, un seul à la fois).
  setFocus(on) {
    this.#dom.focus.setAttribute("aria-pressed", String(on));
  }

  get focused() {
    return this.#dom?.focus.getAttribute("aria-pressed") === "true";
  }

  #ensureAnswer() {
    if (!this.#answer && !this.#ended) {
      const { name, origin } = this.#info;
      this.#answer = this.#dom.thread.beginAnswer({ name, origin, firstToken: true });
      this.#dom.expand.hidden = false;
    }
    return this.#answer;
  }

  setStatus(status, error = null, stoppedReason = null) {
    if (!(status in STATUS_ICON) || FINAL.has(this.#status)) return;
    if (STARTED.has(status)) this.#ensureAnswer();
    this.#status = status;
    this.#stoppedReason = stoppedReason || null;
    this.#renderStatus(error);
    this.#renderScore();
    this.#renderStop();
    if (status in END_STATUS) this.#end(status);
    this.#changed();
  }

  #end(status) {
    if (this.#ended) return;
    this.#ended = true;
    if (!this.#answer && ["done", "judging"].includes(status)) this.#answer = this.#beginEmpty();
    this.#answer?.end({ status: END_STATUS[status] });
  }

  // Une lane terminée sans un seul token : sa réponse vide garde ses mesures.
  #beginEmpty() {
    const { name, origin } = this.#info;
    this.#dom.expand.hidden = false;
    const answer = this.#dom.thread.beginAnswer({ name, origin, firstToken: true });
    if (this.#result) answer.metrics(this.#result);
    return answer;
  }

  token(text, channel) {
    if (this.#ended) return;
    // Un token est la preuve que le modèle génère (le chargement a pris fin, `model_loaded` ou non).
    if (["waiting", "loading"].includes(this.#status)) this.setStatus("generating");
    this.#ensureAnswer()?.token(text, channel);
  }

  retry(reason) {
    if (this.#ended) return;
    this.#ensureAnswer()?.retry(reason);
  }

  metrics(data) {
    this.#result = data ?? null;
    this.#answer?.metrics(data);
    if (this.#dom) this.#renderHead(); // l'origine mesurée prime sur celle du sélecteur
    this.#changed();
  }

  // Le flux est perdu sans statut final : la réponse partielle reste, dite « interrompue ». Une
  // colonne en notation (`judging`, réponse déjà close) ne reste pas « Notation » : notée, elle est
  // terminée ; sans `judge_score`, elle est interrompue et dit « Non évalué » avec la raison.
  interrupt() {
    if (this.#status === "judging") this.setStatus(this.#score ? "done" : "interrupted");
    else if (!this.#ended) this.setStatus("interrupted");
  }

  get ended() {
    return this.#ended;
  }

  suspend() {
    this.#dom?.thread.suspend();
  }

  resume() {
    this.#dom?.thread.resume();
  }
}

if (!customElements.get("wl-arena-lane")) customElements.define("wl-arena-lane", WlArenaLane);
