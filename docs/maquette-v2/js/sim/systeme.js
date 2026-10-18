// Simulation du flux système (`/api/system/stream`, `/api/health`, `/api/carbon/session`) : remplit
// le store comme le ferait static/core/system.js. Rien n'est mesuré ici : les valeurs viennent de
// donnees/commun/systeme.json, avec une petite variation pour donner vie aux cartes « en direct ».
//
// API : startSystem(), recheck(), setOllamaDown(bool), loseConnection(), restoreConnection(),
// restartServer() (voir sim.js pour les runs), recordLeaf({co2, origin, module}), resetCarbon().

import { loadData } from "../core/data.js";
import { setMaquette, store } from "../core/store.js";

let config = null;
let timer = null;
const RETRY_STEPS_MS = [0, 500, 1000]; // trois échecs de suite, puis « perdue » (UX-DR5)

const speed = () => store.get().maquette.speed || 1;
const between = ([low, high]) => low + Math.random() * (high - low);

function ollamaState() {
  const down = store.get().maquette.ollamaDown;
  return { known: true, up: !down, version: down ? null : config.ollama.version, latencyMs: down ? null : config.ollama.latency_ms };
}

function systemState() {
  const state = store.get();
  const busy = state.runsActive.length > 0;
  const memory = config.memory;
  const used = state.maquette.ramGuard
    ? memory.total_gb - memory.ram_guard_free_gb
    : memory.used_gb + (busy ? 2.1 : 0) + (Math.random() - 0.5) * 0.3;
  const down = state.maquette.ollamaDown;
  return {
    cpuPercent: between(busy ? config.cpu_percent.busy : config.cpu_percent.idle),
    memory: { used_gb: Math.round(used * 10) / 10, total_gb: memory.total_gb },
    modelsLoaded: down ? null : state.maquette.noLocalModel ? [] : config.models_loaded,
  };
}

function tick() {
  const state = store.get();
  if (state.connection.status === "open") {
    store.set({ ollama: ollamaState(), ollamaChecking: false, system: systemState(), systemSeen: true });
  }
  timer = setTimeout(tick, config.tick_ms / speed());
}

export async function startSystem() {
  config = await loadData("commun/systeme.json");
  store.set({
    version: config.version,
    cloudProviders: config.cloud_providers,
    instanceId: "instance-a1",
  });
  // Premier état après un court délai : les squelettes de l'Accueil se voient.
  setTimeout(() => {
    store.set({ connection: { status: "open", failures: 0 }, carbon: structuredClone(config.carbon) });
    tick();
  }, config.first_tick_ms / speed());
}

export function systemConfig() {
  return config;
}

// « Réessayer » (panneau Ollama, Accueil) : nouvelle sonde, réponse en un peu plus d'une seconde.
export function recheck() {
  store.set({ ollamaChecking: true });
  setTimeout(() => store.set({ ollama: ollamaState(), ollamaChecking: false }), 1200 / speed());
}

export function setOllamaDown(down) {
  setMaquette({ ollamaDown: down });
  if (store.get().connection.status === "open") {
    store.set({ ollama: ollamaState(), system: systemState() });
  }
}

export function loseConnection() {
  RETRY_STEPS_MS.forEach((delay, index) => {
    setTimeout(() => {
      const failures = index + 1;
      store.set({ connection: { status: failures >= 3 ? "lost" : "retrying", failures } });
    }, delay / speed());
  });
}

export function restoreConnection() {
  store.set({ connection: { status: "open", failures: 0 }, ollama: ollamaState(), system: systemState() });
}

export function markRestarted() {
  store.set({ serverRestarted: true, instanceId: "instance-b2" });
}

function emptyCarbon() {
  return {
    total_mg: 0,
    by_origin: { local: { mg: 0, runs: 0 }, cloud: { mg: 0, runs: 0 } },
    by_module: {},
    measured_runs: 0,
    unmeasurable_runs: 0,
  };
}

// Une feuille terminée (`carbon_updated`) : le total de session suit, les non-mesurables à part.
export function recordLeaf({ co2, origin, module = "chat" }) {
  if (!co2) return;
  const carbon = structuredClone(store.get().carbon ?? emptyCarbon());
  if (co2.mg === null || co2.mg === undefined) {
    carbon.unmeasurable_runs += 1;
  } else {
    const side = origin === "cloud" ? "cloud" : "local";
    carbon.total_mg += co2.mg;
    carbon.by_origin[side].mg += co2.mg;
    carbon.by_origin[side].runs += 1;
    carbon.by_module[module] = { mg: (carbon.by_module[module]?.mg ?? 0) + co2.mg };
    carbon.measured_runs += 1;
  }
  store.set({ carbon });
}

export function resetCarbon() {
  store.set({ carbon: emptyCarbon() });
}

export function stopSystem() {
  clearTimeout(timer);
}
