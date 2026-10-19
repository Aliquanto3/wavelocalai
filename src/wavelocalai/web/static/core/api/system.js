// Appels « système » : santé du serveur, CO₂ de la session et sa méthode (équivalence en voiture),
// identité de la machine.

export function systemApi(request) {
  return {
    health: () => request("/api/health"),
    carbonSession: () => request("/api/carbon/session"),
    systemIdentity: () => request("/api/system/identity"),
    carbonMethod: () => request("/api/carbon/method"),
  };
}
