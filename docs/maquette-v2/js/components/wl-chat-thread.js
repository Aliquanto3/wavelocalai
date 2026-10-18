// Repris de la branche feat/v2-ecran-chat (story 2.2) ; ajout : CO₂ dans le pied définitif (stories 2.3, 2.5).
// <wl-chat-thread> : le fil d'une conversation (UX-DR10, AD-20). `role="log"` sans annonce pendant
// le flux (`aria-live="off"`) ; une région à part annonce poliment la fin de chaque réponse.
//
//   thread.addUserMessage(texte)
//   const answer = thread.beginAnswer({ name, origin, compact })   // une réponse de modèle
//   (`compact` : pied réduit à CO₂ et durée totale, pour une tâche d'agent)
//   answer.token(texte, canal)  answer.retry(raison)  answer.metrics(données)  answer.end({ status })
//
// Les tokens vont dans un nœud tampon dès leur réception (le texte brut est lisible tout de suite),
// et la réponse entière est rendue en Markdown (`core/markdown.js`, sans `innerHTML`) au plus toutes
// les 150 ms et à la fin. Le raisonnement (`thought`) est replié. Le défilement suit la réponse
// seulement si la personne est en bas ; sinon « Aller à la fin » apparaît. Le pied de réponse montre
// d'abord un débit provisoire calculé ici (le seul chiffre local avec le chronomètre, AD-20), puis,
// à `metrics`, les mesures du serveur. Sans Shadow DOM.

import { co2Display } from "../core/co2.js";
import { element, icon } from "../core/dom.js";
import { formatDuration, formatInteger, formatRate } from "../core/format.js";
import { t } from "../core/i18n.js";
import { renderMarkdown, tailHost } from "../core/markdown.js";
import "./wl-badge.js";
import "./wl-metric.js";

export const RENDER_MS = 150; // au plus un rendu Markdown par tranche de 150 ms
const TICK_MS = 250; // pied provisoire : durée et débit
const BOTTOM_PX = 24; // « en bas » : à 24 px près
const CHARS_PER_TOKEN = 4; // estimation provisoire seulement : le serveur donne le compte exact

const FLAGS = {
  cancelled: { flag: "components.thread.stopped", announce: "components.thread.stopped_announce" },
  error: { flag: "components.thread.failed", announce: "components.thread.failed_announce" },
  interrupted: {
    flag: "components.thread.interrupted",
    announce: "components.thread.interrupted_announce",
  },
};

function badgeKind(origin) {
  return ["local", "cloud"].includes(origin) ? origin : "unknown";
}

function metric(label, value, { help, provisional } = {}) {
  const node = document.createElement("wl-metric");
  node.setAttribute("label", label);
  node.setAttribute("value", value);
  if (help) node.setAttribute("help", help);
  if (provisional) node.setAttribute("provisional", "");
  return node;
}

// Un attribut n'est réécrit que s'il change : `wl-metric` se redessine à chaque écriture.
function setValue(node, value) {
  if (node.getAttribute("value") !== value) node.setAttribute("value", value);
}

