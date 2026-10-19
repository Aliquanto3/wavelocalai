// Appels « agents » (stories 6.1 à 6.3) : outils proposés, lancement d'une tâche, réponse à une
// demande de validation.

export function agentsApi(request) {
  return {
    // Les outils de l'agent : `{tools: [{id, label, description, available, reason, sensitive}]}`.
    agentTools: () => request("/api/agents/tools"),
    // Lance une tâche (`mode: "solo"`) : rend `{run_id, conversation_id}` ; `allow_cloud` vient du
    // store, sur chaque commande (AD-9).
    startAgent: (body) => request("/api/agents/runs", { method: "POST", body }),
    // `decision` : `approved` ou `rejected` (jamais `expired`, que seul le serveur dit). Une demande
    // déjà traitée ou expirée rend `409 approval_not_pending`.
    answerApproval: (runId, approvalId, decision) =>
      request(
        `/api/runs/${encodeURIComponent(runId)}/approvals/${encodeURIComponent(approvalId)}`,
        { method: "POST", body: { decision } },
      ),
  };
}
