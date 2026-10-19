// Rejeu du flux d'un run `rag` fini (écran Discussion, story 4.5, extrait en 4.6) : les sources, les
// mesures et les citations d'une réponse déjà donnée, que `GET /api/conversations/{id}` ne porte pas.

import { connectRun } from "../core/sse.js";

const REPLAY_TIMEOUT_MS = 10_000;
// Flux rejoués à la fois : sous la limite de connexions HTTP/1.1 du navigateur (6 par hôte), le
// délai de chaque rejeu ne compte qu'à partir de sa propre connexion.
const REPLAY_CONCURRENCY = 3;

// Le flux d'un run fini, rejoué : ses sources, ses mesures et ses citations (jamais d'erreur : sans
// flux lisible, la réponse s'affiche sans sources).
function replay(runId) {
  return new Promise((resolve) => {
    const found = { sources: [], metrics: null, citations: [] };
    let stream = null;
    const timer = setTimeout(() => {
      stream?.close();
      resolve(found);
    }, REPLAY_TIMEOUT_MS);
    const done = () => {
      clearTimeout(timer);
      resolve(found);
    };
    stream = connectRun(
      runId,
      {
        sources: (data) => {
          found.sources = Array.isArray(data?.sources) ? data.sources : [];
        },
        metrics: (data) => {
          found.metrics = data ?? null;
        },
        citations: (data) => {
          found.citations = Array.isArray(data?.citations) ? data.citations : [];
        },
      },
      ({ status }) => {
        if (status === "closed" || status === "failed") done();
      },
      { maxAttempts: 2 },
    );
  });
}

// Les runs rejoués, au plus `REPLAY_CONCURRENCY` à la fois : Map run_id -> { sources, metrics,
// citations }.
export async function replayAll(ids) {
  const results = new Map();
  const queue = [...ids];
  const worker = async () => {
    while (queue.length) {
      const id = queue.shift();
      results.set(id, await replay(id));
    }
  };
  await Promise.all(Array.from({ length: Math.min(REPLAY_CONCURRENCY, queue.length) }, worker));
  return results;
}
