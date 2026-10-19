// Groupe de segments (EXPERIENCE.md, règles communes) : `role="radiogroup"` de boutons `role="radio"`,
// un seul arrêt de tabulation, flèches pour changer, le choix porte l'icône `check` (jamais la seule
// couleur). « Matrice · Tableau » de l'Arène ; repris par les Références, la Sobriété et l'Évaluation.
//
//   const seg = segments({ label, options: [{ value, label }], value, onChange });
//   host.append(seg.root); seg.select(valeur, { focus, silent }); seg.value
//
// `onChange(valeur)` est appelé quand la personne change de segment (pas pour `select(…, { silent })`).

import { element, icon } from "../core/dom.js";

const STEPS = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };

export function segments({ label, options, value, onChange }) {
  const root = element("div", "wl-seg");
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
    const button = element("button", "wl-seg-button");
    button.type = "button";
    button.setAttribute("role", "radio");
    button.dataset.value = option.value;
    button.append(icon("check"), element("span", "", option.label));
    button.addEventListener("click", () => select(option.value));
    button.addEventListener("keydown", (event) => {
      if (!(event.key in STEPS)) return;
      event.preventDefault();
      const index = options.findIndex((candidate) => candidate.value === value);
      select(options[(index + STEPS[event.key] + options.length) % options.length].value, { focus: true });
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
