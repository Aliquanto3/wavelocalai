// Validation d'un email par la personne (D2, AD-9, story 6.4) : `approval_required` ouvre
// `wl-confirm-dialog` (destinataire, objet, corps, mention de l'expiration, focus sur « Annuler ») ;
// la réponse part par `POST /api/runs/{id}/approvals/{approval_id}`. Rien ne dit « envoyé » avant le
// serveur : l'issue est inscrite dans la trace quand `approval_resolved` arrive (refusé, expiré) ou,
// pour un accord, quand le `tool_result` de l'envoi confirme (ou non) l'email.
//
// - `approval_resolved` venu du serveur (délai écoulé, run annulé) ferme le dialogue sans réponse.
// - Écran masqué : le dialogue est fermé sans réponse (`suspend`), rouvert au retour (`resume`) si la
//   demande attend toujours ; le serveur, lui, garde sa demande jusqu'à l'expiration.
// - Une réponse tardive (`409 approval_not_pending`) est dite sans erreur technique.
// - Un autre échec de la réponse rouvre le dialogue : la personne peut réessayer.

import { api, ApiError } from "../core/api.js";
import { t } from "../core/i18n.js";

function delayText(seconds) {
  const minutes = seconds / 60;
  if (seconds >= 60 && Number.isInteger(minutes)) return t("agents.approval.minutes", { n: minutes });
  return t("agents.approval.seconds", { n: Math.round(seconds) });
}

export function createApproval({ dialog, trace, runId, say, fail }) {
  let pending = null; // { id, data, resolved, suspended, answered }
  let awaitingResult = null; // call_id d'un accord dont on attend le `tool_result`

  async function ask(request) {
    while (pending === request && !request.resolved && !request.suspended) {
      const { data } = request;
      const confirmed = await dialog.ask({
        title: t("agents.approval.title"),
        consequence: t("agents.approval.note", { delay: delayText(data.expiry_s) }),
        confirmLabel: t("agents.approval.confirm"),
        details: [
          { label: t("agents.approval.to"), value: data.destinataire },
          { label: t("agents.approval.subject"), value: data.objet },
          { label: t("agents.approval.body"), value: data.corps, long: true },
        ],
      });
      // Fermé par le serveur ou par l'écran masqué : ce n'est pas un « Annuler ».
      if (pending !== request || request.resolved || request.suspended) return;
      try {
        await api.answerApproval(runId(), request.id, confirmed ? "approved" : "rejected");
        request.answered = true; // répondue : un retour sur l'écran avant `approval_resolved` ne la rouvre pas
        return;
      } catch (failure) {
        const envelope = failure instanceof ApiError ? failure.envelope : null;
        if (failure instanceof ApiError && failure.status === 409 && envelope?.code === "approval_not_pending") {
          request.answered = true;
          say(t("agents.approval.late"));
          return;
        }
        fail(envelope ?? { code: "internal", message: t("agents.approval.answer_failed") });
      }
    }
  }

  return {
    required(data) {
      pending = { id: data.approval_id, data, resolved: false, suspended: false, answered: false };
      ask(pending);
    },

    resolved(data) {
      const request = pending;
      if (request && request.id === data.approval_id) {
        request.resolved = true;
        pending = null;
        dialog.close();
      }
      if (data.decision === "approved") {
        awaitingResult = request?.data.call_id ?? null;
        return;
      }
      const text = t(data.decision === "expired" ? "agents.approval.expired" : "agents.approval.refused");
      trace.note({ text, tone: data.decision === "expired" ? "expired" : "refused" });
      say(text);
    },

    // Le résultat de l'envoi approuvé : « Email envoyé. » seulement si l'outil a réussi.
    toolResult(step) {
      if (awaitingResult === null || step.call_id !== awaitingResult) return;
      awaitingResult = null;
      const ok = !step.failed;
      const text = t(ok ? "agents.approval.sent" : "agents.approval.send_failed");
      trace.note({ text, tone: ok ? "ok" : "failed" });
      say(text);
    },

    suspend() {
      if (!pending || pending.resolved) return;
      pending.suspended = true;
      dialog.close();
    },

    resume() {
      if (!pending || pending.resolved || !pending.suspended) return;
      if (pending.answered) return; // déjà répondue : seul `approval_resolved` reste attendu
      pending.suspended = false;
      ask(pending);
    },

    reset() {
      if (pending) pending.resolved = true;
      pending = null;
      awaitingResult = null;
      dialog.close();
    },
  };
}
