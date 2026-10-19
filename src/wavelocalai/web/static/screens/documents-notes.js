// Avertissements de la Discussion sous le sélecteur de modèle (AD-9, AD-20) :
// - modèle cloud : « les extraits retrouvés dans vos documents lui sont envoyés » (écart n° 12) ;
// - stratégie vérifiée (Self-RAG) avec un modèle local de moins de `verify_min_params_b` milliards
//   de paramètres actifs, ou de taille inconnue : « vérification peu fiable ». Comme pour le juge de
//   l'Arène, la taille vient de la fiche du modèle (`params_active_b`) et le seuil du serveur
//   (`GET /api/rag/settings`, `verify_min_params_b`) : rien n'est calculé ni écrit en dur ici.
//
//   const notes = modelNotes({ picker, strategy: () => advanced.strategy() });
//   column.append(picker, ...notes.nodes);
//   notes.update();                     // à chaque changement de modèle ou de stratégie
//   notes.verifyMin = settings.verify_min_params_b;

import { element, icon } from "../core/dom.js";
import { formatNumber } from "../core/format.js";
import { t } from "../core/i18n.js";

export function modelNotes({ picker, strategy }) {
  const cloud = element("p", "docs-cloud-note");
  cloud.hidden = true;
  const verify = element("p", "docs-verify-note");
  verify.hidden = true;

  function show(node, text) {
    node.hidden = text === null;
    node.replaceChildren();
    if (text !== null) node.append(icon("warning"), element("span", "", text));
  }

  const notes = {
    nodes: [cloud, verify],
    verifyMin: null,
    update() {
      const model = picker.selected;
      show(cloud, model?.origin === "cloud" ? t("discussion.cloud_warning", { name: model.name }) : null);
      const min = notes.verifyMin;
      const weak =
        strategy() === "self_rag" &&
        Number.isFinite(min) &&
        model?.origin === "local" &&
        (model.params_active_b == null || model.params_active_b < min);
      show(verify, weak ? t("discussion.verify_weak", { name: model.name, min: formatNumber(min) }) : null);
    },
  };
  return notes;
}
