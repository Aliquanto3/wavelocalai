// <wl-team-graph> : le schéma d'une équipe d'agents (UX-DR13, UX-DR28, AD-20, story 6.6). Un SVG fait
// main : un nœud par agent, dans l'ordre, des flèches, puis le nœud « Rapport ».
//
//   graph.set(roles, states)   // roles : ["Chercheur", …] ; states : { <rôle>: état }
//                              //   état : "pending" (rien d'affiché), "current", "done", "stopped",
//                              //   "notrun" ; un rôle absent de `states` est « pending »
//
// - Horizontal (de gauche à droite) dès 768 px de large jusqu'à 4 agents ; vertical en deçà ou à
//   5 agents (D-36). L'orientation suit la fenêtre (`matchMedia`), sans rien recalculer d'autre.
// - L'agent actif est marqué par un contour épais et le libellé « en cours » sous le nœud, jamais par
//   la couleur seule ; terminé : coche et « terminé » ; arrêté : « arrêté » ; non lancé : « non
//   lancé » (D-34).
// - Non interactif : `<title>` et `<desc>` lisent l'ordre (« Chercheur, puis Analyste, puis le
//   rapport »). Le front n'invente aucun état : l'écran les déduit des événements du serveur.
// Sans Shadow DOM ; couleurs par `css/components/team-graph.css`.

import { t } from "../core/i18n.js";

const NS = "http://www.w3.org/2000/svg";
const NODE_W = 156;
const NODE_H = 48;
const REPORT_W = 112;
const GAP = 52; // espace d'une flèche
const LABEL_H = 22; // libellé d'état sous un nœud
const PAD = 4; // marge pour le contour épais
const MAX_HORIZONTAL = 4;
const WIDE = "(min-width: 768px)";
const LINE_CHARS = 19; // caractères par ligne dans un nœud (deux lignes au plus)
const STATES = ["current", "done", "stopped", "notrun"];

let counter = 0;

