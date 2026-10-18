// Simulateur de runs : rejoue un script de donnees/flux/<id>.json au format SSE de la spine (AD-6).
// Chaque événement livré est l'enveloppe exacte `{seq, run_id, type, ts, data}` : `seq` part de 1,
// contigu, `run_started` en premier et `run_ended` une seule fois, en dernier ; `ts` en ISO UTC.
//
//   const run = sim.play("chat-libre-reponse", handlers, { vars, speed, kind, origin, module });
//   handlers = { token: (data, envelope) => …, metrics: …, run_ended: …, "*": (data, env) => … }
//   run.stop()          Arrêter : `run_ended {status: "cancelled"}` en moins d'une seconde
//   run.fail(code, d)   erreur injectée : `run_ended {status: "error", error: <enveloppe>}`
//   run.cut(ms)         coupure de connexion : livraison suspendue, bandeau, reprise sans doublon
//   run.detach()        l'écran ferme son flux (le run continue) ; run.attach(handlers, {after})
//                       rejoue ce qui suit `after` (reprise par `?after=<seq>`) puis suit en direct
//   run.done            promesse du statut final ; run.lastSeq, run.status, run.id
//
// Script : `{id, kind, events: [{wait, type, data} | {wait, tokens: {lane, channel, text, tps}}]}`.
// `wait` = délai en ms avant l'événement (`slow_wait` le remplace en « premier chargement lent ») ;
// `tokens` est développé en événements `token` groupés par tranches de 50 ms (AD-6). Une chaîne
// "{{nom}}" est remplacée par `vars.nom` (la valeur garde son type si la chaîne est entière).
// `"when": "{{nom}}"` : l'événement n'est joué que si `vars.nom` est vrai (modèle déjà chargé…).
// Options : `error`/`errorAfter` (code injecté après N événements livrés), `vars`, `speed`.

import { loadData } from "../core/data.js";
import { errorEnvelope } from "../core/errors.js";
import { store } from "../core/store.js";
import { loseConnection, markRestarted, recordLeaf, restoreConnection } from "./systeme.js";

const TOKEN_SLICE_MS = 50;
const CHARS_PER_TOKEN = 4;
const CANCEL_MS = 300; // latence d'annulation simulée (< 1 s, story 2.2)
const runs = new Map();
let counter = 0;

const globalSpeed = () => store.get().maquette.speed || 1;

function substitute(value, vars) {
  if (typeof value === "string") {
    const whole = /^\{\{(\w+)\}\}$/.exec(value);
    if (whole && whole[1] in vars) return vars[whole[1]];
    return value.replace(/\{\{(\w+)\}\}/g, (match, name) => (name in vars ? String(vars[name]) : match));
  }
  if (Array.isArray(value)) return value.map((item) => substitute(item, vars));
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, substitute(item, vars)]));
  }
  return value;
}

// Développe `tokens` en événements `token` de 50 ms de génération chacun.
function expand(events) {
  const out = [];
  for (const event of events) {
    if ("when" in event && !event.when) continue; // "when": "{{var}}" faux : événement omis
    if (!event.tokens) {
      out.push(event);
      continue;
    }
    const { lane, channel = "answer", text, tps = 40 } = event.tokens;
    const perSlice = Math.max(1, Math.round((tps * TOKEN_SLICE_MS * CHARS_PER_TOKEN) / 1000));
    for (let i = 0, first = true; i < text.length; i += perSlice, first = false) {
      out.push({
        wait: first ? (event.wait ?? 0) : TOKEN_SLICE_MS,
        type: "token",
        data: { lane, text: text.slice(i, i + perSlice), channel },
      });
    }
  }
  return out;
}

class SimRun {
  constructor(script, options) {
    this.id = options.runId ?? `run-${script.kind ?? "sim"}-${String(++counter).padStart(4, "0")}`;
    this.kind = options.kind ?? script.kind ?? "chat";
    this.origin = options.origin ?? "local";
    this.module = options.module ?? this.kind;
    this.options = options;
    this.queue = expand(substitute(script.events, options.vars ?? {}));
    this.log = [];
    this.status = "running";
    this.attachments = new Set();
    this.timer = null;
    this.index = 0;
    this.done = new Promise((resolve) => {
      this.resolveDone = resolve;
    });
    store.set((state) => ({ runsActive: [...state.runsActive, { run_id: this.id, kind: this.kind, status: "running" }] }));
    this.unsubscribe = store.select(
      (state) => state.connection.status,
      (status) => {
        if (status === "open") this.flush();
      },
    );
  }

  get lastSeq() {
    return this.log.length;
  }

  get ended() {
    return this.status !== "running";
  }

  speed() {
    return this.options.speed ?? globalSpeed();
  }

  schedule() {
    if (this.ended || this.index >= this.queue.length) return;
    const event = this.queue[this.index];
    const slow = store.get().maquette.slowLoad && event.slow_wait !== undefined;
    const wait = (slow ? event.slow_wait : (event.wait ?? 0)) / this.speed();
    this.timer = setTimeout(() => {
      this.index += 1;
      const injected = this.options.error && this.log.length >= (this.options.errorAfter ?? 3);
      if (injected && event.type !== "run_started") {
        this.fail(this.options.error, this.options.errorDetail);
        return;
      }
      this.emit(event.type, event.data ?? {});
      this.schedule();
    }, wait);
  }

