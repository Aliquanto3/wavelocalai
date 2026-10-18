// Graphiques SVG accessibles (UX-DR14), communs à l'Arène et à l'Évaluation de la qualité.
//
//   svgNode(tag, attrs, text)   nœud SVG (attributs en chaîne)
//   bubbleMatrix({title, desc, points, x, y, size, seeTable, missing, className})
//
// La matrice : nuage de points, note en ordonnée, débit en abscisse (linéaire ou logarithmique), taille
// du point = CO₂ (cercle pointillé = non mesurable), chaque point étiqueté par son nom complet. Le
// SVG porte `role="img"`, `<title>` et `<desc>` (le texte de `desc` liste les points) ; la légende de
// taille est en HTML (lisible par un lecteur d'écran) ; un bouton mène au tableau équivalent.
//
// - `points` : `[{name, x, y, mg}]` (`mg` : nombre, ou null si non mesurable) ; la couleur suit l'ordre.
// - `x` : `{label, log?, min?, max?, ticks?}` ; sans `ticks` ni `max`, l'échelle linéaire part de 0 et
//   s'arrondit au-dessus du plus grand point. `y` : `{label, max: 100, ticks}`.
// - `size` : `{title, format(mg), unmeasurable, note}` ; `seeTable` : `{label, onClick}` ;
//   `missing` : phrase des modèles non placés (ou null).

import { element } from "../core/dom.js";
import { formatInteger } from "../core/format.js";

const SVG_NS = "http://www.w3.org/2000/svg";
let counter = 0;

export function svgNode(tag, attrs = {}, text = null) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  if (text !== null && text !== undefined) node.textContent = text;
  return node;
}

function linearAxis(points, axis) {
  if (axis.ticks && axis.max !== undefined) return { min: axis.min ?? 0, max: axis.max, ticks: axis.ticks };
  const top = Math.max(...points.map((point) => point.x), 1) * 1.15;
  const step = top <= 100 ? 20 : top <= 250 ? 50 : 100;
  const max = Math.max(step * 2, Math.ceil(top / step) * step);
  const ticks = [];
  for (let value = 0; value <= max; value += step) ticks.push(value);
  return { min: 0, max, ticks };
}

