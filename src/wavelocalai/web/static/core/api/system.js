// Appels « système » : santé du serveur, CO₂ de la session et sa méthode (équivalence en voiture),
// son historique par session close et la remise à zéro du compteur, identité de la machine.

export function systemApi(request) {
  return {
    health: () => request("/api/health"),
    carbonSession: () => request("/api/carbon/session"),
    systemIdentity: () => request("/api/system/identity"),
    carbonMethod: () => request("/api/carbon/method"),
    // `window` : "7d", "30d" ou "all" ; une ligne par session close (story 5.2).
    carbonHistory: (window) => request(`/api/carbon/history?window=${encodeURIComponent(window)}`),
    resetCarbonSession: () => request("/api/carbon/session/reset", { method: "POST" }),
  };
}
