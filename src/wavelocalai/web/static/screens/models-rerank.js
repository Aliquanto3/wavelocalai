// « Reclassement des extraits » de l'écran Modèles (story 5.5, AD-5, AD-17, UX-DR27 ; fastembed en
// dépendance de base depuis la story 9.5, D-R6) : le reranker local que la recherche documentaire
// emploie pour remettre les extraits dans l'ordre de pertinence.
//
// L'état vient de `GET /api/rag/settings` (`reranker: {model, available, reason}`) ; le front ne le
// devine pas et ne calcule rien (AD-20). Trois états :
// - « Installé » : rien à faire ;
// - « Non installé » avec la raison du serveur et « Installer le reranker », actif dès `uv sync` seul ;
// - « Installation en cours » : la barre de progression chiffrée et « Annuler » du run `pull`, que ce
//   module n'écrit pas (`models-pull.js`) : il en range seulement le nœud ici.
// Un clic est le seul geste qui télécharge (AD-17). Une autre installation en cours désactive le
// bouton, avec sa raison.

import { element } from "../core/dom.js";
import { t } from "../core/i18n.js";

export function createRerank({ pull, onInstall }) {
  let settings = null; // { model, available, reason } ; null : pas encore lu
  let unknown = false; // la lecture a échoué

  const title = element("h2", "section-label", t("models.rerank.title"));
  title.id = "models-rerank-title";
  const lead = element("p", "help", t("models.rerank.lead"));
  const status = element("p", "models-rerank-status");
  status.setAttribute("role", "status");
  const reason = element("p", "help models-reason");
  reason.id = "models-rerank-reason";
  const button = element("button", "btn models-install-reranker", t("models.rerank.install"));
  button.type = "button";
  button.setAttribute("aria-describedby", reason.id);
  const download = element("p", "help", t("models.rerank.download_help"));
  const progressHost = element("div", "models-rerank-progress");
  const section = element("section", "models-section models-rerank");
  section.setAttribute("aria-labelledby", title.id);
  section.append(title, lead, status, reason, button, download, progressHost);

  button.addEventListener("click", () => {
    if (button.getAttribute("aria-disabled") === "true" || settings === null) return;
    onInstall(settings.model);
  });

  // Pourquoi « Installer le reranker » est désactivé, ou null.
  function blockedReason() {
    if (pull.busy) return t("models.rerank.busy", { tag: pull.activeTag ?? "…" });
    return null;
  }

  function render() {
    const installing = pull.busy && pull.activeReranker;
    if (installing) {
      progressHost.replaceChildren(pull.progress.el);
    } else if (pull.failedReranker) {
      progressHost.replaceChildren(pull.failureNode);
    } else {
      progressHost.replaceChildren();
    }
    progressHost.hidden = progressHost.childElementCount === 0;

    if (settings === null) {
      status.textContent = unknown ? t("models.rerank.status_unknown") : "";
      reason.textContent = unknown ? t("models.rerank.unknown") : "";
      reason.hidden = !unknown;
      button.hidden = true;
      download.hidden = true;
      return;
    }
    if (settings.available && !installing) {
      status.textContent = t("models.rerank.status_on");
      reason.textContent = t("models.rerank.on_help", { model: settings.model });
      reason.hidden = false;
      button.hidden = true;
      download.hidden = true;
      return;
    }
    status.textContent = installing
      ? t("models.rerank.status_installing")
      : t("models.rerank.status_off");
    button.hidden = installing;
    download.hidden = installing;
    const blocked = installing ? null : blockedReason();
    button.setAttribute("aria-disabled", String(blocked !== null));
    button.setAttribute("aria-label", t("models.rerank.install_aria", { model: settings.model }));
    if (installing) {
      reason.textContent = "";
      reason.hidden = true;
    } else if (blocked !== null) {
      reason.textContent = blocked;
      reason.hidden = false;
    } else {
      // Non installé : la raison dite par le serveur (extra présent, modèle absent du cache).
      reason.textContent = settings.reason ? t("models.rerank.reason", { reason: settings.reason }) : "";
      reason.hidden = !settings.reason;
    }
  }

  return {
    el: section,
    setSettings(value) {
      settings = value;
      unknown = false;
      render();
    },
    setUnknown() {
      settings = null;
      unknown = true;
      render();
    },
    render,
    get installed() {
      return settings?.available === true;
    },
  };
}
