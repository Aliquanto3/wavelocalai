// Client SSE unique (AD-6, AD-20) : le flux système et les flux de runs passent tous par ici.
//
// Pas de `EventSource` : il se reconnecte sans fin et sans rendre la main. Ce client lit le flux
// par `fetch`, aiguille chaque enveloppe `{seq, run_id, type, ts, data}` par `type` (un type
// inconnu est ignoré, il n'y a pas de champ `event:`), et reprend lui-même avec un délai croissant.
//
// - Flux de run : un `seq` déjà vu est écarté (le dernier `seq` est dans le store), la reprise
//   se fait par `?after=<seq>`, la connexion se ferme à `run_ended` et sur un `204`.
// - Flux système : ni `id:` ni rejeu ; `seq` est informatif, rien n'est écarté.
// - Après `failuresBeforeLost` échecs de suite, l'état passe à `lost` (bandeau « Connexion au
//   serveur perdue ») ; les tentatives continuent.

import { forgetRun, lastSeq, markSeq } from "./store.js";

export const SYSTEM_URL = "/api/system/stream";
const BACKOFF_MS = [500, 1000, 2000, 4000, 8000];
// Le flux système publie toutes les 2 s : 10 s sans un octet veut dire un serveur figé ou une
// connexion morte sans fermeture. La lecture est alors abandonnée et compte comme un échec.
const SYSTEM_IDLE_MS = 10000;

// Découpe un flux de texte en trames (`id`, `data`). Les lignes finissent par \n, \r\n ou \r ;
// une ligne coupée entre deux morceaux est gardée pour le suivant ; un commentaire (`:`) est ignoré.
export class SseParser {
  constructor() {
    this.pending = "";
    this.data = [];
    this.id = null;
    this.skipLf = false; // un \r\n coupé entre deux morceaux
  }

  feed(chunk) {
    let text = this.pending + chunk;
    this.pending = "";
    if (this.skipLf && text.startsWith("\n")) text = text.slice(1);
    this.skipLf = false;
    const frames = [];
    let start = 0;
    for (let i = 0; i < text.length; i++) {
      const char = text[i];
      if (char !== "\n" && char !== "\r") continue;
      this.line(text.slice(start, i), frames);
      if (char === "\r") {
        if (text[i + 1] === "\n") i++;
        else if (i + 1 === text.length) this.skipLf = true;
      }
      start = i + 1;
    }
    this.pending = text.slice(start);
    return frames;
  }

  line(line, frames) {
    if (line === "") {
      if (this.data.length) frames.push({ id: this.id, data: this.data.join("\n") });
      this.data = [];
      this.id = null;
      return;
    }
    if (line.startsWith(":")) return;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "data") this.data.push(value);
    else if (field === "id") this.id = value;
  }
}

function parseEnvelope(frame) {
  try {
    const envelope = JSON.parse(frame.data);
    return envelope && typeof envelope === "object" && typeof envelope.type === "string"
      ? envelope
      : null;
  } catch {
    return null; // trame illisible : ignorée
  }
}

// Ouvre un flux. `handlers` : { <type>: (data, envelope) => void }. `onStatus({status, failures})`
// reçoit `open`, `retrying`, `lost`, `closed` (fin normale) ou `failed` (abandon).
// Rend { close(), retryNow() }.
export function connectStream({
  url,
  runId = null,
  handlers = {},
  onStatus = () => {},
  failuresBeforeLost = 3,
  maxAttempts = Infinity,
  backoffMs = BACKOFF_MS,
  idleMs = null,
}) {
  let closed = false;
  let failures = 0;
  let controller = null;
  let wake = null;

  const status = (value) => onStatus({ status: value, failures });

  function target() {
    if (runId === null) return url;
    const after = lastSeq(runId);
    return after > 0 ? `${url}?after=${after}` : url;
  }

  function finish(value) {
    controller?.abort(); // libère la connexion : un flux terminé n'a plus rien à dire
    closed = true;
    if (runId !== null) forgetRun(runId);
    status(value);
  }

  function dispatch(envelope) {
    if (runId !== null) {
      if (typeof envelope.seq !== "number" || envelope.seq <= lastSeq(runId)) return;
      markSeq(runId, envelope.seq);
    }
    try {
      // Propriété propre seulement : un type `constructor` ou `toString` reste un type inconnu.
      if (Object.prototype.hasOwnProperty.call(handlers, envelope.type)) {
        handlers[envelope.type](envelope.data, envelope);
      }
    } catch (error) {
      console.error(`Flux : le traitement de « ${envelope.type} » a échoué`, error);
    }
    if (envelope.type === "run_ended") finish("closed");
  }

  async function readOnce() {
    const current = new AbortController();
    controller = current;
    // Chien de garde (flux système) : ni réponse ni octet pendant `idleMs`, la lecture est
    // abandonnée, ce qui compte comme un échec (serveur figé, connexion morte sans fermeture).
    let idle = null;
    const arm = () => {
      if (idleMs === null) return;
      clearTimeout(idle);
      idle = setTimeout(() => current.abort(), idleMs);
    };
    try {
      arm();
      const response = await fetch(target(), {
        headers: { Accept: "text/event-stream" },
        cache: "no-store",
        signal: current.signal,
      });
      if (runId !== null && response.status === 204) return finish("closed");
      if (!response.ok || !response.body) {
        if (runId !== null && response.status >= 400 && response.status < 500) {
          return finish("failed"); // run inconnu ou requête refusée : inutile de réessayer
        }
        throw new Error(`Flux indisponible (${response.status}).`);
      }
      failures = 0;
      status("open");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      const parser = new SseParser();
      arm();
      while (!closed) {
        const { done, value } = await reader.read();
        if (done) break;
        arm();
        for (const frame of parser.feed(decoder.decode(value, { stream: true }))) {
          const envelope = parseEnvelope(frame);
          if (envelope) dispatch(envelope);
          if (closed) return;
        }
      }
    } finally {
      clearTimeout(idle);
    }
  }

  function sleep(ms) {
    return new Promise((resolve) => {
      const timer = setTimeout(resolve, ms);
      wake = () => {
        clearTimeout(timer);
        resolve();
      };
    });
  }

  async function loop() {
    while (!closed) {
      try {
        await readOnce();
      } catch {
        // Échec de connexion ou flux coupé : on compte et on reprend ci-dessous.
      }
      if (closed) return;
      failures += 1; // un flux qui se termine seul (arrêt du serveur) compte comme un échec
      if (failures >= maxAttempts) return finish("failed");
      status(failures >= failuresBeforeLost ? "lost" : "retrying");
      await sleep(backoffMs[Math.min(failures, backoffMs.length) - 1]);
    }
  }

  loop();
  return {
    // `keepSeq` : l'écran quitte la vue sans quitter le run ; le dernier `seq` reste dans le store,
    // et le prochain `connectRun` du même run reprend par `?after=<seq>` (AD-6).
    close({ keepSeq = false } = {}) {
      if (closed) return;
      closed = true;
      controller?.abort();
      wake?.();
      if (runId !== null && !keepSeq) forgetRun(runId);
    },
    // « Réessayer » : ne pas attendre la fin du délai.
    retryNow() {
      wake?.();
    },
  };
}

export function connectSystem(handlers, onStatus) {
  return connectStream({ url: SYSTEM_URL, handlers, onStatus, idleMs: SYSTEM_IDLE_MS });
}

export function connectRun(runId, handlers, onStatus, options = {}) {
  return connectStream({
    url: `/api/runs/${encodeURIComponent(runId)}/events`,
    runId,
    handlers,
    onStatus,
    maxAttempts: 6,
    ...options,
  });
}

