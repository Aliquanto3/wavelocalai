// Base documentaire : supprimer un document et vider la base (story 4.3, AD-13, UX-DR12).
//
// - « Supprimer » (une ligne `ready` ou `failed`) et « Vider la base documentaire » ouvrent le
//   même `wl-confirm-dialog` : titre en question, conséquence chiffrée, focus sur « Annuler ».
//   « Annuler » ne supprime rien et l'annonce ; confirmer appelle `DELETE`, puis le résultat est
//   annoncé au même verbe (zone polie).
// - Pendant un import (suivi ici, ou document `indexing` d'un autre onglet), « Supprimer » et
//   « Vider » sont désactivés et leur raison est écrite à côté (`lockId`, décision n° 13 du 2026-10-19).
//   Le serveur reste juge : il répond `409 base_in_use` (import ou question en cours) et `wl-error`
//   l'affiche, par exemple pour une question posée depuis un autre onglet.
// - « Vider » envoie `expected_count`, le nombre d'extraits que l'écran affichait : s'il a changé,
//   le serveur répond `409 base_count_stale` sans rien supprimer, et l'écran relit la base.

import { api, ApiError } from "../core/api.js";
import { element } from "../core/dom.js";
import { t } from "../core/i18n.js";
import { plural } from "./documents-import-row.js";

export function createManage({ dialog, problem, getData, refresh, fallbackFocus, isLocked, lockId }) {
  const status = element("p", "docs-notice docs-manage-status");
  status.setAttribute("role", "status");
  status.hidden = true;
  let working = false; // une confirmation ou une requête est en cours

  // `append` : à la suite du message déjà dit (deux résultats d'un même geste, dans la même zone).
  function say(text, append = false) {
    status.hidden = false;
    status.textContent = append && status.textContent ? `${status.textContent} ${text}` : text;
  }

  function fail(failure) {
    problem.error =
      failure instanceof ApiError && failure.envelope
        ? failure.envelope
        : { code: "manage_failed", message: t("docs.delete_failed"), action: t("docs.delete_failed_action") };
  }

  function focusRow(id) {
    const shown = [...document.querySelectorAll(".docs-delete")].filter(
      (button) => !button.closest("[hidden]"),
    );
    const button = shown.find((candidate) => candidate.dataset.id === id) ?? shown[0];
    (button ?? fallbackFocus())?.focus();
  }

  // Le bouton « Supprimer » d'une ligne `ready` ou `failed` ; rien pour un document `indexing`
  // (« Annuler l'import » l'arrête).
  function deleteButton(doc) {
    if (doc.status === "indexing") return "";
    const button = element("button", "btn docs-delete", t("docs.delete"));
    button.type = "button";
    button.dataset.id = doc.id;
    button.setAttribute("aria-label", t("docs.delete_for", { name: doc.source }));
    if (isLocked?.()) {
      button.disabled = true;
      button.setAttribute("aria-describedby", lockId);
    }
    button.addEventListener("click", () => deleteDocument(doc));
    return button;
  }

  async function deleteDocument(doc) {
    if (working || isLocked?.()) return; // bouton désactivé pendant un import : le serveur reste juge
    working = true;
    problem.error = null;
    try {
      const confirmed = await dialog.ask({
        title: t("docs.delete_title", { name: doc.source }),
        consequence:
          doc.status === "failed"
            ? t("docs.delete_consequence_failed")
            : plural("docs.delete_consequence", doc.chunks),
        confirmLabel: t("docs.delete"),
      });
      if (!confirmed) {
        say(t("docs.delete_cancelled", { name: doc.source }));
        focusRow(doc.id);
        return;
      }
      try {
        const done = await api.deleteDocument(doc.id);
        say(
          done.chunks_removed > 0
            ? plural("docs.deleted", done.chunks_removed, { name: doc.source })
            : t("docs.deleted_none", { name: doc.source }),
        );
      } catch (failure) {
        fail(failure);
      }
      await refresh();
      focusRow(null);
    } finally {
      working = false;
    }
  }

  // Rend vrai si la base a été vidée.
  async function clearBase() {
    const data = getData();
    if (working || !data || isLocked?.()) return false; // pendant un import (décision n° 13)
    working = true;
    problem.error = null;
    try {
      const expected = data.totals.chunks;
      const vars = {
        chunks: plural("docs.chunks", expected),
        documents: plural("docs.documents", data.documents.length),
      };
      const confirmed = await dialog.ask({
        title: t("docs.clear_title"),
        consequence: plural("docs.clear_consequence", expected, vars),
        confirmLabel: t("docs.clear"),
      });
      if (!confirmed) {
        say(t("docs.clear_cancelled"));
        return false;
      }
      let cleared = false;
      try {
        const done = await api.clearBase(expected);
        say(
          plural("docs.cleared", done.chunks_removed, {
            chunks: plural("docs.chunks", done.chunks_removed),
            documents: plural("docs.documents", done.documents_removed),
          }),
        );
        cleared = true;
      } catch (failure) {
        fail(failure);
      }
      await refresh();
      fallbackFocus()?.focus();
      return cleared;
    } finally {
      working = false;
    }
  }

  return { status, say, deleteButton, clearBase };
}
