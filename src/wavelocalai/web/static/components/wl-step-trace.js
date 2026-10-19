// <wl-step-trace> : la trace des étapes d'un agent (UX-DR28, AD-6, AD-20, story 6.4). Une liste
// ordonnée (`ol`), une ligne par événement `step` du serveur, dans l'ordre où elles arrivent.
//
//   trace.add(step)                 // un `step` du flux : { step_id, agent, kind, tool, arguments,
//                                   //   summary, duration_s, failed, artifact_url, stopped }
//   trace.note({ text, tone })      // une issue à inscrire dans la trace (ok, refused, expired, failed)
//   trace.setCurrent(state)         // "running" : la dernière étape est marquée « en cours » si c'est un
//                                   //   appel d'outil (les autres sont terminées) ; "approval" : « En
//                                   //   attente de votre validation » ; null : rien n'est en cours
//   trace.labelOf = (toolId) => …   // libellé d'un outil (défaut : son identifiant)
//   trace.maxTurns = n              // borne de tours de la tâche, dite à l'étape d'arrêt (facultatif)
//   trace.clear()   trace.count
//
// Générique : le champ `agent` de l'étape (`null` en agent seul, le nom de l'agent en équipe, 6.6) est
// affiché quand il existe. Motif APG « disclosure » : chaque étape qui a un détail est un bouton
// (`aria-expanded`, `aria-controls`) ; l'ajout d'une étape n'écrit que sa propre ligne, si bien qu'une
// étape dépliée le reste et que le focus ne bouge pas. La liste n'est pas une région `aria-live` : la
// personne l'explore, et `wl-run-status` annonce le changement d'étape. Le front ne calcule rien :
// durées et textes viennent du serveur, mis en forme seulement (AD-20). Sans Shadow DOM.

import { element, icon } from "../core/dom.js";
import { formatDuration } from "../core/format.js";
import { t } from "../core/i18n.js";

// Symboles du sprite actuel (aucun n'est dessiné à la main avant le sprite officiel).
const ICONS = {
  think: "smart-toy",
  tool_call: "sync",
  tool_result: "check",
  failed: "error",
  answer: "description",
  stopped: "block",
};
const NOTE_ICONS = { ok: "check", refused: "block", expired: "hourglass-empty", failed: "error" };

let counter = 0;

// `artifact_url` est bâti par le serveur (`/api/outputs/<nom>`) : seul un chemin du même site est
// suivi (ni `javascript:`, ni `//hôte`, ni adresse absolue).
function sameOriginPath(url) {
  return typeof url === "string" && url.startsWith("/") && !url.startsWith("//") && !url.includes("\\");
}

function kindOf(step) {
  if (step.kind === "tool_result" && step.failed) return "failed";
  if (step.kind === "answer" && step.stopped) return "stopped";
  return step.kind;
}

export class WlStepTrace extends HTMLElement {
  #list = null;
  #uid = `wl-trace-${++counter}`;
  #steps = [];
  #state = null;
  #marked = null; // l'étape qui porte la marque « en cours »
  labelOf = (toolId) => toolId;
  maxTurns = null;

