// Appels « Banc d'essai » (story 7.4) : les scénarios, lancer un essai, retrouver les passés.

export function benchApi(request) {
  return {
    // Scénarios prédéfinis : consigne système (`instruction`) et format attendu (`schema`, `null` sans
    // format).
    scenarios: () => request("/api/scenarios"),
    // Lance un essai ; `allow_cloud` vient du store, sur chaque commande (AD-9).
    startBench: (body) => request("/api/bench/runs", { method: "POST", body }),
    // Essais passés (les plus récents d'abord).
    benchRuns: (limit = 20) => request(`/api/bench/runs?limit=${encodeURIComponent(limit)}`),
  };
}
