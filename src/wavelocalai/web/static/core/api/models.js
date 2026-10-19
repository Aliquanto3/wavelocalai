// Appels « modèles » : liste unique, défauts par usage, déchargement mémoire.

export function modelsApi(request) {
  return {
    // Liste unique des modèles (AD-15) : sans `allowCloud`, aucun modèle cloud (AD-9).
    models: (allowCloud) => request(`/api/models?allow_cloud=${allowCloud ? "true" : "false"}`),
    modelDefaults: (purpose, allowCloud) =>
      request(
        `/api/models/defaults?purpose=${encodeURIComponent(purpose)}&allow_cloud=${allowCloud ? "true" : "false"}`,
      ),
    // Catalogue installable (`config/models_catalog.json` moins les modèles installés), avec la
    // mémoire nécessaire et `fits` calculés par le serveur (story 5.3).
    installableModels: () => request("/api/models/catalog"),
    // Installe un modèle : run racine `pull`, `{run_id}` aussitôt ; la progression se lit par le flux
    // du run. `409 run_busy` (`detail.run_id`) : une installation tourne déjà (story 5.3).
    pullModel: (tag) => request("/api/models/pull", { method: "POST", body: { tag } }),
    // Décharge les modèles Ollama qu'aucun run actif n'emploie (garde-fou mémoire, story 4.8).
    unloadModels: () => request("/api/models/unload", { method: "POST", timeoutMs: 20000 }),
  };
}
