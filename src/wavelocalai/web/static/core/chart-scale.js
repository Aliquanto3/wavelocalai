// Calculs d'échelle des graphiques SVG faits main (UX-DR14, AD-20) : fonctions pures, sans DOM,
// prouvées par `tests/v2/e2e/test_arena_results.py`. Le front ne calcule aucune mesure (AD-20) : il
// place ce que le serveur a mesuré.
//
// - Un axe part toujours de 0 et sa longueur n'est jamais nulle : un seul point, ou des points
//   alignés, ne resserrent jamais l'axe sur eux.
// - La taille d'un point est une fonction croissante du CO2 ; sans mesure, un rayon fixe (le point
//   est alors tracé en pointillés par l'appelant).

export const CHAR_WIDTH = 6.6; // largeur moyenne d'un caractère à 12 px, sans mesure réelle
export const LINE_HEIGHT = 14;

// Un pas « rond » (1, 2 ou 5 fois une puissance de dix) : au plus `count` graduations.
function niceStep(top, count) {
  const raw = top / count;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / magnitude;
  const factor = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
  return factor * magnitude;
}

// Axe linéaire de 0 au-delà de `maxValue` (marge de 10 %), avec ses graduations.
// -> { min: 0, max, ticks: [0, step, 2 step, …] }, toujours au moins deux graduations.
export function linearAxis(values, { count = 5, headroom = 1.1 } = {}) {
  const known = values.filter((value) => typeof value === "number" && Number.isFinite(value) && value > 0);
  const top = known.length ? Math.max(...known) * headroom : 1;
  const step = niceStep(top, count);
  const steps = Math.max(1, Math.ceil(top / step - 1e-9));
  const ticks = Array.from({ length: steps + 1 }, (_, index) => Number((index * step).toPrecision(12)));
  return { min: 0, max: ticks[steps], ticks };
}

// Rayon d'un point : de `min` (CO2 nul) à `min + span` (le plus grand CO2 du graphique), la surface
// suivant le CO2. Un CO2 non mesuré (`null`) n'a pas de rayon proportionnel : `unknown`.
export function bubbleRadius(mg, maxMg, { min = 7, span = 15, unknown = 9 } = {}) {
  if (typeof mg !== "number" || !Number.isFinite(mg)) return unknown;
  if (!(maxMg > 0)) return min;
  return min + span * Math.sqrt(Math.max(0, mg) / maxMg);
}

// Les tailles montrées par la légende : le plus petit et le plus grand CO2 mesurés (un seul si égaux).
export function legendSizes(values) {
  const known = values.filter((value) => typeof value === "number" && Number.isFinite(value));
  if (!known.length) return [];
  const low = Math.min(...known);
  const high = Math.max(...known);
  return low === high ? [high] : [low, high];
}

// Coupe un nom en lignes d'au plus `max` (en unités de `width`, par défaut des caractères), aux
// espaces ; un mot trop long (un tag comme `mistral-small3.2:24b-instruct-2506`) est coupé après un
// `:`, `-`, `.`, `_` ou `/`, puis au caractère s'il dépasse encore : aucune ligne ne déborde.
export function wrapLabel(name, max, width = (text) => text.length) {
  const fits = (text) => width(text) <= max;
  const pieces = []; // { text, space } : `space` = séparé du précédent par une espace
  for (const word of String(name).split(/\s+/).filter(Boolean)) {
    if (fits(word)) {
      pieces.push({ text: word, space: true });
      continue;
    }
    let first = true;
    for (const part of word.split(/(?<=[:\-._/])/)) {
      let rest = part;
      while (rest) {
        let cut = rest.length;
        while (cut > 1 && !fits(rest.slice(0, cut))) cut--;
        pieces.push({ text: rest.slice(0, cut), space: first });
        first = false;
        rest = rest.slice(cut);
      }
    }
  }
  const lines = [];
  let line = "";
  for (const { text, space } of pieces) {
    const joined = line ? `${line}${space ? " " : ""}${text}` : text;
    if (line && !fits(joined)) {
      lines.push(line);
      line = text;
    } else {
      line = joined;
    }
  }
  if (line) lines.push(line);
  return lines.length ? lines : [""];
}

