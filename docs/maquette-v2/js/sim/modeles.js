// Réponses simulées de `GET /api/models?allow_cloud=` et `GET /api/models/defaults?purpose=`, depuis
// donnees/commun/modeles.json, selon l'état du store : Ollama arrêté (modèles locaux indisponibles),
// aucun modèle local installé (`no_model`), cloud autorisé ou non. Même forme que l'API.

import { loadCopy } from "../core/data.js";
import { errorEnvelope } from "../core/errors.js";
import { store } from "../core/store.js";

export class SimApiError extends Error {
  constructor(status, envelope) {
    super(envelope.message);
    this.status = status;
    this.envelope = envelope;
  }
}

function localVisible(model, maquette) {
  return !(maquette.noLocalModel && model.origin === "local");
}

export async function listModels(allowCloud = store.get().allowCloud) {
  const data = await loadCopy("commun/modeles.json");
  const { maquette } = store.get();
  const models = data.models
    .filter((model) => localVisible(model, maquette))
    .filter((model) => allowCloud || model.origin !== "cloud")
    .map((model) =>
      model.origin === "local" && maquette.ollamaDown ? { ...model, available: false } : model,
    );
  return { ollama_up: !maquette.ollamaDown, models };
}

export async function modelDefaults(purpose = "chat", allowCloud = store.get().allowCloud) {
  const data = await loadCopy("commun/modeles.json");
  const { maquette } = store.get();
  if (maquette.noLocalModel && !allowCloud) {
    throw new SimApiError(404, errorEnvelope("no_model", { detail: { purpose } }));
  }
  if (maquette.noLocalModel) {
    const cloud = data.models.find((model) => model.origin === "cloud" && model.kind === "chat" && model.available);
    return { tags: cloud ? [cloud.tag] : [], reason: "Aucun modèle local : modèle cloud proposé, le cloud étant autorisé." };
  }
  return data.defaults[purpose] ?? data.defaults.chat;
}

export async function findModel(tag) {
  const data = await loadCopy("commun/modeles.json");
  return data.models.find((model) => model.tag === tag) ?? null;
}
