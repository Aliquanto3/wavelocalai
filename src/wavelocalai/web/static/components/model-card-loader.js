// Chargeur de la fiche d'un modèle (story 5.6) : lit `GET /api/models/card/<tag>` (jamais avant le
// repère `shell-ready`, AD-15), l'affiche dans un conteneur avec `renderModelCard`, et dit les états :
// chargement, modèle introuvable (`404 model_not_found`), lecture échouée. Une réponse tardive d'un
// modèle déjà quitté est ignorée. Sert le panneau de l'écran Modèles et le panneau d'un sélecteur.
//
//   const loader = createCardLoader({ container, options: () => ({ onInstall, installBlocked }) });
//   await loader.open("qwen3.5:2b");   // charge puis rend ; rend `true` si la fiche est affichée
//   loader.refresh();                  // rend de nouveau la dernière fiche (la raison d'un bouton a changé)
//   loader.clear();

import { api, ApiError } from "../core/api.js";
import { element } from "../core/dom.js";
import { t } from "../core/i18n.js";
import { shellReady } from "../core/shell-ready.js";
import { renderModelCard } from "./model-card-view.js";
import "./wl-error.js";

export function createCardLoader({ container, options = () => ({}), headingId, backHref = null }) {
  let token = 0;
  let current = null; // dernière fiche rendue

  function show(...nodes) {
    container.replaceChildren(...nodes);
  }

  function notFound(tag) {
    const title = element("h2", "models-card-title", t("models.card.not_found_title"));
    title.id = headingId ?? "models-card-title";
    title.tabIndex = -1;
    const nodes = [title, element("p", "", t("models.card.not_found_text", { tag }))];
    if (backHref) {
      const back = element("a", "btn", t("models.card.back"));
      back.href = backHref;
      nodes.push(back);
    }
    show(...nodes);
  }

  function failed(envelope) {
    const problem = document.createElement("wl-error");
    problem.error = envelope ?? {
      code: "card_failed",
      message: t("models.card.failed"),
      action: t("models.card.failed_action"),
    };
    show(problem);
  }

  function draw() {
    if (current === null) return;
    show(...renderModelCard(current, { headingId, ...options() }));
  }

  return {
    async open(tag) {
      const mine = ++token;
      current = null;
      const loading = element("p", "help", t("models.card.loading"));
      loading.setAttribute("role", "status");
      show(loading);
      try {
        await shellReady();
        const card = await api.modelCard(tag);
        if (mine !== token) return false;
        current = card;
        draw();
        return true;
      } catch (failure) {
        if (mine !== token) return false;
        if (failure instanceof ApiError && failure.envelope?.code === "model_not_found") notFound(tag);
        else failed(failure instanceof ApiError ? failure.envelope : null);
        return false;
      }
    },
    refresh: draw,
    clear() {
      token += 1;
      current = null;
      container.replaceChildren();
    },
    get tag() {
      return current?.tag ?? null;
    },
    get heading() {
      return container.querySelector("h2");
    },
  };
}
