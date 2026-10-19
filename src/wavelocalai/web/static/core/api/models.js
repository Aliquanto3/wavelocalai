// Appels « modèles » : liste unique, défauts par usage, déchargement mémoire.

export function modelsApi(request) {
  return {
    // Liste unique des modèles (AD-15) : sans `allowCloud`, aucun modèle cloud (AD-9).
    models: (allowCloud) => request(`/api/models?allow_cloud=${allowCloud ? "true" : "false"}`),
    modelDefaults: (purpose, allowCloud) =>
      request(
        `/api/models/defaults?purpose=${encodeURIComponent(purpose)}&allow_cloud=${allowCloud ? "true" : "false"}`,
      ),
    // Décharge les modèles Ollama qu'aucun run actif n'emploie (garde-fou mémoire, story 4.8).
    unloadModels: () => request("/api/models/unload", { method: "POST", timeoutMs: 20000 }),
  };
}
