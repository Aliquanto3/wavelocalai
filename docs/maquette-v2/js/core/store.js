// Store observable unique (repris de static/core/store.js, AD-20). Même forme que le front livré,
// plus `maquette` : les réglages du simulateur, pilotés par le panneau Scénarios. La bascule cloud
// vit ici seulement : jamais dans `localStorage`, donc désactivée à chaque ouverture (AD-9).

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

export const INITIAL_MAQUETTE = {
  ollamaDown: false, // Ollama arrêté (pastille, Accueil, écrans locaux)
  ramGuard: false, // le prochain run local est bloqué par le garde-fou mémoire
  slowLoad: false, // premier chargement lent (8 à 26 s mesurés) : « Chargement du modèle… » allongé
  noLocalModel: false, // aucun modèle de conversation installé
  livePaused: false, // onglet masqué simulé : les cartes en direct cessent de se mettre à jour
  speed: 1, // vitesse du simulateur (2 = deux fois plus vite)
};

export const store = createStore({
  allowCloud: false,
  connection: { status: "connecting", failures: 0 }, // connecting | open | retrying | lost
  serverRestarted: false,
  instanceId: null,
  version: "2.0.0",
  cloudProviders: [],
  ollama: { known: false, up: false, version: null, latencyMs: null },
  ollamaChecking: false,
  system: { cpuPercent: null, memory: null, modelsLoaded: null },
  systemSeen: false, // le premier état du flux système est arrivé (squelettes de l'Accueil)
  runsActive: [],
  carbon: null,
  runs: {},
  maquette: { ...INITIAL_MAQUETTE },
});

// Raccourci : fusionne dans `maquette`.
export function setMaquette(patch) {
  store.set((state) => ({ maquette: { ...state.maquette, ...patch } }));
}
