// Aides DOM partagées : icône du sprite, élément avec classe et texte (repris de static/core/dom.js).

const SVG_NS = "http://www.w3.org/2000/svg";
// Le sprite est à la racine de la maquette : chemin résolu depuis ce module, pas depuis la page.
export const SPRITE = new URL("../../icons.svg", import.meta.url).pathname;

// Une icône du sprite `icons.svg` (`i-<name>`), décorative : le texte voisin porte le sens.
export function icon(name) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", `${SPRITE}#i-${name}`);
  svg.append(use);
  return svg;
}

export function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// Remplace l'icône d'un `<svg>` du HTML (`<use href>`) sans le recréer.
export function setIcon(svg, name) {
  svg.querySelector("use").setAttribute("href", `${SPRITE}#i-${name}`);
}
