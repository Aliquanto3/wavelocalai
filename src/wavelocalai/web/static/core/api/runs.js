// Appels « runs » : instantané et annulation d'un run, tous écrans confondus.

export function runsApi(request) {
  return {
    // Instantané d'un run (AD-5) : statut, mesures des feuilles et, pour une Arène, son `verdict`.
    run: (runId) => request(`/api/runs/${encodeURIComponent(runId)}`),
    cancelRun: (runId) =>
      request(`/api/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" }),
  };
}