  connectedCallback() {
    if (this.#list) return;
    this.className = "wl-step-trace";
    this.#list = element("ol", "wl-step-list");
    this.#list.setAttribute("aria-label", t("components.step_trace.label"));
    this.replaceChildren(this.#list);
  }

  get count() {
    return this.#steps.length;
  }

  #label(step) {
    const tool = step.tool ? this.labelOf(step.tool) : "";
    switch (kindOf(step)) {
      case "think":
        return t("components.step_trace.think");
      case "tool_call":
        return t("components.step_trace.tool_call", { tool });
      case "tool_result":
        return t("components.step_trace.tool_result", { tool });
      case "failed":
        return t("components.step_trace.tool_failed", { tool });
      case "stopped":
        return this.maxTurns
          ? t("components.step_trace.stopped_n", { n: this.maxTurns })
          : t("components.step_trace.stopped");
      default:
        return t("components.step_trace.answer");
    }
  }

  // Le contenu qu'on déplie : arguments (JSON mis en forme), résultat, texte de réflexion.
  #detail(step, id) {
    const parts = [];
    const section = (heading, body) => {
      const block = element("div", "wl-step-section");
      block.append(element("p", "wl-step-heading", heading), body);
      parts.push(block);
    };
    if (step.kind === "tool_call") {
      const args = element("pre", "wl-step-code");
      args.textContent = JSON.stringify(step.arguments ?? {}, null, 2);
      section(t("components.step_trace.arguments"), args);
    } else if (step.kind === "think" && step.summary) {
      section(t("components.step_trace.thought"), element("p", "wl-step-text", step.summary));
    } else if (step.kind === "tool_result") {
      if (step.summary) section(t("components.step_trace.result"), element("p", "wl-step-text", step.summary));
      if (sameOriginPath(step.artifact_url)) {
        const link = element("a", "wl-step-file", t("components.step_trace.open_file"));
        link.href = step.artifact_url;
        link.download = "";
        parts.push(link);
      }
    } else if (step.kind === "answer" && step.stopped && step.summary) {
      section(t("components.step_trace.result"), element("p", "wl-step-text", step.summary));
    }
    if (!parts.length) return null;
    const detail = element("div", "wl-step-detail");
    detail.id = id;
    detail.hidden = true;
    detail.append(...parts);
    return detail;
  }

  add(step) {
    if (!this.#list || !step) return;
    const n = this.#steps.length + 1;
    const kind = kindOf(step);
    const item = element("li", "wl-step");
    item.dataset.kind = kind;
    const head = [icon(ICONS[kind] ?? ICONS.tool_result), element("span", "wl-step-label", this.#label(step))];
    if (step.agent) head.push(element("span", "wl-step-agent", step.agent));
    if (typeof step.duration_s === "number") {
      head.push(element("span", "wl-step-duration", formatDuration(step.duration_s)));
    }
    const state = element("span", "wl-step-state");
    state.hidden = true;
    head.push(state);

    const detail = this.#detail(step, `${this.#uid}-detail-${n}`);
    if (detail) {
      const toggle = element("button", "wl-step-toggle");
      toggle.type = "button";
      toggle.setAttribute("aria-expanded", "false");
      toggle.setAttribute("aria-controls", detail.id);
      toggle.append(...head, icon("expand-more"));
      toggle.addEventListener("click", () => {
        const open = detail.hidden;
        detail.hidden = !open;
        toggle.setAttribute("aria-expanded", String(open));
        item.dataset.open = String(open);
      });
      item.append(toggle, detail);
    } else {
      const row = element("div", "wl-step-row");
      row.append(...head);
      item.append(row);
    }
    this.#list.append(item);
    this.#steps.push({ item, state, kind: step.kind });
    this.#mark();
  }

  note({ text, tone = "ok" }) {
    if (!this.#list) return;
    const item = element("li", "wl-step wl-step-note");
    item.dataset.tone = tone;
    const row = element("div", "wl-step-row");
    row.append(icon(NOTE_ICONS[tone] ?? "check"), element("span", "wl-step-label", text));
    item.append(row);
    this.#list.append(item);
    this.#mark();
  }

  setCurrent(state) {
    this.#state = state;
    this.#mark();
  }

  // Seule la dernière étape porte la marque (contour et libellé) : les autres sont terminées. Un
  // appel d'outil est « en cours » jusqu'à son résultat ; une réflexion ou un résultat ne l'est pas.
  // Seules l'ancienne étape marquée et la dernière sont touchées : O(1) par événement.
  #mark() {
    const last = this.#steps.at(-1) ?? null;
    const open =
      last && (this.#state === "approval" || (this.#state === "running" && last.kind === "tool_call"));
    if (this.#marked && this.#marked !== last) this.#paint(this.#marked, null);
    if (last) this.#paint(last, open ? this.#state : null);
    this.#marked = open ? last : null;
  }

  #paint({ item, state }, current) {
    if (current) item.dataset.current = current;
    else delete item.dataset.current;
    state.hidden = !current;
    state.textContent = current ? t(`components.step_trace.state_${current}`) : "";
  }

  clear() {
    this.#steps = [];
    this.#state = null;
    this.#marked = null;
    this.#list?.replaceChildren();
  }
}

if (!customElements.get("wl-step-trace")) customElements.define("wl-step-trace", WlStepTrace);
