// Rouvrir une comparaison par son adresse (story 3.6, AD-5, correct course) : `#/arene/comparer/<run_id>`.
//
//   const reopen = reopenView(uid, follow);   reopen.el  reopen.open(runId)
//
// Avant de suivre le flux (qui rejoue le run depuis la base, sans relancer de modèle), l'écran lit
// l'instantané du run : un identifiant inconnu (`404 run_not_found`) dit « Résultat introuvable » avec un
// lien vers une nouvelle comparaison, une comparaison effacée (AD-13 : plus de texte, le CO2 reste au
// registre) le dit de même (écart ouvert n° 8 de la proposition de changement du 19 octobre : variante
// la plus proche du critère actuel, même titre, phrase distincte). Un serveur qui ne répond pas laisse le
// flux dire la connexion perdue.

import { api, ApiError } from "../core/api.js";
import { element } from "../core/dom.js";
import { t } from "../core/i18n.js";

export function reopenView(uid, follow) {
  const title = element("h2", "", t("arena.missing.title"));
  title.id = `${uid}-missing-title`;
  const text = element("p", "");
  const link = element("a", "btn", t("arena.missing.new"));
  link.href = "#/arene/comparer";
  const el = element("section", "arena-missing");
  el.setAttribute("role", "alert");
  el.setAttribute("aria-labelledby", title.id);
  el.hidden = true;
  el.append(title, text, link);

  const show = (reason) => {
    text.textContent = t(`arena.missing.${reason}`);
    el.hidden = false;
  };

  return {
    el,
    async open(runId) {
      el.hidden = true;
      let missing = null;
      try {
        const snapshot = await api.run(runId);
        if (snapshot?.erased) missing = "erased";
      } catch (failure) {
        if (failure instanceof ApiError && failure.envelope?.code === "run_not_found") missing = "unknown";
        // Autre échec : le flux réessaie et dit la connexion perdue.
      }
      if (!el.isConnected) return; // l'écran a été remplacé pendant la lecture
      if (missing) show(missing);
      else follow(runId);
    },
  };
}
