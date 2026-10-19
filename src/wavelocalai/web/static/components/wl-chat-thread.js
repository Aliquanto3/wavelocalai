// <wl-chat-thread> : le fil d'une conversation (UX-DR10, AD-20). `role="log"` sans annonce pendant
// le flux (`aria-live="off"`) ; une région à part annonce poliment la fin de chaque réponse.
//
//   thread.addUserMessage(texte)
//   const answer = thread.beginAnswer({ name, origin })   // une réponse de modèle
//   answer.token(texte, canal)  answer.retry(raison)  answer.metrics(données)  answer.end({ status })
//   thread.restoreAnswer({ name, origin, text, thought, result, status })   // réponse déjà finie,
//                                                                           // rouverte : rien n'est annoncé
//                                                                           // (rend la réponse)
//   answer.actions   // zone sous le pied où l'écran range ses boutons (« Afficher les sources »)
//   answer.decorator = (corps) => {…}   // appelée après chaque rendu Markdown de la réponse : l'écran y
//                                       // transforme des marqueurs en boutons (citations vérifiées) ;
//                                       // restoreAnswer({ …, decorator }) l'applique à une réponse rouverte
//   answer.refresh()                    // rend la réponse de nouveau (le décorateur a de nouvelles données)
//   thread.beginAnswer({ name, origin, reduced: true })   // pied réduit (agents, D-31) : ni débit, ni
//   answer.summarize({ co2, steps, duration_s })           // tokens, ni chargement ; les totaux du serveur
//
// Les tokens vont dans un nœud tampon dès leur réception (le texte brut est lisible tout de suite),
// et la réponse entière est rendue en Markdown (`core/markdown.js`, sans `innerHTML`) au plus toutes
// les 150 ms et à la fin. Le raisonnement (`thought`) est replié. Le défilement suit la réponse
// seulement si la personne est en bas ; sinon « Aller à la fin » apparaît. Le pied de réponse montre
// d'abord un débit provisoire calculé ici (le seul chiffre local avec le chronomètre, AD-20), puis,
// à `metrics`, les mesures du serveur. Sans Shadow DOM.

import { element, icon } from "../core/dom.js";
import { formatCo2, formatDuration, formatInteger, formatRate } from "../core/format.js";
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

// CO2 de la réponse, tel que le serveur l'a mesuré (`metrics.co2`, AD-10) : la valeur est seulement
// mise en forme (`formatCo2`, une seule unité, fr-FR), sans calcul ni couleur par seuil (AD-20).
// `mg` nul ne devient jamais 0 : « non mesurable », la raison du serveur en aide. Une réponse cloud
// est estimée (ecologits, AD-11) : « (estimé) » après la valeur, la réserve du serveur en aide.
function co2Metric(co2) {
  const label = t("components.thread.co2");
  if (typeof co2?.mg === "number" && Number.isFinite(co2.mg)) {
    if (co2.estimated) {
      const help = t("components.thread.co2_estimated_help");
      return metric(label, t("components.thread.co2_estimated", { value: formatCo2(co2.mg) }), {
        help: co2.reason ? `${help} ${co2.reason}` : help,
      });
    }
    return metric(label, formatCo2(co2.mg), { help: t("components.thread.co2_help") });
  }
  return metric(label, t("components.thread.co2_unmeasurable"), {
    help: co2?.reason || t("components.thread.co2_unmeasurable_help"),
  });
}

// Un attribut n'est réécrit que s'il change : `wl-metric` se redessine à chaque écriture.
function setValue(node, value) {
  if (node.getAttribute("value") !== value) node.setAttribute("value", value);
}