class ChatAnswer {
  constructor(thread, { name, origin, compact = false }) {
    this.thread = thread;
    this.compact = compact; // pied réduit (agent, décision 31) : CO₂ et durée totale
    this.name = name;
    this.origin = origin;
    this.text = "";
    this.thoughtText = "";
    this.result = null; // données de `metrics`
    this.ended = false;
    this.startedAt = performance.now();
    this.firstTokenAt = null;
    this.lastRender = -Infinity;
    this.timer = null;

    const who = element("p", "wl-msg-who");
    who.append(element("span", "wl-msg-name", name));
    this.badge = document.createElement("wl-badge");
    this.badge.setAttribute("kind", badgeKind(origin));
    who.append(this.badge);

    this.thoughtNode = document.createTextNode("");
    this.thought = element("details", "wl-thought");
    this.thought.hidden = true;
    const body = element("div", "wl-thought-body");
    body.append(this.thoughtNode);
    this.thought.append(element("summary", "", t("components.thread.thought")), body);

    this.body = element("div", "wl-msg-text wl-md");
    this.tail = document.createTextNode(""); // le nœud tampon des tokens, entre deux rendus
    this.body.append(this.tail);
    this.note = element("p", "help wl-msg-note");
    this.note.hidden = true;
    this.flag = element("p", "wl-msg-flag");
    this.flag.hidden = true;
    this.foot = element("div", "wl-msg-foot");

    this.rate = metric(t("components.thread.rate"), formatRate(null), { provisional: true });
    this.duration = metric(t("components.thread.duration"), formatDuration(0));
    this.tokens = metric(t("components.thread.tokens"), formatInteger(0));
    this.foot.append(this.rate, this.tokens, this.duration);

    this.root = element("div", "wl-msg wl-msg-assistant");
    this.root.append(who, this.thought, this.body, this.note, this.flag, this.foot);
    this.ticker = setInterval(() => this.#tick(), TICK_MS);
  }

  token(text, channel = "answer") {
    if (this.ended || typeof text !== "string") return;
    if (channel === "thought") {
      this.thoughtText += text;
      this.thoughtNode.data = this.thoughtText;
      this.thought.hidden = false;
    } else {
      this.firstTokenAt ??= performance.now();
      this.text += text;
      this.tail.data += text; // lisible tout de suite ; le Markdown suit au prochain rendu
      this.#scheduleRender();
    }
    this.thread._changed();
  }

  // Le serveur relance la génération après une coupure : le texte partiel est retiré (AD-5).
  retry(reason) {
    if (this.ended) return;
    this.text = "";
    this.thoughtText = "";
    this.thoughtNode.data = "";
    this.thought.hidden = true;
    this.firstTokenAt = null;
    this.#render();
    this.note.textContent = t("components.thread.retried", { reason: reason ?? "" });
    this.note.hidden = false;
    this.thread._changed();
  }

  metrics(data) {
    this.result = data ?? null;
  }

  end({ status = "ok" } = {}) {
    if (this.ended) return;
    this.ended = true;
    clearInterval(this.ticker);
    clearTimeout(this.timer);
    this.#render(); // dernier rendu : tout le texte, mis en forme
    this.tail.remove();
    const kind = FLAGS[status];
    if (kind) {
      this.flag.textContent = t(kind.flag);
      this.flag.hidden = false;
    }
    this.#finalFoot();
    this.thread._changed();
    this.thread._announce(this.#announcement(status));
  }

  #announcement(status) {
    if (FLAGS[status]) return t(FLAGS[status].announce, { model: this.name });
    const count = this.result?.eval_tokens;
    return typeof count === "number"
      ? t("components.thread.done", { model: this.name, tokens: formatInteger(count) })
      : t("components.thread.done_plain", { model: this.name });
  }

  #scheduleRender() {
    const wait = RENDER_MS - (performance.now() - this.lastRender);
    if (wait <= 0) this.#render();
    else this.timer ??= setTimeout(() => this.#render(), wait);
  }

  #render() {
    clearTimeout(this.timer);
    this.timer = null;
    this.lastRender = performance.now();
    this.body.replaceChildren(renderMarkdown(this.text));
    this.tail.data = "";
    if (!this.ended) tailHost(this.body).append(this.tail);
    this.thread._changed();
  }

  #estimate() {
    const now = performance.now();
    const tokens = Math.round(this.text.length / CHARS_PER_TOKEN);
    const seconds = this.firstTokenAt === null ? 0 : (now - this.firstTokenAt) / 1000;
    return {
      tokens,
      elapsed: (now - this.startedAt) / 1000,
      rate: seconds >= 0.5 && tokens > 0 ? tokens / seconds : null,
    };
  }

  // Pied provisoire : débit, tokens et durée du navigateur, tant que `metrics` n'est pas arrivé.
  #tick() {
    if (!this.ended) this.#refreshFoot();
  }

  #refreshFoot() {
    const { tokens, elapsed, rate } = this.#estimate();
    setValue(this.rate, formatRate(rate));
    setValue(this.tokens, formatInteger(tokens));
    setValue(this.duration, formatDuration(Math.floor(elapsed)));
  }

  // Pied définitif : les mesures du serveur. Sans `metrics` (arrêt, échec), le pied reste celui
  // du navigateur, figé et toujours dit « provisoire ».
  #finalFoot() {
    const result = this.result;
    if (!result) {
      this.#refreshFoot();
      return;
    }
    this.badge.setAttribute("kind", badgeKind(result.origin ?? this.origin));
    const co2 = co2Display(result.co2);
    if (this.compact) {
      // Réponse d'agent : le débit agrégé de plusieurs appels dit peu (décision 31).
      this.foot.replaceChildren(
        metric(t("components.thread.co2"), co2.value, { help: co2.help }),
        metric(t("components.thread.total"), formatDuration(result.total_s)),
      );
      return;
    }
    const parts = [
      metric(t("components.thread.co2"), co2.value, { help: co2.help }),
      metric(t("components.thread.rate"), formatRate(result.tps), {
        help: t("components.thread.rate_help"),
      }),
      metric(t("components.thread.tokens"), formatInteger(result.eval_tokens)),
      metric(t("components.thread.load"), formatDuration(result.load_s)),
      metric(t("components.thread.total"), formatDuration(result.total_s)),
    ];
    if (result.tps_source === "wallclock") {
      const estimated = document.createElement("wl-badge");
      estimated.setAttribute("kind", "estimated");
      parts.unshift(estimated);
    }
    this.foot.replaceChildren(...parts);
  }

  dispose() {
    clearInterval(this.ticker);
    clearTimeout(this.timer);
  }
}

