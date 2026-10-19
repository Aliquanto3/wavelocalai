// Éléments du formulaire de l'Arène, extraits de `arena.js` (plafond de taille des fichiers du front).

import { element, icon } from "../core/dom.js";
import { saveDraft } from "../core/drafts.js";
import { t } from "../core/i18n.js";

export const SCENARIOS = ["popularize", "extract", "summarize", "translate"];

// Les scénarios d'exemple : un clic remplace la question (et son brouillon), puis rend le focus.
export function scenarioFieldset(question, draft, onPick) {
  const scenarios = element("fieldset", "arena-scenarios");
  scenarios.append(element("legend", "", t("arena.scenarios")));
  const row = element("div", "arena-scenario-row");
  for (const id of SCENARIOS) {
    const button = element("button", "btn", t(`arena.scenario.${id}.label`));
    button.type = "button";
    button.addEventListener("click", () => {
      question.value = t(`arena.scenario.${id}.prompt`);
      saveDraft(draft, question.value);
      onPick();
      question.focus();
    });
    row.append(button);
  }
  scenarios.append(row, element("p", "help", t("arena.scenarios_help")));
  return scenarios;
}

// Sans modèle local prêt (D-11) : `alert-info` qui dit quoi faire, au-dessus du formulaire.
export function noLocalNotice() {
  const el = element("p", "wl-notice wl-notice-info");
  el.setAttribute("role", "status");
  const text = element("span", "");
  el.append(icon("info"), text); // masqué ou non par l'écran, dès le montage
  return { el, text };
}