class ChatAnswer {
  constructor(thread, { name, origin, firstToken = false, restored = false, reduced = false }) {
    this.showFirstToken = firstToken; // colonne de l'Arène : le pied dit aussi le premier token
    this.reduced = reduced; // agents : pied réduit aux totaux de la tâche (D-31)
    this.totals = null;
    this.thread = thread;
    this.restored = restored;
    this.name = name;
    this.origin = origin;
    this.text = "";
    this.thoughtText = "";
    this.result = null; // données de `metrics`
    this.decorator = null;
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
    this.actions = element("div", "wl-msg-actions");

    this.rate = metric(t("components.thread.rate"), formatRate(null), { provisional: true });
    this.duration = metric(t("components.thread.duration"), formatDuration(0));
    this.tokens = metric(t("components.thread.tokens"), formatInteger(0));
    if (reduced) this.foot.hidden = true; // les totaux du serveur le remplissent à la fin
    else this.foot.append(this.rate, this.tokens, this.duration);

    this.root = element("div", "wl-msg wl-msg-assistant");
    this.root.append(who, this.thought, this.body, this.note, this.flag, this.foot, this.actions);
    this.ticker = reduced ? null : setInterval(() => this.#tick(), TICK_MS);
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

  // Pied réduit : CO2, étapes et durée de la tâche, additionnés par le serveur (AD-20).
  summarize(totals) {
    this.totals = totals ?? null;
    if (this.ended) this.#finalFoot();
  }

  metrics(data) {
    if (this.reduced) return; // un appel de modèle parmi d'autres : le pied dit la tâche entière
    this.result = data ?? null;
    if (this.ended) this.#finalFoot(); // mesures complétées après l'arrêt (Arène rouverte, story 3.6)
  }

  refresh() {
    this.#render();
  }

  end({ status = "ok" } = {}) {
    if (this.ended) return;
    this.#settle(status);
    this.thread._announce(this.#announcement(status));
  }

  // Réponse retrouvée dans une conversation rouverte (GET /api/conversations/{id}) : texte,
  // raisonnement et mesures du serveur, comme à la fin du flux, mais sans annonce (la personne
  // n'attend pas de réponse) et sans pied provisoire : sans mesure, le pied est retiré, car la
  // durée vue par le navigateur n'existe plus.
  restore({ text = "", thought = "", result = null, status = "ok" }) {
    this.text = text;
    if (thought) {
      this.thoughtText = thought;
      this.thoughtNode.data = thought;
      this.thought.hidden = false;
    }
    this.result = result;
    this.#settle(status);
  }

  #settle(status) {
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
    this.decorator?.(this.body);
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
    if (this.reduced) return this.#reducedFoot();
    const result = this.result;
    if (!result) {
      if (this.restored) this.foot.remove();
      else this.#refreshFoot();
      return;
    }
    this.badge.setAttribute("kind", badgeKind(result.origin ?? this.origin));
    const parts = [
      co2Metric(result.co2),
      metric(t("components.thread.rate"), formatRate(result.tps), {
        help: t("components.thread.rate_help"),
      }),
      metric(t("components.thread.tokens"), formatInteger(result.eval_tokens)),
      metric(t("components.thread.load"), formatDuration(result.load_s)),
    ];
    if (typeof result.retrieval_s === "number") {
      // Réponse à partir de documents : la recherche des extraits et la génération, à part
      // (UX-DR23) ; `total_s` est celui de la génération seule.
      parts.push(
        metric(t("components.thread.retrieval"), formatDuration(result.retrieval_s), {
          help: t("components.thread.retrieval_help"),
        }),
        metric(t("components.thread.generation"), formatDuration(result.total_s), {
          help: t("components.thread.generation_help"),
        }),
      );
    } else {
      parts.push(metric(t("components.thread.total"), formatDuration(result.total_s)));
    }
    if (this.showFirstToken) {
      parts.splice(2, 0, metric(t("components.thread.first_token"), formatDuration(result.ttft_s)));
    }
    if (result.tps_source === "wallclock") {
      const estimated = document.createElement("wl-badge");
      estimated.setAttribute("kind", "estimated");
      parts.unshift(estimated);
    }
    this.foot.replaceChildren(...parts);
  }

  #reducedFoot() {
    const totals = this.totals;
    this.foot.hidden = !totals;
    if (!totals) return;
    const parts = [];
    if (totals.co2) parts.push(co2Metric(totals.co2));
    parts.push(
      metric(t("components.thread.steps"), formatInteger(totals.steps)),
      metric(t("components.thread.duration"), formatDuration(totals.duration_s)),
    );
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
  #top = 0; // dernière position vue à l'écran : masqué (`display: none`), `scrollTop` vaut 0
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

  beginAnswer({ name, origin, firstToken = false, reduced = false }) {
    const answer = new ChatAnswer(this, { name, origin, firstToken, reduced });
    this.#answers.add(answer);
    this.#dom.log.append(answer.root);
    this.scrollToEnd();
    return answer;
  }

  restoreAnswer({ name, origin, decorator = null, ...content }) {
    const answer = new ChatAnswer(this, { name, origin, restored: true });
    answer.decorator = decorator;
    this.#answers.add(answer);
    this.#dom.log.append(answer.root);
    answer.restore(content);
    this.scrollToEnd();
    return answer;
  }

  clear() {
    for (const answer of this.#answers) answer.dispose();
    this.#answers.clear();
    this.#dom.log.replaceChildren();
    this.#dom.live.textContent = "";
    this.#following = true;
    this.#top = 0;
    this.#dom.toEnd.hidden = true;
  }

  scrollToEnd() {
    const { log, toEnd } = this.#dom;
    log.scrollTop = log.scrollHeight;
    this.#following = true;
    toEnd.hidden = true;
  }

  // L'écran sort de la vue (masqué, gardé en mémoire) : le défilement est mémorisé, puis rendu.
  // L'appel arrive après le masquage : la position vient du dernier défilement vu, pas du DOM.
  suspend() {
    this.#saved = { following: this.#following, top: this.#top };
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
    if (this.hasAttribute("silent")) return; // l'écran annonce lui-même (Arène : une seule fin)
    // Vider puis remplir : un même texte est de nouveau annoncé.
    this.#dom.live.textContent = "";
    requestAnimationFrame(() => {
      this.#dom.live.textContent = text;
    });
  }

  #onScroll() {
    if (this.closest("[hidden]")) return; // écran masqué : la position n'est pas celle de la personne
    const { log, toEnd } = this.#dom;
    this.#top = log.scrollTop;
    const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight <= BOTTOM_PX;
    this.#following = atBottom;
    toEnd.hidden = atBottom;
  }
}

if (!customElements.get("wl-chat-thread")) customElements.define("wl-chat-thread", WlChatThread);
