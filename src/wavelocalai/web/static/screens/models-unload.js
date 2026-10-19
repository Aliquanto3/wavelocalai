// « Décharger les modèles inactifs » (story 5.4, AD-6, AD-9) : libère la mémoire avant une démo.
// `POST /api/models/unload` décharge les modèles Ollama qu'aucun run actif n'emploie ; la colonne
// « Chargé » et la mémoire libre suivent le flux système (le serveur le publie aussitôt).
//
// - Le bouton est `aria-disabled` (focalisable, clic sans effet) avec sa raison écrite à côté :
//   Ollama muet, aucun modèle chargé, ou tous employés par une réponse en cours. Tant que le flux
//   système n'a rien dit des modèles chargés, le serveur tranche.
// - Le résultat est annoncé (zone polie `say`) : « 2 modèles déchargés. », puis ce qui est gardé
//   (un run actif l'emploie) ou refusé par Ollama. Une erreur va dans `wl-error` (`onProblem`).
// - Aucun calcul (AD-20) : les listes viennent du serveur.

import { api, ApiError } from "../core/api.js";
import { element } from "../core/dom.js";
import { plural } from "../core/format.js";
import { t } from "../core/i18n.js";
import { store } from "../core/store.js";
import { usedBy } from "./models-format.js";

export function createUnload({ say, onProblem, nameOf }) {
  const button = element("button", "btn models-unload", t("models.actions.unload"));
  button.type = "button";
  const why = element("p", "help models-reason");
  why.id = "models-unload-reason";
  const el = element("div", "models-unload-box");
  el.append(button, why);
  let busy = false;

  // Pourquoi il n'y a rien à décharger, ou null.
  function blockedReason(state) {
    if (state.ollama.known && !state.ollama.up) return t("models.actions.unload_ollama_down");
    const loaded = state.system.modelsLoaded;
    if (loaded === null) return null;
    if (loaded.length === 0) return t("models.actions.unload_none");
    if (loaded.every((model) => usedBy(state.system.modelsInUse, model.tag) !== null)) {
      return t("models.actions.unload_busy");
    }
    return null;
  }

  function render(reason) {
    why.hidden = reason === null;
    why.textContent = reason ?? "";
    button.setAttribute("aria-disabled", String(busy || reason !== null));
    if (reason === null) button.removeAttribute("aria-describedby");
    else button.setAttribute("aria-describedby", why.id);
  }

  function message(result) {
    const parts = [
      result.unloaded.length
        ? plural("models.actions.unloaded", result.unloaded.length)
        : t("models.actions.unloaded_none"),
    ];
    if (result.kept.length) {
      const names = result.kept.map((item) => nameOf(item.tag)).join(", ");
      parts.push(t("models.actions.unload_kept", { names }));
    }
    if (result.failed.length) {
      parts.push(t("models.actions.unload_failed", { names: result.failed.map(nameOf).join(", ") }));
    }
    return parts.join(" ");
  }

  button.addEventListener("click", async () => {
    if (busy || button.getAttribute("aria-disabled") === "true") return;
    busy = true;
    render(blockedReason(store.get()));
    onProblem(null);
    try {
      say(message(await api.unloadModels()));
    } catch (failure) {
      onProblem(
        failure instanceof ApiError && failure.envelope
          ? failure.envelope
          : {
              code: "internal",
              message: t("models.actions.unload_error"),
              action: t("models.actions.unload_error_action"),
            },
      );
    } finally {
      busy = false;
      render(blockedReason(store.get()));
    }
  });

  // Le bouton suit le flux système : modèles chargés, runs actifs, Ollama.
  const unsubscribe = store.select((state) => blockedReason(state), render);

  return { el, dispose: unsubscribe };
}