  // Ajoute un événement au journal du run (côté « serveur »), puis le livre aux écrans attachés.
  emit(type, data) {
    if (this.ended) return;
    const envelope = { seq: this.log.length + 1, run_id: this.id, type, ts: new Date().toISOString(), data };
    this.log.push(envelope);
    if (type === "metrics" && data.co2) recordLeaf({ co2: data.co2, origin: data.origin ?? this.origin, module: this.module });
    if (type === "run_ended") this.finish(data.status ?? "ok");
    this.flush();
  }

  finish(status) {
    this.status = status;
    clearTimeout(this.timer);
    this.unsubscribe?.();
    store.set((state) => ({ runsActive: state.runsActive.filter((run) => run.run_id !== this.id) }));
    this.resolveDone(status);
  }

  // Livre à chaque écran attaché les événements qu'il n'a pas encore reçus, si la connexion est là.
  flush() {
    if (store.get().connection.status !== "open" && store.get().connection.status !== "connecting") return;
    for (const attachment of this.attachments) {
      while (attachment.delivered < this.log.length) {
        const envelope = this.log[attachment.delivered];
        attachment.delivered += 1;
        deliver(attachment.handlers, envelope);
      }
    }
  }

  attach(handlers, { after = 0 } = {}) {
    const attachment = { handlers, delivered: Math.max(0, Math.min(after, this.log.length)) };
    this.attachments.add(attachment);
    this.flush();
    return { close: () => this.attachments.delete(attachment) };
  }

  detach() {
    this.attachments.clear();
  }

  stop() {
    if (this.ended || this.stopping) return this.done;
    this.stopping = true;
    clearTimeout(this.timer);
    setTimeout(() => this.emit("run_ended", { status: "cancelled", error: null }), CANCEL_MS / this.speed());
    return this.done;
  }

  fail(code, detail) {
    if (this.ended) return this.done;
    clearTimeout(this.timer);
    this.emit("run_ended", { status: "error", error: errorEnvelope(code, { detail }) });
    return this.done;
  }

  interrupt() {
    if (this.ended) return this.done;
    clearTimeout(this.timer);
    this.emit("run_ended", { status: "interrupted", error: null });
    return this.done;
  }

  // Coupure de connexion pendant `ms` : le run continue côté serveur, la reprise ne double rien.
  cut(ms = 5000) {
    loseConnection();
    setTimeout(() => restoreConnection(), ms / this.speed());
  }
}

function deliver(handlers, envelope) {
  try {
    if (Object.prototype.hasOwnProperty.call(handlers, envelope.type)) handlers[envelope.type](envelope.data, envelope);
    handlers["*"]?.(envelope.data, envelope);
  } catch (error) {
    console.error(`Simulateur : le traitement de « ${envelope.type} » a échoué`, error);
  }
}

export const sim = {
  // Lance un script ; rend le run tout de suite (les événements arrivent ensuite).
  play(scriptId, handlers = {}, options = {}) {
    const placeholder = { kind: options.kind ?? "chat", events: [] };
    const run = new SimRun(placeholder, options);
    runs.set(run.id, run);
    run.ready = loadData(`flux/${scriptId}.json`).then((script) => {
      run.kind = options.kind ?? script.kind ?? run.kind;
      run.queue = expand(substitute(script.events, options.vars ?? {}));
      run.schedule();
      return run;
    });
    run.ready.catch((error) => {
      console.error(error);
      run.fail("internal", { technical: String(error) });
    });
    if (handlers) run.attach(handlers);
    return run;
  },

  // Ce que la commande `POST /api/<module>/runs` refuserait avant de créer un run (réponse 4xx) :
  // l'enveloppe d'erreur, ou null. `origin` : "local" ou "cloud" ; `kind` : un seul run par kind.
  precheck({ origin = "local", kind = "chat", model = null } = {}) {
    const state = store.get();
    const active = [...runs.values()].find((run) => run.kind === kind && !run.ended);
    if (active) return { status: 409, ...errorEnvelope("run_busy", { detail: { run_id: active.id } }) };
    if (origin === "cloud" && !state.allowCloud) {
      return { status: 403, ...errorEnvelope("cloud_not_allowed", { detail: { tag: model?.tag ?? "" } }) };
    }
    if (origin === "cloud" && model && model.available === false) {
      return { status: 400, ...errorEnvelope("cloud_key_missing", { detail: { provider: model.provider, provider_name: model.provider_name, key_var: `${model.provider.toUpperCase()}_API_KEY` } }) };
    }
    if (origin !== "cloud" && state.maquette.ollamaDown) return { status: 503, ...errorEnvelope("ollama_down") };
    if (origin !== "cloud" && state.maquette.ramGuard) return { status: 507, ...errorEnvelope("ram_guard") };
    return null;
  },

  get(runId) {
    return runs.get(runId) ?? null;
  },

  active(kind) {
    return [...runs.values()].find((run) => run.kind === kind && !run.ended) ?? null;
  },

  // Client du flux d'un run (équivalent de `connectRun`) : rejoue après `after` puis suit.
  attach(runId, handlers, { after = 0 } = {}) {
    const run = runs.get(runId);
    if (!run) return { close() {} };
    return run.attach(handlers, { after });
  },

  cancel(runId) {
    return runs.get(runId)?.stop() ?? Promise.resolve(null);
  },

  // Le serveur redémarre : chaque run non terminé reçoit un `run_ended {status: "interrupted"}`.
  restartServer() {
    for (const run of runs.values()) run.interrupt();
    markRestarted();
  },

  // Arrête tout sans bruit (réinitialisation de la maquette).
  reset() {
    for (const run of runs.values()) {
      run.detach();
      if (!run.ended) {
        clearTimeout(run.timer);
        run.finish("cancelled");
      }
    }
    runs.clear();
  },
};
