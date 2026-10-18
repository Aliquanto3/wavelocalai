// <wl-arena-lane> : une colonne de l'Arène (UX-DR20, AD-20). En-tête collant (nom, badge d'origine,
// statut en texte et icône, mode focus), puis la réponse du modèle, qui se remplit au fil du flux.
//
//   lane.setup({ tag, name, origin })      avant l'insertion dans la page
//   lane.setStatus(status, error)          `lane_status` : waiting, loading, generating, judging,
//                                          done, timeout, failed, cancelled (interrupted : flux perdu)
//   lane.token(text, channel)  lane.retry(reason)  lane.metrics(data)
//   lane.setJudge({ single_judge, unreliable })   l'événement `judge` : fiabilité des notes
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
  #answer = null;
  #ended = false;
  #result = null;
  #score = null; // { score, reason } du `judge_score`
  #judge = { single: false, unreliable: false };
  #dom = null;

  setup({ tag, name, origin }) {
    this.#info = { tag, name: name || tag, origin: origin || "unknown" };
    if (this.#dom) this.#renderHead();
  }

  get tag() {
    return this.#info.tag;
  }

  get status() {
    return this.#status;
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
    const title = element("div", "wl-lane-title");
    title.append(name, badge);
    const head = element("div", "wl-lane-head");
    head.append(title, status, focus);

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
    statusText.textContent = t(`components.lane.status.${status}`);
    statusIcon.querySelector("use").setAttribute("href", `/static/icons.svg#i-${STATUS_ICON[status]}`);
    if (status === "timeout") {
      note.textContent = t("components.lane.timeout_note");
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

  setStatus(status, error = null) {
    if (!(status in STATUS_ICON) || FINAL.has(this.#status)) return;
    if (STARTED.has(status)) this.#ensureAnswer();
    this.#status = status;
    this.#renderStatus(error);
    this.#renderScore();
    if (status in END_STATUS) this.#end(status);
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
