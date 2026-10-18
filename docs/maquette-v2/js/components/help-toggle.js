// Aide en bouton (même motif que `wl-metric`, pour un texte hors d'une métrique) : un bouton « i »
// (`aria-expanded`, `aria-controls`) déplie le texte d'aide sous lui ; Échap le replie.
//
//   host.append(helpToggle(libellé, texte))

import { element, icon } from "../core/dom.js";
import { t } from "../core/i18n.js";

let helpCounter = 0;

export function helpToggle(label, text) {
  const id = `wl-help-${++helpCounter}`;
  const root = element("span", "wl-help");
  const button = element("button", "wl-help-button");
  button.type = "button";
  button.setAttribute("aria-label", t("components.help_for", { label }));
  button.setAttribute("aria-expanded", "false");
  button.setAttribute("aria-controls", id);
  button.append(icon("info"));
  const body = element("span", "wl-help-text help", text);
  body.id = id;
  body.hidden = true;
  button.addEventListener("click", () => {
    body.hidden = !body.hidden;
    button.setAttribute("aria-expanded", String(!body.hidden));
  });
  button.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !body.hidden) {
      event.stopPropagation();
      body.hidden = true;
      button.setAttribute("aria-expanded", "false");
    }
  });
  root.append(button, body);
  return root;
}

