// Supprimer un modèle installé (story 5.4, UX-DR12, AD-9, AD-18, AD-20) : « Supprimer » n'agit jamais
// au premier clic, il ouvre `wl-confirm-dialog` (titre en question, conséquence chiffrée, focus sur
// « Annuler »). Si le modèle est un défaut choisi pour un ou plusieurs usages, le dialogue le dit
// avant la confirmation (D-41) : ces usages reviendront à la règle automatique.
//
// - `DELETE /api/models/{tag}` : Ollama supprime le modèle, le serveur purge ses faits et ramène les
//   défauts à la règle. `409 model_in_use` (un run actif l'emploie, même s'il a démarré depuis
//   l'ouverture du dialogue) et les autres échecs vont dans `wl-error` (`onProblem`) ; la liste est
//   relue (`onDone`) dans tous les cas.
// - L'issue est annoncée (zone polie `say`) : « Modèle supprimé : qwen3.5:2b (2,7 Go libérés). ».
// - Les Go libérés sont la taille que le serveur a donnée du modèle : aucun calcul (AD-20).

import { api, ApiError } from "../core/api.js";
import { formatGb } from "../core/format.js";
import { t } from "../core/i18n.js";

const LIST = new Intl.ListFormat("fr", { style: "long", type: "conjunction" });

export function createDeleter({ say, onProblem, onDone, usagesOf }) {
  const dialog = document.createElement("wl-confirm-dialog");
  let busy = false;

  // `model` : la ligne de `GET /api/models` (tag, nom, taille).
  async function ask(model) {
    if (busy) return;
    onProblem(null);
    const hasSize = model.size_gb !== null && model.size_gb !== undefined;
    let consequence = hasSize
      ? t("models.delete.consequence", { tag: model.tag, size: formatGb(model.size_gb) })
      : t("models.delete.consequence_nosize", { tag: model.tag });
    const usages = usagesOf(model.tag);
    if (usages.length) {
      consequence += ` ${t("models.delete.default", { usages: LIST.format(usages) })}`;
    }
    const confirmed = await dialog.ask({
      title: t("models.delete.title", { tag: model.tag }),
      consequence,
      confirmLabel: t("models.delete.confirm"),
    });
    if (!confirmed) return; // « Annuler » : rien n'est supprimé, le focus revient au bouton
    busy = true;
    let deleted = false;
    try {
      await api.deleteModel(model.tag);
      deleted = true;
      say(
        hasSize
          ? t("models.delete.done", { name: model.name, size: formatGb(model.size_gb) })
          : t("models.delete.done_nosize", { name: model.name }),
      );
    } catch (failure) {
      onProblem(
        failure instanceof ApiError && failure.envelope
          ? failure.envelope
          : {
              code: "model_delete_failed",
              message: t("models.delete.failed", { name: model.name }),
              action: t("models.delete.failed_action"),
            },
      );
    } finally {
      busy = false;
      await onDone({ deleted });
    }
  }

  return { el: dialog, ask };
}
