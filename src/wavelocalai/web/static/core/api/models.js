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
    // Installe le reranker local (modèle fastembed, dépendance de base depuis la story 9.5) : le même
    // run racine `pull`, `{run_id}` aussitôt ; `409 run_busy` si une installation tourne, `422` si le
    // modèle est déjà là (story 5.5).
    pullReranker: () => request("/api/models/reranker/pull", { method: "POST" }),
    // Fiche d'un modèle (story 5.6) : caractéristiques, « Pourquoi ce débit ? » et « Sur d'autres
    // postes » (résultats du banc), tout calculé par le serveur. `404 model_not_found` si inconnu.
    // Le tag garde ses `/` (`hf.co/utilisateur/depot:Q4`), le reste est encodé.
    modelCard: (tag) => request(`/api/models/card/${tag.split("/").map(encodeURIComponent).join("/")}`),
    // Choix explicite du modèle d'un usage (`PUT`, un tag, 2 à 3 pour `arena`) : rend le défaut
    // résultant (`source: preference`) ; `model_not_eligible`, `cloud_not_allowed` sinon (story 5.4).
    setModelDefault: (purpose, tags, allowCloud) =>
      request(`/api/models/defaults/${encodeURIComponent(purpose)}`, {
        method: "PUT",
        body: { tags, allow_cloud: Boolean(allowCloud) },
      }),
    // « Revenir au choix automatique » : efface la préférence de l'usage (204).
    clearModelDefault: (purpose) =>
      request(`/api/models/defaults/${encodeURIComponent(purpose)}`, { method: "DELETE" }),
    // Supprime un modèle installé : `{tag, freed_gb, reverted}` ; `409 model_in_use` si un run
    // l'emploie. Le tag garde ses `/` (un nom `hf.co/utilisateur/depot:Q4`), le reste est encodé.
    deleteModel: (tag) =>
      request(`/api/models/${tag.split("/").map(encodeURIComponent).join("/")}`, {
        method: "DELETE",
        // Au pire : `/api/ps` 2 s, déchargement 10 s, Ollama 20 s, purge 5 s, relecture 8 s.
        timeoutMs: 60000,
      }),
    // Décharge les modèles Ollama qu'aucun run actif n'emploie (garde-fou mémoire, story 4.8).
    unloadModels: () => request("/api/models/unload", { method: "POST", timeoutMs: 20000 }),
  };
}
