// Appels « agents » (stories 6.1 à 6.6) : outils proposés, équipes, lancement d'une tâche ou d'une
// mission, réponse à une demande de validation.

export function agentsApi(request) {
  return {
    // Les outils de l'agent : `{tools: [{id, label, description, available, reason, sensitive}]}`.
    agentTools: () => request("/api/agents/tools"),
    // Lance une tâche (`mode: "solo"`) ou une mission (`mode: "crew"`, `crew` et `topic`) : rend
    // `{run_id, conversation_id}` ; `allow_cloud` vient du store, sur chaque commande (AD-9).
    startAgent: (body) => request("/api/agents/runs", { method: "POST", body }),
    // Les équipes en vigueur : `{crews: [{id, label, category, description, topic, modified, agents,
    // tasks}], max_agents}`. La validation rend toujours `200 {valid, errors: [{field, message}]}`.
    agentCrews: () => request("/api/agents/crews"),
    validateCrew: (agents, allowCloud) =>
      request("/api/agents/crews/validate", {
        method: "POST",
        body: { agents, allow_cloud: allowCloud },
      }),
    // Enregistre la modification de l'utilisateur (`422` si invalide) ; rend l'équipe en vigueur.
    saveCrew: (id, agents, allowCloud) =>
      request(`/api/agents/crews/${encodeURIComponent(id)}`, {
        method: "PUT",
        body: { agents, allow_cloud: allowCloud },
      }),
    // « Revenir à l'équipe d'origine » : efface la modification ; rend l'équipe d'origine.
    resetCrew: (id) => request(`/api/agents/crews/${encodeURIComponent(id)}`, { method: "DELETE" }),
    // `decision` : `approved` ou `rejected` (jamais `expired`, que seul le serveur dit). Une demande
    // déjà traitée ou expirée rend `409 approval_not_pending`.
    answerApproval: (runId, approvalId, decision) =>
      request(
        `/api/runs/${encodeURIComponent(runId)}/approvals/${encodeURIComponent(approvalId)}`,
        { method: "POST", body: { decision } },
      ),
  };
}
