// Encart d'alerte « Aucun modèle de représentation installé », Base documentaire (story 9.4, AD-17,
// UX-DR22, maquette story 9.6 du 2026-10-21) : sans modèle d'embedding, il précède tout le reste de
// l'écran, propose « Installer nomic-embed-text » et dit pourquoi la zone de dépôt est désactivée.
//
// - L'état vient de `GET /api/rag/settings` (`embedding_models`) : vide, aucun modèle n'est installé
//   (AD-20, le front ne calcule rien). Le tag proposé et sa taille sont fixes (texte produit) : un
//   seul modèle est proposé ici, jamais une liste.
// - Un clic installe par le même run `pull` que l'écran Modèles (`models-pull.js`, `pull` partagé) :
//   même route, même composant de progression, « Annuler » compris (AD-17, un seul geste télécharge).
// - À la fin (succès), le modèle installé est enregistré comme défaut de représentation
//   (`PUT /api/rag/settings`), puis l'encart disparaît dès que les réglages relus le listent.
// - Ollama absent : le bouton est désactivé avec la raison existante (AD-20, état du flux système).

import { api } from "../core/api.js";
import { element, icon } from "../core/dom.js";
import { t } from "../core/i18n.js";
import { store } from "../core/store.js";
import { createPull } from "./models-pull.js";

const TAG = "nomic-embed-text";

// `host` : l'hôte de l'écran (visibilité du flux SSE, comme l'écran Modèles). `say` : la zone
// polie de l'écran (fin de l'installation). `onChange` : après chaque rendu interne, pour que
// l'écran redessine la zone de dépôt. `onInstalled` : une fois le run `pull` réussi, pour que
// l'écran relise sa propre liste de modèles (le formulaire des réglages).
export function createEmbeddingAlert({ host, say, onChange, onInstalled }) {
  let embeddingModels = null; // `null` : réglages pas encore lus ; tableau sinon
  let ollamaUp = true;
  const problem = document.createElement("wl-error");
  problem.setAttribute("alert", "");

  const pull = createPull({
    host,
    nameOf: () => TAG,
    say,
    onChange: render,
    onEnded: async ({ status }) => {
      if (status !== "ok") return;
      // Le modèle installé devient le défaut enregistré (préférence, AD-15) : jamais un « premier
      // installé » implicite, ni un modèle du `.toml` absent du poste. Base déjà liée à un autre
      // modèle (`embedding_change_needs_clear`) : le réglage reste celui de la base.
      try {
        await api.saveRagSettings({ embedding_model: TAG });
      } catch {
        // la relecture ci-dessous montre l'état réel
      }
      load();
      onInstalled();
    },
    onProblem: (envelope) => {
      problem.error = envelope ?? {
        code: "pull_failed",
        message: t("models.pull.start_failed"),
        action: t("models.pull.start_failed_action"),
      };
    },
  });

  const title = element("h2", "", t("docs.embedding_alert_title"));
  title.id = "docs-embedding-alert-title";
  const text = element("p", "", t("docs.embedding_alert_text", { size: t("docs.embedding_alert_size") }));
  const button = element("button", "btn docs-embedding-alert-install", t("docs.embedding_alert_install"));
  button.type = "button";
  const reason = element("p", "help docs-reason");
  reason.id = "docs-embedding-alert-reason";
  button.setAttribute("aria-describedby", reason.id);
  const download = element("p", "help", t("docs.embedding_alert_download_help"));
  const progressHost = element("div", "docs-embedding-alert-progress");
  // La zone de dépôt désactivée (`documents-base.js`) porte cette phrase en légende (EXPERIENCE.md :
  // jamais par la seule opacité).
  const dropReason = element("p", "help docs-reason");
  dropReason.id = "docs-drop-embedding-reason";
  dropReason.hidden = true;
  const section = element("section", "docs-embedding-alert");
  section.setAttribute("role", "group");
  section.setAttribute("aria-labelledby", title.id);
  section.append(icon("warning"), title, text, button, reason, download, progressHost, problem);
  section.hidden = true;

  button.addEventListener("click", () => {
    if (button.getAttribute("aria-disabled") === "true") return;
    problem.error = null;
    pull.start(TAG);
  });

  // Pourquoi « Installer nomic-embed-text » est désactivé, ou `null`.
  function blockedReason() {
    if (pull.busy) return t("docs.embedding_alert_busy", { tag: pull.activeTag ?? "…" });
    if (!ollamaUp) return t("docs.embedding_alert_ollama_down");
    return null;
  }

  function render() {
    const missing = embeddingModels !== null && embeddingModels.length === 0;
    // Entre la fin du run et la relecture des réglages (qui fait disparaître l'encart), le bouton
    // reste masqué : jamais un aller-retour visible « actif » juste après l'installation.
    const installing =
      missing &&
      ((pull.busy && pull.activeTag === TAG && !pull.activeReranker) ||
        (pull.doneTag === TAG && !pull.doneReranker));
    section.hidden = !missing;
    dropReason.hidden = !missing;
    dropReason.textContent = missing ? t("docs.embedding_alert_drop_reason") : "";
    if (missing) {
      if (installing) progressHost.replaceChildren(pull.progress.el);
      else if (pull.failedTag === TAG && !pull.failedReranker) progressHost.replaceChildren(pull.failureNode);
      else progressHost.replaceChildren();
      progressHost.hidden = progressHost.childElementCount === 0;
      button.hidden = installing;
      download.hidden = installing;
      const blocked = installing ? null : blockedReason();
      button.setAttribute("aria-disabled", String(blocked !== null));
      reason.hidden = installing || blocked === null;
      reason.textContent = installing ? "" : (blocked ?? "");
    } else {
      progressHost.replaceChildren();
      progressHost.hidden = true;
    }
    onChange();
  }

  // Réglages relus à part de `api.documents()` (comme le fait déjà l'écran Discussion) ; un échec
  // laisse l'encart dans son dernier état connu plutôt que de masquer la zone de dépôt à tort.
  async function load() {
    try {
      const settings = await api.ragSettings();
      embeddingModels = Array.isArray(settings?.embedding_models) ? settings.embedding_models : [];
    } catch {
      // pas d'état sûr à afficher
    }
    render();
  }

  // Ollama s'arrête ou revient : le bouton suit le flux système, sans tout relire.
  const unsubscribeOllama = store.select(
    (state) => (state.ollama.known ? state.ollama.up : null),
    (up) => {
      if (up === null) return;
      ollamaUp = up;
      render();
    },
  );

  return {
    el: section,
    dropReasonNode: dropReason,
    load,
    // La zone de dépôt (et les boutons d'import) se désactivent tant que l'encart est visible.
    get blocksImport() {
      return !section.hidden;
    },
    // Écran masqué puis revu : le flux de l'installation suit celui de l'écran (`models-pull.js`).
    setHidden(hidden) {
      pull.setHidden(hidden);
    },
    dispose() {
      unsubscribeOllama();
      pull.dispose();
    },
  };
}
