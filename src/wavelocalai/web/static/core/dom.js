// Aides DOM partagées : icône du sprite, élément avec classe et texte.

const SVG_NS = "http://www.w3.org/2000/svg";

// Une icône du sprite `icons.svg` (`i-<name>`), décorative : le texte voisin porte le sens.
export function icon(name) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", `/static/icons.svg#i-${name}`);
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
  svg.querySelector("use").setAttribute("href", `/static/icons.svg#i-${name}`);
}
