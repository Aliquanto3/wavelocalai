// Appels « documents » (RAG) : question aux documents, extraits, base, réglages. L'envoi des
// fichiers (multipart, avec progression) est `uploadDocuments`, dans `core/api.js`.

export function ragApi(request) {
  return {
    // Pose une question aux documents prêts ; `allow_cloud` vient du store, sur chaque commande
    // (AD-9).
    startRag: (body) => request("/api/rag/runs", { method: "POST", body }),
    // Un extrait en entier (« Ouvrir l'extrait ») ; `404 chunk_not_found` s'il n'existe plus.
    chunk: (id) => request(`/api/rag/chunks/${encodeURIComponent(id)}`),
    // Documents de la base (tous statuts), totaux des prêts et plafonds d'un import.
    documents: () => request("/api/rag/documents"),
    // Supprime un document `ready` ou `failed` (AD-13) ; rend `{chunks_removed, ...}`. Le `VACUUM`
    // qui suit réécrit tout le fichier : sur une grosse base, il dépasse largement 30 s.
    deleteDocument: (id) =>
      request(`/api/rag/documents/${encodeURIComponent(id)}`, { method: "DELETE", timeoutMs: 300000 }),
    // Vide la base : `expectedCount` est le nombre d'extraits affiché, le serveur le compare au réel.
    clearBase: (expectedCount) =>
      request(`/api/rag/base?expected_count=${encodeURIComponent(expectedCount)}`, {
        method: "DELETE",
        timeoutMs: 300000,
      }),
    // Réglages de la base (embedding, découpe, nombre d'extraits, stratégie par défaut).
    ragSettings: () => request("/api/rag/settings"),
    saveRagSettings: (body) => request("/api/rag/settings", { method: "PUT", body }),
  };
}
