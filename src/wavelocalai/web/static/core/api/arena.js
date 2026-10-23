// Appels « Arène » : lancer une comparaison, retrouver, exporter et effacer les précédentes.

export function arenaApi(request) {
  return {
    // Lance une comparaison de 2 à 4 modèles ; `allow_cloud` vient du store, sur chaque commande
    // (AD-9).
    startArena: (body) => request("/api/arena/runs", { method: "POST", body }),
    // Comparaisons précédentes (les plus récentes d'abord), adresse de leurs exports (`csv`, `md`,
    // téléchargés par un lien et non par `fetch`) et effacement (AD-13) : story 3.6.
    arenaRuns: (limit = 20) => request(`/api/arena/runs?limit=${encodeURIComponent(limit)}`),
    arenaExportUrl: (id, extension) => `/api/arena/runs/${encodeURIComponent(id)}.${extension}`,
    deleteArenaRun: (id) =>
      request(`/api/arena/runs/${encodeURIComponent(id)}`, { method: "DELETE", timeoutMs: 120000 }),
  };
}
