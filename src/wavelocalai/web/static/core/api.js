// Appels JSON à l'API locale. Toute réponse en erreur suit `{code, message, action, detail}`
// (AD-18) : `ApiError.envelope` la garde telle quelle, l'écran affiche `message` puis `action`.
// Les requêtes ne visent que la même origine (127.0.0.1).
//
// Ce fichier garde le transport (`request`, `ApiError`, `uploadDocuments`) et assemble `api`. Les
// appels sont rangés par domaine dans `core/api/<domaine>.js`, fonction `<domaine>Api(request)` qui
// rend ses appels. Mode d'emploi : une story qui ajoute un domaine crée son fichier et ajoute ici
// son import et une ligne dans `api` ; une story qui ajoute un appel à un domaine existant ne
// touche que le fichier de ce domaine. Les écrans importent toujours `api` d'ici.

import { arenaApi } from "./api/arena.js";
import { conversationsApi } from "./api/conversations.js";
import { modelsApi } from "./api/models.js";
import { ragApi } from "./api/rag.js";
import { referencesApi } from "./api/references.js";
import { runsApi } from "./api/runs.js";
import { systemApi } from "./api/system.js";

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
  ...systemApi(request),
  ...modelsApi(request),
  ...conversationsApi(request),
  ...arenaApi(request),
  ...ragApi(request),
  ...referencesApi(request),
  ...runsApi(request),
};
