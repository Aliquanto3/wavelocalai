// <wl-chart-svg> : nuage de points SVG fait main, accessible (UX-DR14, AD-20). Sans dépendance, sans
// Shadow DOM. Note en ordonnée, débit en abscisse, taille du point = CO2, nom complet en étiquette.
//
//   chart.chart = {
//     title, desc,                         // `<title>` et `<desc>` du SVG
//     points: [{ name, x, y, mg }],        // `mg` : CO2 en mg, ou null (non mesurable : contour en pointillés)
//     xAxis: { label }, yAxis: { label, max, ticks },
//     size: { title, format(mg), unmeasurable, note },   // légende de taille, en HTML
//     seeTable: { label, onClick } | null, // bouton qui mène au tableau équivalent
//     missing: "…" | null,                 // phrase des modèles non placés
//   };
//
// - Les couleurs sont les jetons `chart-1` à `chart-4` (CSS) ; chaque point garde son contour
//   d'encre et son nom écrit : aucune information ne tient à la couleur seule.
// - Les axes partent de 0 (`core/chart-scale.js`) : jamais resserrés sur un seul point.
// - Le SVG suit la largeur du composant (la police reste à 12 px) : il se redessine au
//   redimensionnement. Le bouton « Voir le tableau » est créé une fois : le focus survit aux mises à jour.

import { element } from "../core/dom.js";
import { formatInteger, formatNumber } from "../core/format.js";
import { bubbleRadius, layoutLabels, legendSizes, linearAxis } from "../core/chart-scale.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const BASE_MARGIN = { left: 52, right: 16, top: 14, bottom: 50 };
const MIN_WIDTH = 260;
const MAX_WIDTH = 736;
let counter = 0;

function svgNode(tag, attrs = {}, text = null) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  if (text !== null) node.textContent = text;
  return node;
}

export class WlChartSvg extends HTMLElement {
  #uid = `wl-chart-${++counter}`;
  #chart = null;
  #plot = null;
  #legend = null;
  #button = null;
  #missing = null;
  #observer = null;
  #projection = null;
  #width = 0;

  get chart() {
    return this.#chart;
  }
  set chart(value) {
    this.#chart = value ?? null;
    this.#render();
  }

  connectedCallback() {
    this.#build();
    this.#observer = new ResizeObserver(() => {
      const width = Math.round(this.#plot.clientWidth);
      if (width && width !== this.#width) this.#render();
    });
    this.#observer.observe(this.#plot);
    // Le mode projection agrandit la police : le tracé suit (marges, étiquettes).
    this.#projection = new MutationObserver(() => this.#render());
    this.#projection.observe(document.documentElement, { attributes: true, attributeFilter: ["data-projection"] });
    this.#render();
  }

  disconnectedCallback() {
    this.#observer?.disconnect();
    this.#projection?.disconnect();
    this.#observer = null;
    this.#projection = null;
  }

  // Le bouton qui mène au tableau (pour le focus rendu par l'écran).
  get seeTableButton() {
    return this.#button;
  }

