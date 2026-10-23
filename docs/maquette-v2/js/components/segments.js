// Groupe de segments (EXPERIENCE.md, règles communes) : `role="radiogroup"` de boutons `role="radio"`,
// un seul arrêt de tabulation, flèches pour changer, le choix porte l'icône `check` (jamais la seule
// couleur). Commun à l'Arène, aux Références, à la Sobriété et à l'Évaluation.
//
//   const seg = segments({label, options: [{value, label}], value, onChange, className});
//   host.append(seg.root); seg.select(valeur, {focus, silent}); seg.value
//
// `onChange(valeur)` est appelé quand la personne change de segment (pas pour `select(…, {silent})`).
// `className` ajoute un préfixe propre à l'écran (`<p>-seg`, `<p>-seg-button`) aux classes communes.

import { element, icon } from "../core/dom.js";

export function segments({ label, options, value, onChange, className = "" }) {
  const root = element("div", className ? `wl-seg ${className}-seg` : "wl-seg");
  root.setAttribute("role", "radiogroup");
  root.setAttribute("aria-label", label);
  const buttons = new Map();
  const select = (next, { focus = false, silent = false } = {}) => {
    value = next;
    for (const [id, button] of buttons) {
      const on = id === value;
      button.setAttribute("aria-checked", String(on));
      button.tabIndex = on ? 0 : -1;
      if (on && focus) button.focus();
    }
    if (!silent) onChange?.(value);
  };
  for (const option of options) {
    const button = element("button", className ? `wl-seg-button ${className}-seg-button` : "wl-seg-button");
    button.type = "button";
    button.setAttribute("role", "radio");
    button.dataset.value = option.value;
    button.append(icon("check"), element("span", "", option.label));
    button.addEventListener("click", () => select(option.value));
    button.addEventListener("keydown", (event) => {
      const keys = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
      if (!(event.key in keys)) return;
      event.preventDefault();
      const index = options.findIndex((candidate) => candidate.value === value);
      const target = options[(index + keys[event.key] + options.length) % options.length];
      select(target.value, { focus: true });
    });
    buttons.set(option.value, button);
    root.append(button);
  }
  select(value, { silent: true });
  return {
    root,
    select,
    get value() {
      return value;
    },
  };
}