export function bubbleMatrix({ title, desc, points, x: xAxis, y: yAxis, size, seeTable = null, missing = null, className = "" }) {
  const uid = `wl-matrix-${++counter}`;
  const wrap = element("div", className ? `wl-matrix ${className}-matrix` : "wl-matrix");
  const W = 560;
  const H = 340;
  const M = { left: 58, right: 24, top: 18, bottom: 54 };
  const plotW = W - M.left - M.right;

  const xScale = xAxis.log
    ? (() => {
        const low = Math.log10(xAxis.min);
        const high = Math.log10(xAxis.max);
        const clamp = (value) => Math.min(xAxis.max, Math.max(xAxis.min, value));
        return { ticks: xAxis.ticks, at: (value) => M.left + ((Math.log10(clamp(value)) - low) / (high - low)) * plotW };
      })()
    : (() => {
        const axis = linearAxis(points, xAxis);
        return { ticks: axis.ticks, at: (value) => M.left + ((value - axis.min) / (axis.max - axis.min)) * plotW };
      })();
  const yMax = yAxis.max ?? 100;
  const y = (value) => H - M.bottom - (value / yMax) * (H - M.top - M.bottom);

  const measured = points.map((point) => point.mg).filter((mg) => typeof mg === "number");
  const maxMg = Math.max(...measured, 0.0001);
  const minMg = Math.min(...measured, maxMg);
  const radius = (mg) => 7 + 15 * Math.sqrt(mg / maxMg);

  const svg = svgNode("svg", {
    viewBox: `0 0 ${W} ${H}`,
    class: "wl-matrix-svg",
    role: "img",
    focusable: "false",
    "aria-labelledby": `${uid}-title ${uid}-desc`,
  });
  const add = (tag, attrs, text = null, parent = svg) => parent.appendChild(svgNode(tag, attrs, text));
  add("title", { id: `${uid}-title` }, title);
  add("desc", { id: `${uid}-desc` }, desc);
  for (const value of yAxis.ticks) {
    add("line", { x1: M.left, x2: W - M.right, y1: y(value), y2: y(value), class: "wl-matrix-grid" });
    add("text", { x: M.left - 8, y: y(value) + 4, class: "wl-matrix-tick", "text-anchor": "end" }, formatInteger(value));
  }
  for (const value of xScale.ticks) {
    const at = xScale.at(value);
    add("line", { x1: at, x2: at, y1: M.top, y2: H - M.bottom, class: "wl-matrix-grid" });
    add("text", { x: at, y: H - M.bottom + 18, class: "wl-matrix-tick", "text-anchor": "middle" }, formatInteger(value));
  }
  add("line", { x1: M.left, x2: W - M.right, y1: y(0), y2: y(0), class: "wl-matrix-axis" });
  add("line", { x1: M.left, x2: M.left, y1: M.top, y2: y(0), class: "wl-matrix-axis" });
  add("text", { x: (M.left + W - M.right) / 2, y: H - 10, class: "wl-matrix-axis-title", "text-anchor": "middle" }, xAxis.label);
  const yMid = (M.top + y(0)) / 2;
  add("text", { x: 14, y: yMid, class: "wl-matrix-axis-title", "text-anchor": "middle", transform: `rotate(-90 14 ${yMid})` }, yAxis.label);

  // Points, puis étiquettes décalées pour ne pas se chevaucher.
  const labels = [];
  points.forEach((point, index) => {
    const known = typeof point.mg === "number";
    const r = known ? radius(point.mg) : 9;
    const cx = xScale.at(point.x);
    const cy = y(point.y);
    add("circle", { cx, cy, r, class: known ? "wl-matrix-dot" : "wl-matrix-dot is-unknown", style: `--dot: var(--color-chart-${(index % 4) + 1})` });
    labels.push({ name: point.name, cx, cy, r });
  });
  labels.sort((a, b) => a.cy - b.cy);
  labels.forEach((label, index) => {
    const nearRight = label.cx > W - M.right - 150;
    label.ly = label.cy - label.r - 6;
    if (index > 0) {
      const previous = labels[index - 1];
      if (Math.abs(label.ly - previous.ly) < 15 && Math.abs(label.cx - previous.cx) < 150) label.ly = previous.ly + 15;
    }
    add("text", { x: nearRight ? label.cx + label.r : label.cx - label.r, y: label.ly, class: "wl-matrix-label", "text-anchor": nearRight ? "end" : "start" }, label.name);
  });
  wrap.append(svg);

  // Légende de taille (HTML).
  const legend = element("div", "wl-matrix-legend");
  legend.append(element("p", "wl-matrix-legend-title", size.title));
  const list = element("ul", "wl-matrix-sizes");
  const sizeItem = (mg, dashed, text) => {
    const item = element("li", "wl-matrix-size");
    const dot = svgNode("svg", { class: "wl-matrix-size-dot", viewBox: "0 0 44 44", "aria-hidden": "true", focusable: "false" });
    add("circle", { cx: 22, cy: 22, r: dashed ? 9 : Math.min(21, radius(mg)), class: dashed ? "wl-matrix-dot is-unknown" : "wl-matrix-dot", style: "--dot: var(--color-gray-graphic)" }, null, dot);
    item.append(dot, element("span", "", text));
    return item;
  };
  if (measured.length) {
    list.append(sizeItem(minMg, false, size.format(minMg)));
    if (maxMg !== minMg) list.append(sizeItem(maxMg, false, size.format(maxMg)));
  }
  if (points.some((point) => typeof point.mg !== "number")) list.append(sizeItem(0, true, size.unmeasurable));
  legend.append(list);
  if (measured.length && size.note) legend.append(element("p", "help", size.note));
  wrap.append(legend);
  if (seeTable) {
    const button = element("button", "btn wl-matrix-see-table", seeTable.label);
    button.type = "button";
    button.addEventListener("click", seeTable.onClick);
    wrap.append(button);
  }
  if (missing) wrap.append(element("p", "help", missing));
  return wrap;
}
