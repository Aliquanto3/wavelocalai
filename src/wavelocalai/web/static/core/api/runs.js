// Appels « runs » : instantané, annulation et arrêt d'une lane, tous écrans confondus.

export function runsApi(request) {
  return {
    // Instantané d'un run (AD-5) : statut, mesures des feuilles et, pour une Arène, son `verdict`.
    run: (runId) => request(`/api/runs/${encodeURIComponent(runId)}`),
    cancelRun: (runId) =>
      request(`/api/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" }),
    // Arrête une seule lane de l'Arène (story 9.2) : garde et note sa réponse partielle, à la
    // différence de `cancelRun` qui annule tout un run sans rien noter.
    stopLane: (laneRunId) =>
      request(`/api/runs/${encodeURIComponent(laneRunId)}/stop`, { method: "POST" }),
  };
}
