// État du système dans le store (AD-6, AD-10) : un seul abonnement à `/api/system/stream` pour
// toute la page. Le flux dit l'état d'Ollama, du poste et des runs actifs toutes les 2 s, et
// `carbon_updated` à chaque réponse mesurée. `/api/health` donne l'identité du serveur : un
// `instance_id` qui change veut dire que le serveur a redémarré (les runs en cours sont perdus).

import { api } from "./api.js";
import { connectSystem } from "./sse.js";
import { store } from "./store.js";

const CHECK_TIMEOUT_MS = 4000;

function applyOllama(ollama) {
  return {
    known: true,
    up: ollama.up === true,
    version: ollama.version ?? null,
    latencyMs: ollama.latency_ms ?? null,
  };
}

function onSystemState(data) {
  store.set({
    ollama: applyOllama(data.ollama ?? {}),
    ollamaChecking: false,
    system: {
      cpuPercent: data.cpu_percent ?? null,
      memory: data.memory ?? null,
      modelsLoaded: data.models_loaded ?? null,
    },
    runsActive: Array.isArray(data.runs_active) ? data.runs_active : [],
  });
}

// Lit l'identité du serveur. Rend true si ce n'est plus le serveur déjà connu.
async function readHealth() {
  const health = await api.health();
  const known = store.get().instanceId;
  const restarted = known !== null && known !== health.instance_id;
  store.set((state) => ({
    instanceId: health.instance_id,
    serverRestarted: state.serverRestarted || restarted,
    version: health.version,
    cloudProviders: health.cloud_providers ?? [],
    // Avant le premier tick du flux, l'état d'Ollama vient de la sonde de `/api/health`.
    ollama: state.ollama.known ? state.ollama : applyOllama(health.ollama),
  }));
  return restarted;
}

async function readCarbon() {
  try {
    store.set({ carbon: await api.carbonSession() });
  } catch {
    // Le prochain `carbon_updated` ou la prochaine ouverture du flux le rétablira.
  }
}

export function startSystem() {
  let wasOpen = false;
  const stream = connectSystem(
    {
      system_state: onSystemState,
      carbon_updated: (data) => store.set({ carbon: data }),
    },
    ({ status, failures }) => {
      store.set({ connection: { status, failures } });
      if (status !== "open") return;
      // Première ouverture ou reconnexion : identité du serveur et somme du CO2 à jour.
      const reconnected = wasOpen;
      wasOpen = true;
      readHealth().catch(() => {});
      if (reconnected) readCarbon();
    },
  );
  readCarbon();

  return {
    // « Réessayer » (panneau Ollama) : reconnecte tout de suite si le flux est perdu, sinon attend
    // le prochain état du flux (au plus 2 s) ; l'état d'attente tombe de lui-même.
    recheck() {
      store.set({ ollamaChecking: true });
      stream.retryNow();
      setTimeout(() => store.set({ ollamaChecking: false }), CHECK_TIMEOUT_MS);
    },
    close: stream.close,
  };
}
