// Appels « conversations » : lancer un chat et retrouver, exporter, effacer les conversations
// (AD-5, AD-13).

export function conversationsApi(request) {
  return {
    // Lance une réponse de chat ; `allow_cloud` vient du store, sur chaque commande (AD-9).
    startChat: (body) => request("/api/chat/runs", { method: "POST", body }),
    // Les plus récentes d'un genre, une conversation, son effacement, et l'adresse de ses exports
    // (`json`, `md`), téléchargés par un lien et non par `fetch`.
    conversations: (kind, limit = 1) =>
      request(`/api/conversations?kind=${encodeURIComponent(kind)}&limit=${limit}`),
    conversation: (id) => request(`/api/conversations/${encodeURIComponent(id)}`),
    deleteConversation: (id) =>
      request(`/api/conversations/${encodeURIComponent(id)}`, { method: "DELETE" }),
    conversationExportUrl: (id, extension) =>
      `/api/conversations/${encodeURIComponent(id)}.${extension}`,
  };
}