  #build() {
    if (this.#plot) return;
    this.className = "wl-chart";
    this.#plot = element("div", "wl-chart-plot");
    this.#legend = element("div", "wl-chart-legend");
    this.#button = element("button", "btn wl-chart-see-table");
    this.#button.type = "button";
    this.#button.addEventListener("click", () => this.#chart?.seeTable?.onClick());
    this.#missing = element("p", "help wl-chart-missing");
    this.replaceChildren(this.#plot, this.#legend, this.#button, this.#missing);
  }

  #render() {
    if (!this.isConnected || !this.#plot) return;
    const chart = this.#chart;
    const seeTable = chart?.seeTable;
    this.#button.hidden = !seeTable;
    if (seeTable) this.#button.textContent = seeTable.label;
    this.#missing.hidden = !chart?.missing;
    this.#missing.textContent = chart?.missing ?? "";
    if (!chart || !chart.points.length) {
      this.#plot.replaceChildren();
      this.#legend.replaceChildren();
      return;
    }
    this.#width = Math.round(this.#plot.clientWidth);
    this.#plot.replaceChildren(this.#svg(chart));
    this.#legend.replaceChildren(...this.#legendNodes(chart));
  }

  #svg(chart) {
    // Le texte du SVG suit la police de la page (mode projection) : marges et interlignes aussi.
    const unit = (parseFloat(getComputedStyle(document.documentElement).fontSize) || 16) / 16;
    const MARGIN = Object.fromEntries(Object.entries(BASE_MARGIN).map(([side, size]) => [side, size * unit]));
    const W = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, this.#width || MAX_WIDTH));
    const H = Math.round(Math.min(380 * unit, Math.max(250 * unit, W * 0.58)));
    const bottom = H - MARGIN.bottom;
    const right = W - MARGIN.right;
    const xAxis = linearAxis(chart.points.map((point) => point.x));
    const yMax = chart.yAxis.max ?? 100;
    const x = (value) => MARGIN.left + (value / xAxis.max) * (right - MARGIN.left);
    const y = (value) => bottom - (value / yMax) * (bottom - MARGIN.top);
    const maxMg = Math.max(0, ...chart.points.map((point) => (typeof point.mg === "number" ? point.mg : 0)));

    const svg = svgNode("svg", {
      viewBox: `0 0 ${W} ${H}`,
      width: W,
      height: H,
      class: "wl-chart-svg",
      role: "img",
      focusable: "false",
      "aria-labelledby": `${this.#uid}-title ${this.#uid}-desc`,
    });
    const add = (tag, attrs, text = null, parent = svg) => parent.appendChild(svgNode(tag, attrs, text));
    add("title", { id: `${this.#uid}-title` }, chart.title);
    add("desc", { id: `${this.#uid}-desc` }, chart.desc);
    for (const tick of chart.yAxis.ticks) {
      add("line", { x1: MARGIN.left, x2: right, y1: y(tick), y2: y(tick), class: "wl-chart-grid" });
      add("text", { x: MARGIN.left - 8 * unit, y: y(tick) + 4 * unit, class: "wl-chart-tick", "text-anchor": "end" }, formatInteger(tick));
    }
    for (const tick of xAxis.ticks) {
      add("line", { x1: x(tick), x2: x(tick), y1: MARGIN.top, y2: bottom, class: "wl-chart-grid" });
      add("text", { x: x(tick), y: bottom + 18 * unit, class: "wl-chart-tick", "text-anchor": "middle" }, formatNumber(tick));
    }
    add("line", { x1: MARGIN.left, x2: right, y1: bottom, y2: bottom, class: "wl-chart-axis" });
    add("line", { x1: MARGIN.left, x2: MARGIN.left, y1: MARGIN.top, y2: bottom, class: "wl-chart-axis" });
    add("text", { x: (MARGIN.left + right) / 2, y: H - 10 * unit, class: "wl-chart-axis-title", "text-anchor": "middle" }, chart.xAxis.label);
    const middle = (MARGIN.top + bottom) / 2;
    add(
      "text",
      { x: 14 * unit, y: middle, class: "wl-chart-axis-title", "text-anchor": "middle", transform: `rotate(-90 ${14 * unit} ${middle})` },
      chart.yAxis.label,
    );

    const dots = chart.points.map((point, index) => {
      const known = typeof point.mg === "number";
      const r = bubbleRadius(point.mg, maxMg);
      const dot = add("circle", {
        cx: x(point.x),
        cy: y(point.y),
        r,
        class: known ? "wl-chart-dot" : "wl-chart-dot is-unknown",
        "data-name": point.name,
      });
      dot.style.setProperty("--dot", `var(--color-chart-${(index % 4) + 1})`);
      return { name: point.name, cx: x(point.x), cy: y(point.y), r };
    });
    const labels = layoutLabels(dots, { left: MARGIN.left, right, top: MARGIN.top, bottom }, unit);
    labels.forEach((label) => {
      const text = add("text", { x: label.x, y: label.y, class: "wl-chart-label", "text-anchor": label.anchor });
      label.lines.forEach((line, index) => {
        text.appendChild(svgNode("tspan", { x: label.x, dy: index ? 14 * unit : 0 }, line));
      });
    });
    return svg;
  }

  #legendNodes(chart) {
    const { size, points } = chart;
    const nodes = [element("p", "wl-chart-legend-title", size.title)];
    const list = element("ul", "wl-chart-sizes");
    const measured = points.map((point) => point.mg).filter((mg) => typeof mg === "number");
    const maxMg = Math.max(0, ...measured);
    const item = (mg, text) => {
      const entry = element("li", "wl-chart-size");
      const dot = svgNode("svg", { class: "wl-chart-size-dot", viewBox: "0 0 44 44", "aria-hidden": "true", focusable: "false" });
      const known = mg !== null;
      const circle = svgNode("circle", {
        cx: 22,
        cy: 22,
        r: Math.min(21, bubbleRadius(mg, maxMg)),
        class: known ? "wl-chart-dot" : "wl-chart-dot is-unknown",
      });
      circle.style.setProperty("--dot", "var(--color-gray-graphic)");
      dot.appendChild(circle);
      entry.append(dot, element("span", "", text));
      return entry;
    };
    for (const mg of legendSizes(measured)) list.append(item(mg, size.format(mg)));
    if (points.some((point) => typeof point.mg !== "number")) list.append(item(null, size.unmeasurable));
    nodes.push(list);
    if (measured.length && size.note) nodes.push(element("p", "help", size.note));
    return nodes;
  }
}

if (!customElements.get("wl-chart-svg")) customElements.define("wl-chart-svg", WlChartSvg);
