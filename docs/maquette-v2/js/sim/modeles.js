// Réponses simulées de `GET /api/models?allow_cloud=` et `GET /api/models/defaults?purpose=`, depuis
// donnees/commun/modeles.json, selon l'état du store : Ollama arrêté (modèles locaux indisponibles),
// aucun modèle local installé (`no_model`), cloud autorisé ou non. Même forme que l'API.
//
// Ce que l'écran Modèles change sur le poste (installation, suppression, déchargement) est gardé dans
// le store (`maquette.localModels`) : la liste, les défauts, le sélecteur, l'Accueil et le flux
// système simulé le voient. API : installModel(model), deleteModel(tag), unloadModels(tags),
// localModelsState() ; remis à zéro avec la maquette.

import { loadCopy } from "../core/data.js";
import { errorEnvelope } from "../core/errors.js";
import { setMaquette, store } from "../core/store.js";

const overlay = () => store.get().maquette.localModels;

// Créativité par défaut que le serveur rendrait avec chaque modèle (décision 12, champ
// `default_temperature` de `GET /api/models`, simulé ici) ; repli à 0,2 si le serveur n'en dit rien.
export const FALLBACK_TEMPERATURE = 0.2;
const SERVER_TEMPERATURE = { "qwen3.5:2b": 0.6, "gemma4:1b": 0.8, "qwen3.6:7b": 0.5 };

export function defaultTemperature(model) {
  return model?.default_temperature ?? FALLBACK_TEMPERATURE;
}

function withTemperature(model) {
  const value = SERVER_TEMPERATURE[model.tag];
  return value === undefined || model.default_temperature !== undefined ? model : { ...model, default_temperature: value };
}

export function localModelsState() {
  const { added, deleted, unloaded } = overlay();
  return { added: [...added], deleted: new Set(deleted), unloaded: new Set(unloaded) };
}

// Modèle installé (fin d'un `pull`) : il redevient visible s'il avait été supprimé.
export function installModel(model) {
  const { added, deleted, unloaded } = overlay();
  setMaquette({
    localModels: {
      added: [...added.filter((entry) => entry.tag !== model.tag), model],
      deleted: deleted.filter((tag) => tag !== model.tag),
      unloaded,
    },
  });
}

export function deleteModel(tag) {
  const { added, deleted, unloaded } = overlay();
  setMaquette({
    localModels: {
      added: added.filter((entry) => entry.tag !== tag),
      deleted: deleted.includes(tag) ? deleted : [...deleted, tag],
      unloaded,
    },
  });
}

// Modèles déchargés de la mémoire (ils restent installés).
export function unloadModels(tags) {
  const { added, deleted, unloaded } = overlay();
  setMaquette({ localModels: { added, deleted, unloaded: [...new Set([...unloaded, ...tags])] } });
}

function withOverlay(models) {
  const { added, deleted } = overlay();
  const known = new Set(models.map((model) => model.tag));
  return [...models.filter((model) => !deleted.includes(model.tag)), ...added.filter((model) => !known.has(model.tag))].map(withTemperature);
}

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
  const models = withOverlay(data.models)
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
  const found = data.defaults[purpose] ?? data.defaults.chat;
  // Un défaut supprimé du poste n'est plus proposé.
  const { deleted } = overlay();
  return deleted.length ? { ...found, tags: found.tags.filter((tag) => !deleted.includes(tag)) } : found;
}

export async function findModel(tag) {
  const data = await loadCopy("commun/modeles.json");
  const found = data.models.find((model) => model.tag === tag) ?? overlay().added.find((model) => model.tag === tag) ?? null;
  return found && withTemperature(found);
}
