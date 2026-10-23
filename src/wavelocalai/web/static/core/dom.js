// Aides DOM partagées : icône du sprite, élément avec classe et texte.

const SVG_NS = "http://www.w3.org/2000/svg";

// Une icône du sprite `icons.svg` (`i-<name>`), décorative : le texte voisin porte le sens.
// `extraClass` (story 9.7) : classes ajoutées à "icon", par exemple "icon-mod arena" pour une icône
// de module colorée sur sa pastille (base.css).
export function icon(name, extraClass) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", extraClass ? `icon ${extraClass}` : "icon");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", `/static/icons.svg#i-${name}`);
  svg.append(use);
  return svg;
}

// Titre d'écran avec son icône de module colorée (story 9.7, `.icon-mod`, base.css). `modClass` :
// "arena" | "bench" | "docs" | "models", ou omis pour un titre sans icône de module.
export function moduleTitle(iconName, modClass, text) {
  const h1 = element("h1", "");
  h1.append(icon(iconName, modClass ? `icon-mod ${modClass}` : undefined), document.createTextNode(text));
  return h1;
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
