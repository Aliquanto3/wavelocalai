// Store observable unique (AD-20). Il garde l'état partagé par la barre haute et les écrans :
// connexion au serveur, Ollama, système, CO2 de session, bascule cloud, dernier `seq` des runs
// actifs. La bascule cloud vit ici et nulle part ailleurs : jamais dans `localStorage`, donc
// désactivée à chaque ouverture de la page (AD-9, AD-20).

export function createStore(initial) {
  let state = initial;
  const listeners = new Set();

  function subscribe(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }

  return {
    get: () => state,
    // `patch` : un objet fusionné à plat, ou une fonction `(état) => objet`.
    set(patch) {
      const previous = state;
      state = { ...state, ...(typeof patch === "function" ? patch(state) : patch) };
      for (const listener of [...listeners]) listener(state, previous);
    },
    subscribe,
    // Appelle `listener(valeur)` tout de suite puis à chaque changement de `selector(état)`.
    select(selector, listener) {
      let current = selector(state);
      listener(current);
      return subscribe((next) => {
        const value = selector(next);
        if (!Object.is(value, current)) {
          current = value;
          listener(value);
        }
      });
    },
  };
}

export const store = createStore({
  allowCloud: false,
  connection: { status: "connecting", failures: 0 }, // connecting | open | retrying | lost
  serverRestarted: false,
  instanceId: null,
  version: null,
  cloudProviders: [],
  ollama: { known: false, up: false, version: null, latencyMs: null },
  ollamaChecking: false,
  system: { cpuPercent: null, memory: null, modelsLoaded: null },
  systemSeen: false, // vrai dès le premier état du flux : avant, les cartes montrent un squelette
  runsActive: [],
  carbon: null, // dernière somme de session (GET /api/carbon/session ou carbon_updated)
  runs: {}, // run_id -> { lastSeq } des runs dont un flux est ouvert
});

export function lastSeq(runId) {
  return store.get().runs[runId]?.lastSeq ?? 0;
}

export function markSeq(runId, seq) {
  store.set((state) => ({ runs: { ...state.runs, [runId]: { lastSeq: seq } } }));
}

export function forgetRun(runId) {
  store.set((state) => {
    const { [runId]: _removed, ...runs } = state.runs;
    return { runs };
  });
}
