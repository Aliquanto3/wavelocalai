// Rouvrir une évaluation par son adresse (story 7.3, D-28) : `#/documents/evaluation/<run_id>`. Avant
// de suivre le flux (qui rejoue le run depuis la base, sans relancer de modèle), l'écran lit
// l'instantané : un identifiant inconnu (`404 run_not_found`, ou un run qui n'est pas une évaluation)
// dit « Résultat introuvable » avec le texte du serveur et un lien vers une nouvelle évaluation ; une
// évaluation effacée (AD-13 : plus de texte) le dit de même. Un serveur qui ne répond pas laisse le
// flux dire la connexion perdue.
//
//   const reopen = reopenView(uid, follow);   reopen.el  reopen.open(runId)

import { api, ApiError } from "../core/api.js";
import { element } from "../core/dom.js";
import { t } from "../core/i18n.js";
import "../components/wl-error.js";

export function reopenView(uid, follow) {
  const title = element("h2", "", t("evaluation.missing.title"));
  title.id = `${uid}-missing-title`;
  const text = element("p", "");
  const error = document.createElement("wl-error");
  const link = element("a", "btn", t("evaluation.missing.new"));
  link.href = "#/documents/evaluation";
  const el = element("section", "eval-missing");
  el.setAttribute("role", "alert");
  el.setAttribute("aria-labelledby", title.id);
  el.hidden = true;
  el.append(title, text, error, link);

  const show = (reason, envelope = null) => {
    text.textContent = t(`evaluation.missing.${reason}`);
    error.error = envelope;
    el.dataset.code = envelope?.code ?? reason;
    el.hidden = false;
  };

  return {
    el,
    hide() {
      el.hidden = true;
    },
    async open(runId) {
      el.hidden = true;
      let missing = null;
      try {
        const snapshot = await api.run(runId);
        if (snapshot && snapshot.kind !== "eval") missing = ["unknown", { code: "run_not_found", message: t("evaluation.missing.unknown") }];
        else if (snapshot?.erased) missing = ["erased", null];
      } catch (failure) {
        if (failure instanceof ApiError && failure.envelope?.code === "run_not_found") missing = ["unknown", failure.envelope];
        // Autre échec : le flux réessaie et dit la connexion perdue.
      }
      if (!el.isConnected) return; // l'écran a été remplacé pendant la lecture
      if (missing) show(...missing);
      else follow(runId);
    },
  };
}
