// Appels « Évaluation de la qualité » (story 7.3) : lancer une évaluation et retrouver les passées.

export function evaluationApi(request) {
  return {
    // Lance l'évaluation de 1 à 4 modèles sur une question ou un jeu de questions ; `allow_cloud`
    // vient du store, sur chaque commande (AD-9).
    startEval: (body) => request("/api/rag/eval/runs", { method: "POST", body }),
    // Évaluations passées (les plus récentes d'abord, sans les effacées).
    evalRuns: (limit = 20) => request(`/api/rag/eval/runs?limit=${encodeURIComponent(limit)}`),
  };
}