const overlap = (a, b) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;

// Place l'étiquette de chaque point, à droite du point s'il y a la place, sinon à gauche, sur plusieurs
// lignes si besoin, et décale vers le bas celles qui se chevaucheraient.
// `items` : [{ name, cx, cy, r }] ; `bounds` : { left, right, top, bottom } (zone de tracé) ;
// `unit` : facteur de la police (1 à 12 px ; le mode projection l'agrandit) ; `measure(text)` : la
// largeur réelle du texte en px à cette taille (sinon `CHAR_WIDTH` par caractère).
// -> [{ lines, x, y, anchor: "start" | "end" }] dans l'ordre de `items`.
export function layoutLabels(items, bounds, unit = 1, measure = null) {
  const CHAR = CHAR_WIDTH * unit;
  const LINE = LINE_HEIGHT * unit;
  const textWidth = measure ?? ((text) => text.length * CHAR);
  const placed = [];
  const order = items.map((item, index) => ({ item, index })).sort((a, b) => a.item.cy - b.item.cy);
  const result = new Array(items.length);
  for (const { item, index } of order) {
    const { name, cx, cy, r } = item;
    const gap = r + 6;
    const roomRight = bounds.right - (cx + gap);
    const roomLeft = cx - gap - bounds.left;
    const full = textWidth(String(name));
    const right = roomRight >= full || (roomLeft < full && roomRight >= roomLeft);
    const room = Math.max(CHAR * 6, right ? roomRight : roomLeft);
    const lines = wrapLabel(name, room, textWidth);
    const width = Math.max(...lines.map(textWidth));
    const x = right ? cx + gap : cx - gap;
    let top = cy - (lines.length * LINE) / 2;
    const box = () => ({
      x0: right ? x : x - width,
      x1: right ? x + width : x,
      y0: top,
      y1: top + lines.length * LINE,
    });
    for (let guard = 0; guard < 12; guard++) {
      const clash = placed.find((other) => overlap(box(), other));
      if (!clash) break;
      top = clash.y1;
    }
    top = Math.min(Math.max(top, bounds.top), Math.max(bounds.top, bounds.bottom - lines.length * LINE));
    placed.push(box());
    result[index] = { lines, x, y: top + 11 * unit, anchor: right ? "start" : "end" };
  }
  return result;
}

// --- Graphique en barres (historique carbone, story 5.2) -----------------------------------------

// Bandes d'un graphique en barres : une par barre, réparties de `left` à `right`. Une barre occupe
// `1 - gap` de sa bande, au plus `maxWidth` ; `center(index)` est le milieu de la bande.
export function barBands(count, left, right, { gap = 0.3, maxWidth = 56 } = {}) {
  const step = count > 0 ? (right - left) / count : right - left;
  return { step, width: Math.min(maxWidth, step * (1 - gap)), center: (index) => left + step * (index + 0.5) };
}

// Hauteur d'une barre en pixels : proportionnelle à la valeur sur l'axe (0 à `axisMax`) ; une valeur
// non nulle garde au moins `minPx` (une barre trop basse disparaîtrait). Nulle ou absente : 0.
export function barHeight(value, axisMax, plotHeight, minPx = 2) {
  if (typeof value !== "number" || !Number.isFinite(value) || !(value > 0) || !(axisMax > 0)) return 0;
  return Math.max(minPx, Math.min(plotHeight, (value / axisMax) * plotHeight));
}

// Une étiquette d'abscisse toutes les `n` barres, pour qu'aucune ne chevauche sa voisine : `n` est le
// plus petit entier tel que `n` bandes de `step` px contiennent une étiquette de `labelWidth` px.
export function labelStride(step, labelWidth, gap = 8) {
  return step > 0 ? Math.max(1, Math.ceil((labelWidth + gap) / step)) : 1;
}
