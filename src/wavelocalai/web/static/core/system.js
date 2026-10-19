// État du système dans le store (AD-6, AD-10) : un seul abonnement à `/api/system/stream` pour
// toute la page. Le flux dit l'état d'Ollama, du poste et des runs actifs toutes les 2 s, et
// `carbon_updated` à chaque réponse mesurée. `/api/health` donne l'identité du serveur : un
// `instance_id` qui change veut dire que le serveur a redémarré (les runs en cours sont perdus).
//
// Onglet masqué (`visibilitychange`) : le flux est fermé, plus rien ne se met à jour ; au retour il
// est rouvert, et la réouverture relit `/api/health` et `GET /api/carbon/session` (les
// `carbon_updated` manqués pendant la pause ne se rejouent pas).

import { api } from "./api.js";
import { connectSystem } from "./sse.js";
import { store } from "./store.js";

const CHECK_TIMEOUT_MS = 4000;
const HEALTH_RETRY_MS = 2000;

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
    systemSeen: true,
    system: {
      cpuPercent: data.cpu_percent ?? null,
      memory: data.memory ?? null,
      modelsLoaded: data.models_loaded ?? null,
      modelsInUse: data.models_in_use ?? {}, // tag -> run racine qui l'emploie (story 5.4)
      gpu: data.gpu ?? null, // champ absent sans NVML : l'écran Sobriété dit « Aucun »
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

// Chaque `carbon_updated` avance ce compteur : une lecture partie avant n'écrase pas sa somme.
let carbonEvents = 0;

function onCarbonUpdated(data) {
  carbonEvents += 1;
  store.set({ carbon: data });
}

async function readCarbon() {
  const seen = carbonEvents;
  try {
    const carbon = await api.carbonSession();
    if (seen === carbonEvents) store.set({ carbon });
  } catch {
    // Le prochain `carbon_updated` ou la prochaine ouverture du flux le rétablira.
  }
}

let current = null;

// « Réessayer » depuis un écran (cartes de l'Accueil) : la même demande que le panneau Ollama.
export function recheckOllama() {
  current?.recheck();
}

export function startSystem() {
  let wasOpen = false;
  let stream = null;

  // Sans identité connue, un redémarrage ne se voit pas : une lecture de santé en échec est
  // reprise tant que le flux reste ouvert. Onglet masqué, le flux est fermé et la reprise s'arrête
  // (`connection.status` garde sa dernière valeur pendant la pause : on teste aussi `stream`).
  let healthTimer = null;
  function readHealthWhileOpen() {
    clearTimeout(healthTimer);
    readHealth().catch(() => {
      healthTimer = setTimeout(() => {
        if (stream && store.get().connection.status === "open") readHealthWhileOpen();
      }, HEALTH_RETRY_MS);
    });
  }

  function open() {
    stream = connectSystem(
      {
        system_state: onSystemState,
        carbon_updated: onCarbonUpdated,
      },
      ({ status, failures }) => {
        store.set({ connection: { status, failures } });
        if (status !== "open") return;
        // Première ouverture ou reconnexion : identité du serveur et somme du CO2 à jour.
        const reconnected = wasOpen;
        wasOpen = true;
        readHealthWhileOpen();
        if (reconnected) readCarbon();
      },
    );
  }

  function close() {
    clearTimeout(healthTimer);
    healthTimer = null;
    stream?.close();
    stream = null;
  }

  function onVisibility() {
    if (document.hidden) close();
    else if (!stream) open();
  }

  if (!document.hidden) open();
  document.addEventListener("visibilitychange", onVisibility);
  readCarbon();

  const system = {
    // « Réessayer » (panneau Ollama) : reconnecte tout de suite si le flux est perdu, sinon attend
    // le prochain état du flux (au plus 2 s) ; l'état d'attente tombe de lui-même.
    recheck() {
      store.set({ ollamaChecking: true });
      stream?.retryNow();
      setTimeout(() => store.set({ ollamaChecking: false }), CHECK_TIMEOUT_MS);
    },
    close() {
      document.removeEventListener("visibilitychange", onVisibility);
      close();
      if (current === system) current = null;
    },
  };
  current = system;
  return system;
}