function svgElement(name, attributes = {}, text) {
  const node = document.createElementNS(NS, name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
  if (text !== undefined) node.textContent = text;
  return node;
}

// Le rôle est coupé aux espaces en deux lignes au plus, abrégé au-delà ; son nom entier reste dans le
// `<title>` du nœud.
function lines(role) {
  const out = [""];
  for (const word of role.split(/\s+/).filter(Boolean)) {
    const last = out.length - 1;
    const next = out[last] ? `${out[last]} ${word}` : word;
    if ([...next].length <= LINE_CHARS || !out[last]) out[last] = next;
    else if (out.length < 2) out.push(word);
    else out[last] = next;
  }
  return out.map((line, index) => {
    const chars = [...line];
    const text = chars.length > LINE_CHARS ? `${chars.slice(0, LINE_CHARS - 1).join("")}…` : line;
    return index < out.length - 1 ? `${text} ` : text; // l'espace de coupe garde le texte lisible
  });
}

export class WlTeamGraph extends HTMLElement {
  #roles = [];
  #states = {};
  #uid = `wl-team-${++counter}`;
  #query = null;
  #drawn = "";
  #onChange = () => this.#render();

  connectedCallback() {
    this.className = "wl-team-graph";
    this.#query ??= window.matchMedia(WIDE);
    this.#query.addEventListener("change", this.#onChange);
    this.#render();
  }

  disconnectedCallback() {
    this.#query?.removeEventListener("change", this.#onChange);
  }

  set(roles, states = {}) {
    this.#roles = [...roles];
    this.#states = states;
    this.#render();
  }

  get vertical() {
    return !(this.#query ?? window.matchMedia(WIDE)).matches || this.#roles.length > MAX_HORIZONTAL;
  }

  #node(x, y, width, label, { state = null, report = false } = {}) {
    const group = svgElement("g", { class: "wl-team-node" });
    if (report) group.dataset.report = "";
    if (state) group.dataset.state = state;
    group.append(
      svgElement("title", {}, label),
      svgElement("rect", { x, y, width, height: NODE_H, rx: 6, class: "wl-team-box" }),
    );
    const name = svgElement("text", { class: "wl-team-name", "text-anchor": "middle" });
    const parts = lines(label);
    parts.forEach((part, index) => {
      const dy = parts.length === 1 ? 0 : index === 0 ? -8 : 8;
      const attributes = { x: x + width / 2, y: y + NODE_H / 2 + dy, "dominant-baseline": "central" };
      name.append(svgElement("tspan", attributes, part));
    });
    group.append(name);
    if (state && STATES.includes(state)) {
      const caption = svgElement(
        "text",
        { x: x + width / 2, y: y + NODE_H + 16, class: "wl-team-state", "text-anchor": "middle" },
        t(`components.team_graph.${state}`),
      );
      group.append(caption);
    }
    if (state === "done") {
      // Coche du sprite (Material), en plus du libellé « terminé ».
      group.append(
        svgElement("use", {
          href: "/static/icons.svg#i-check",
          x: x + 6,
          y: y + 6,
          width: 16,
          height: 16,
          class: "wl-team-check",
        }),
      );
    }
    return group;
  }

  #arrow(x1, y1, x2, y2) {
    return svgElement("line", {
      x1,
      y1,
      x2,
      y2,
      class: "wl-team-arrow",
      "marker-end": `url(#${this.#uid}-head)`,
    });
  }

  #render() {
    if (!this.isConnected) return;
    const roles = this.#roles;
    const signature = JSON.stringify([roles, this.#states, this.vertical]);
    if (signature === this.#drawn) return; // rien n'a changé : le dessin reste
    this.#drawn = signature;
    if (!roles.length) {
      this.replaceChildren();
      this.hidden = true;
      return;
    }
    this.hidden = false;
    const vertical = this.vertical;
    const count = roles.length;
    const step = vertical ? NODE_H + LABEL_H + GAP : NODE_W + GAP;
    const width = vertical ? NODE_W + 2 * PAD : count * step + REPORT_W + 2 * PAD;
    const height = vertical
      ? count * step + NODE_H + 2 * PAD
      : NODE_H + LABEL_H + 2 * PAD;
    const svg = svgElement("svg", {
      viewBox: `0 0 ${width} ${height}`,
      class: "wl-team-svg",
      role: "img",
      "aria-labelledby": `${this.#uid}-title ${this.#uid}-desc`,
      "data-orientation": vertical ? "vertical" : "horizontal",
    });
    // Largeur propre (px) : le schéma ne grossit pas au-delà de sa taille de dessin.
    svg.style.maxWidth = `${width}px`;
    const order = [...roles, t("components.team_graph.report_short")];
    const desc = roles.join(t("components.team_graph.then")) + t("components.team_graph.then_report");
    const marker = svgElement("marker", {
      id: `${this.#uid}-head`,
      viewBox: "0 0 10 10",
      refX: 9,
      refY: 5,
      markerWidth: 8,
      markerHeight: 8,
      orient: "auto-start-reverse",
    });
    marker.append(svgElement("path", { d: "M 0 1 L 10 5 L 0 9 z", class: "wl-team-head" }));
    svg.append(
      svgElement("title", { id: `${this.#uid}-title` }, t("components.team_graph.title")),
      svgElement("desc", { id: `${this.#uid}-desc` }, desc),
      svgElement("defs"),
    );
    svg.querySelector("defs").append(marker);
    order.forEach((label, index) => {
      const report = index === count;
      const w = report ? REPORT_W : NODE_W;
      const x = vertical ? PAD : PAD + index * step;
      const y = vertical ? PAD + index * step : PAD;
      if (index > 0) {
        if (vertical) svg.append(this.#arrow(PAD + NODE_W / 2, y - GAP + 4, PAD + NODE_W / 2, y - 4));
        else svg.append(this.#arrow(x - GAP + 4, y + NODE_H / 2, x - 4, y + NODE_H / 2));
      }
      const state = report ? null : (Object.hasOwn(this.#states, label) ? this.#states[label] : "pending");
      svg.append(this.#node(x, y, w, label, { state, report }));
    });
    this.replaceChildren(svg);
  }
}

if (!customElements.get("wl-team-graph")) customElements.define("wl-team-graph", WlTeamGraph);
