// Appels JSON à l'API locale. Toute réponse en erreur suit `{code, message, action, detail}`
// (AD-18) : `ApiError.envelope` la garde telle quelle, l'écran affiche `message` puis `action`.
// Les requêtes ne visent que la même origine (127.0.0.1).

export class ApiError extends Error {
  constructor(message, { status = 0, envelope = null, cause } = {}) {
    super(message, { cause });
    this.name = "ApiError";
    this.status = status;
    this.envelope = envelope;
  }
}

function asEnvelope(data) {
  return data && typeof data.code === "string" && typeof data.message === "string" ? data : null;
}

export async function request(path, { method = "GET", body, timeoutMs = 5000, signal } = {}) {
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: signal ?? AbortSignal.timeout(timeoutMs),
      cache: "no-store",
    });
  } catch (cause) {
    throw new ApiError("Le serveur ne répond pas.", { cause });
  }
  if (!response.ok) {
    let envelope = null;
    try {
      envelope = asEnvelope(await response.json());
    } catch {
      // Corps absent ou illisible : le statut suffit.
    }
    throw new ApiError(envelope?.message ?? `Erreur ${response.status}.`, {
      status: response.status,
      envelope,
    });
  }
  return response.status === 204 ? null : response.json();
}

// Envoie des fichiers à `POST /api/rag/documents` (multipart). `fetch` ne rend pas la progression de
// l'envoi : `XMLHttpRequest` la donne (`onProgress(octets envoyés, octets au total)`). Rend
// `{run_id}`. Annuler par `signal` rejette avec une `DOMException` `AbortError`. `onSent()` dit que
// le corps est parti : le serveur peut dès lors créer le run, abandonner la requête ne l'arrête plus.
export function uploadDocuments(files, { signal, onProgress = () => {}, onSent = () => {} } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    for (const file of files) form.append("files", file, file.name);
    const abort = () => xhr.abort();
    const finish = () => signal?.removeEventListener("abort", abort);
    xhr.open("POST", "/api/rag/documents");
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded, event.total);
    };
    xhr.upload.onload = () => onSent();
    xhr.onload = () => {
      finish();
      let body = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        // Corps absent ou illisible : le statut suffit.
      }
      if (xhr.status >= 200 && xhr.status < 300 && body) return resolve(body);
      const envelope = asEnvelope(body);
      reject(
        new ApiError(envelope?.message ?? `Erreur ${xhr.status}.`, { status: xhr.status, envelope }),
      );
    };
    xhr.onerror = () => {
      finish();
      reject(new ApiError("Le serveur ne répond pas."));
    };
    xhr.onabort = () => {
      finish();
      reject(new DOMException("Envoi annulé.", "AbortError"));
    };
    if (signal?.aborted) return xhr.abort();
    signal?.addEventListener("abort", abort, { once: true });
    xhr.send(form);
  });
}

export const api = {
  health: () => request("/api/health"),
  carbonSession: () => request("/api/carbon/session"),
  systemIdentity: () => request("/api/system/identity"),
  // Liste unique des modèles (AD-15) : sans `allowCloud`, aucun modèle cloud (AD-9).
  models: (allowCloud) => request(`/api/models?allow_cloud=${allowCloud ? "true" : "false"}`),
  modelDefaults: (purpose, allowCloud) =>
    request(
      `/api/models/defaults?purpose=${encodeURIComponent(purpose)}&allow_cloud=${allowCloud ? "true" : "false"}`,
    ),
  // Lance une réponse de chat ; `allow_cloud` vient du store, sur chaque commande (AD-9).
  startChat: (body) => request("/api/chat/runs", { method: "POST", body }),
  // Documents de la base (tous statuts), totaux des prêts et plafonds d'un import.
  documents: () => request("/api/rag/documents"),
  // Lance une comparaison de 2 à 4 modèles ; `allow_cloud` vient du store, sur chaque commande (AD-9).
  startArena: (body) => request("/api/arena/runs", { method: "POST", body }),
  // Conversations (AD-5, AD-13) : les plus récentes d'un genre, une conversation, son effacement,
  // et l'adresse de ses exports (`json`, `md`), téléchargés par un lien et non par `fetch`.
  conversations: (kind, limit = 1) =>
    request(`/api/conversations?kind=${encodeURIComponent(kind)}&limit=${limit}`),
  conversation: (id) => request(`/api/conversations/${encodeURIComponent(id)}`),
  deleteConversation: (id) =>
    request(`/api/conversations/${encodeURIComponent(id)}`, { method: "DELETE" }),
  conversationExportUrl: (id, extension) =>
    `/api/conversations/${encodeURIComponent(id)}.${extension}`,
  // Instantané d'un run (AD-5) : statut, mesures des feuilles et, pour une Arène, son `verdict`.
  run: (runId) => request(`/api/runs/${encodeURIComponent(runId)}`),
  cancelRun: (runId) =>
    request(`/api/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" }),
};