export class WlChatThread extends HTMLElement {
  #dom = null;
  #following = true;
  #saved = null;
  #answers = new Set();

  connectedCallback() {
    this.#build();
  }

  disconnectedCallback() {
    for (const answer of this.#answers) answer.dispose();
  }

  #build() {
    if (this.#dom) return;
    this.className = "wl-thread";
    const log = element("div", "wl-thread-log");
    log.setAttribute("role", "log");
    log.setAttribute("aria-live", "off"); // rien n'est annoncé pendant le flux
    log.setAttribute("aria-label", t("components.thread.label"));
    log.tabIndex = 0; // une zone qui défile se lit au clavier
    log.addEventListener("scroll", () => this.#onScroll());
    const toEnd = element("button", "btn wl-thread-end");
    toEnd.type = "button";
    toEnd.hidden = true;
    toEnd.append(icon("expand-more"), element("span", "", t("components.thread.to_end")));
    toEnd.addEventListener("click", () => {
      this.scrollToEnd();
      log.focus({ preventScroll: true });
    });
    const live = element("div", "sr-only");
    live.setAttribute("role", "status");
    live.setAttribute("aria-live", "polite");
    live.setAttribute("aria-atomic", "true");
    this.replaceChildren(log, toEnd, live);
    this.#dom = { log, toEnd, live };
  }

  get empty() {
    return this.#dom.log.childElementCount === 0;
  }

  addUserMessage(text) {
    const message = element("div", "wl-msg wl-msg-user");
    message.append(element("p", "wl-msg-who", t("components.thread.you")));
    message.append(element("div", "wl-msg-text wl-msg-plain", text)); // texte brut, jamais du HTML
    this.#dom.log.append(message);
    this.scrollToEnd();
  }

  beginAnswer({ name, origin, compact = false }) {
    const answer = new ChatAnswer(this, { name, origin, compact });
    this.#answers.add(answer);
    this.#dom.log.append(answer.root);
    this.scrollToEnd();
    return answer;
  }

  clear() {
    for (const answer of this.#answers) answer.dispose();
    this.#answers.clear();
    this.#dom.log.replaceChildren();
    this.#dom.live.textContent = "";
    this.#following = true;
    this.#dom.toEnd.hidden = true;
  }

  scrollToEnd() {
    const { log, toEnd } = this.#dom;
    log.scrollTop = log.scrollHeight;
    this.#following = true;
    toEnd.hidden = true;
  }

  // L'écran sort de la vue (masqué, gardé en mémoire) : le défilement est mémorisé, puis rendu.
  suspend() {
    this.#saved = { following: this.#following, top: this.#dom.log.scrollTop };
  }

  resume() {
    const saved = this.#saved;
    this.#saved = null;
    if (!saved) return;
    if (saved.following) this.scrollToEnd();
    else {
      this.#dom.log.scrollTop = saved.top;
      this.#onScroll();
    }
  }

  // Appelés par les réponses.
  _changed() {
    const { log, toEnd } = this.#dom;
    if (this.#following) log.scrollTop = log.scrollHeight;
    else toEnd.hidden = false;
  }

  _announce(text) {
    // Vider puis remplir : un même texte est de nouveau annoncé.
    this.#dom.live.textContent = "";
    requestAnimationFrame(() => {
      this.#dom.live.textContent = text;
    });
  }

  #onScroll() {
    if (this.closest("[hidden]")) return; // écran masqué : la position n'est pas celle de la personne
    const { log, toEnd } = this.#dom;
    const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight <= BOTTOM_PX;
    this.#following = atBottom;
    toEnd.hidden = atBottom;
  }
}

if (!customElements.get("wl-chat-thread")) customElements.define("wl-chat-thread", WlChatThread);
