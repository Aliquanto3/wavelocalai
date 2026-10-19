// Tracé en barres de `<wl-chart-svg>` (story 5.2, UX-DR14, AD-20) : une barre par élément, valeur en
// ordonnée, une seule unité. Appelé par `wl-chart-svg.js` quand le graphique porte `bars`.
//
//   chart.chart = {
//     title, desc,                          // `<title>` et `<desc>` du SVG
//     bars: [{ label, value, name }],       // `value` : mg, ou null (non mesuré : pas de barre) ; `name` : titre au survol
//     unmeasured: "non mesuré",             // texte écrit à la place de la barre d'une valeur nulle
//     xAxis: { label }, yAxis: { label },   // l'axe part de 0 (`core/chart-scale.js`)
//     note: "…",                            // phrase sous le graphique (l'unité)
//     seeTable: { label, onClick } | null, missing: null,
//   };
//
// - La valeur est écrite au-dessus de la barre quand sa bande est assez large.
// - Aucune donnée n'est tracée entre deux mesures : une valeur nulle garde sa place, marquée en texte
//   (« non mesuré ») et d'un trait en pointillés au pied de sa bande, sans barre.
// - L'étiquette de chaque barre est écrite ; si elles se chevauchent, une sur `n` est écrite (le
//   tableau donne tout). La couleur ne porte aucune information (jeton `chart-1`, contour d'encre).

import { formatNumber } from "../core/format.js";
import { barBands, barHeight, CHAR_WIDTH, labelStride, linearAxis } from "../core/chart-scale.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const BASE_MARGIN = { left: 56, right: 36, top: 14, bottom: 56 };

function node(tag, attrs = {}, text = null) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, String(value));
  if (text !== null) el.textContent = text;
  return el;
}

// `uid` : préfixe des identifiants ; `width` : largeur disponible ; `unit` : facteur de police.
export function barsSvg(chart, { uid, width, unit }) {
  const M = Object.fromEntries(Object.entries(BASE_MARGIN).map(([side, size]) => [side, size * unit]));
  const W = Math.min(736, Math.max(260, width || 736));
  const H = Math.round(Math.min(380 * unit, Math.max(250 * unit, W * 0.5)));
  const bottom = H - M.bottom;
  const right = W - M.right;
  const plotHeight = bottom - M.top;
  const axis = linearAxis(chart.bars.map((bar) => bar.value));
  const y = (value) => bottom - (value / axis.max) * plotHeight;

  const svg = node("svg", {
    viewBox: `0 0 ${W} ${H}`,
    width: W,
    height: H,
    class: "wl-chart-svg",
    role: "img",
    focusable: "false",
    "aria-labelledby": `${uid}-title ${uid}-desc`,
  });
  const add = (tag, attrs, text = null) => svg.appendChild(node(tag, attrs, text));
  add("title", { id: `${uid}-title` }, chart.title);
  add("desc", { id: `${uid}-desc` }, chart.desc);
  for (const tick of axis.ticks) {
    add("line", { x1: M.left, x2: right, y1: y(tick), y2: y(tick), class: "wl-chart-grid" });
    add("text", { x: M.left - 8 * unit, y: y(tick) + 4 * unit, class: "wl-chart-tick", "text-anchor": "end" }, formatNumber(tick));
  }
  add("line", { x1: M.left, x2: right, y1: bottom, y2: bottom, class: "wl-chart-axis" });
  add("line", { x1: M.left, x2: M.left, y1: M.top, y2: bottom, class: "wl-chart-axis" });
  add("text", { x: (M.left + right) / 2, y: H - 8 * unit, class: "wl-chart-axis-title", "text-anchor": "middle" }, chart.xAxis.label);
  const middle = (M.top + bottom) / 2;
  add(
    "text",
    { x: 14 * unit, y: middle, class: "wl-chart-axis-title", "text-anchor": "middle", transform: `rotate(-90 ${14 * unit} ${middle})` },
    chart.yAxis.label,
  );

  const bands = barBands(chart.bars.length, M.left, right);
  const longest = Math.max(...chart.bars.map((bar) => bar.label.length));
  const stride = labelStride(bands.step, longest * CHAR_WIDTH * unit);
  chart.bars.forEach((bar, index) => {
    const cx = bands.center(index);
    const known = typeof bar.value === "number";
    if (known) {
      const height = barHeight(bar.value, axis.max, plotHeight);
      const rect = add("rect", {
        x: cx - bands.width / 2,
        y: bottom - height,
        width: bands.width,
        height,
        class: "wl-chart-bar",
      });
      rect.appendChild(node("title", {}, bar.name));
      // La valeur au-dessus de la barre quand la bande la porte ; sinon le titre et le tableau la disent.
      if (bands.step >= 44 * unit) {
        add("text", { x: cx, y: Math.max(M.top + 10 * unit, bottom - height - 6 * unit), class: "wl-chart-value", "text-anchor": "middle" }, formatNumber(bar.value));
      }
    } else {
      add("line", { x1: cx - bands.width / 2, x2: cx + bands.width / 2, y1: bottom - 2, y2: bottom - 2, class: "wl-chart-bar-none" });
      const label = add(
        "text",
        { x: cx + 4 * unit, y: bottom - 8 * unit, class: "wl-chart-unmeasured", transform: `rotate(-90 ${cx + 4 * unit} ${bottom - 8 * unit})` },
        chart.unmeasured,
      );
      label.appendChild(node("title", {}, bar.name));
    }
    if (index % stride === 0) {
      add("text", { x: cx, y: bottom + 18 * unit, class: "wl-chart-tick", "text-anchor": "middle" }, bar.label);
    }
  });
  return svg;
}
