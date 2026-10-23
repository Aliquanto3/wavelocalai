// Panneau de la fiche d'un modèle sur l'écran Modèles (story 5.6, UX-DR27, D-8, D-40) : à droite de la
// liste dès 1 120 px, au-dessus en deçà, ouvert par `#/modeles/<tag>` (un clic sur un modèle des
// tableaux). La fiche vient de `GET /api/models/card/<tag>` (`components/model-card-loader.js`) : le
// front ne calcule rien (AD-20).
//
// - « Fermer la fiche » est un lien vers `#/modeles` : l'adresse suit l'état du panneau.
// - Un modèle pas installé porte « Installer ce modèle » (« Installer quand même » s'il ne tient pas,
//   D-42) : le même geste que le catalogue, bloqué avec sa raison pendant une installation.
// - La fiche se relit quand une installation finit (le modèle est alors installé) et quand la
//   raison d'un bouton change (installation en cours, Ollama muet).

import { createCardLoader } from "../components/model-card-loader.js";
import { element } from "../core/dom.js";
import { t } from "../core/i18n.js";
import { setCurrentCardTag } from "./models-format.js";

export function createCard({ onInstall, blockedReason, onChange }) {
  let tag = null;

  const panel = element("aside", "models-fiche");
  panel.id = "models-fiche";
  panel.setAttribute("aria-label", t("models.card.aria"));
  panel.hidden = true;
  const close = element("a", "btn models-fiche-close", t("models.card.close"));
  close.href = "#/modeles";
  const body = element("div", "models-card-body");
  panel.append(close, body);

  const loader = createCardLoader({
    container: body,
    headingId: "models-card-title",
    backHref: "#/modeles",
    options: () => ({ onInstall: (target) => onInstall(target), installBlocked: blockedReason() }),
  });

  return {
    el: panel,
    get tag() {
      return tag;
    },
    // Ouvre la fiche de `next` (ou la ferme si `null`). Rend vrai quand elle est affichée.
    async open(next, { focus = true } = {}) {
      if (next === null || next === undefined || next === "") {
        tag = null;
        setCurrentCardTag(null);
        panel.hidden = true;
        loader.clear();
        onChange(null);
        return false;
      }
      tag = next;
      setCurrentCardTag(next);
      panel.hidden = false;
      onChange(next);
      const shown = await loader.open(next);
      // L'adresse a pu changer pendant la lecture : on ne déplace le focus que pour la fiche à jour.
      if (focus && tag === next) loader.heading?.focus({ preventScroll: false });
      return shown;
    },
    // Rend de nouveau la fiche ouverte : la raison de « Installer » a changé.
    refresh: () => loader.refresh(),
    // Relit la fiche ouverte (une installation vient de finir : le modèle est installé).
    reload: () => (tag === null ? false : loader.open(tag)),
  };
}
