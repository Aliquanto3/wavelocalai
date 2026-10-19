// Appels « système » : santé du serveur, CO₂ de la session, identité de la machine.

export function systemApi(request) {
  return {
    health: () => request("/api/health"),
    carbonSession: () => request("/api/carbon/session"),
    systemIdentity: () => request("/api/system/identity"),
  };
}
