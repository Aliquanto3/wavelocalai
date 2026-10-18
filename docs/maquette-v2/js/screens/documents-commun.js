// Commun aux trois écrans du module Documents (Discussion, Base documentaire, Évaluation de la
// qualité) : la base documentaire simulée (ce que le serveur garderait), de petits utilitaires de
// scénario. Le panneau de sources et l'aide en bouton sont des composants communs
// (js/components/source-panel.js, js/components/help-toggle.js), réexportés ici. Ce n'est pas un écran : aucune route ne le charge.
//
// La base vit dans le store sous `ragBase` : `{documents, settings, reranker}`. Les trois écrans la
// lisent et s'y abonnent, si bien qu'un import fait dans « Base documentaire » se voit tout de suite
// dans « Discussion » (compteur, documents interrogeables). Chaque scénario pose la base qu'il
// attend (`setBasePreset`) : `ctx.reset()` ne la remet pas à zéro.

import { loadCopy } from "../core/data.js";
import { formatDate, formatInteger, formatTime } from "../core/format.js";
import { loadScreenTexts, plural } from "../core/i18n.js";
import { store } from "../core/store.js";

export { helpToggle } from "../components/help-toggle.js";
export { createSourcePanel, passageText } from "../components/source-panel.js";

// --- Préparation (feuille de style et textes communs, chargés une seule fois) ---------------------

let prepared = null;

export function prepare() {
  prepared ??= Promise.all([
    loadScreenTexts("documents-commun"),
    new Promise((resolve) => {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = new URL("../../css/screens/documents-commun.css", import.meta.url).href;
      link.onload = link.onerror = () => resolve();
      document.head.append(link);
    }),
  ]);
  return prepared;
}

// --- Utilitaires de scénario ----------------------------------------------------------------------

export const speedOf = () => store.get().maquette.speed || 1;

export function waitUntil(condition, timeoutMs = 20000) {
  return new Promise((resolve, reject) => {
    const started = performance.now();
    const check = () => {
      if (condition()) return resolve();
      if (performance.now() - started > timeoutMs) return reject(new Error("Scénario : état jamais atteint"));
      setTimeout(check, 30);
    };
    check();
  });
}

export const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms / speedOf()));

// --- Base documentaire simulée --------------------------------------------------------------------

export function getBase() {
  return store.get().ragBase ?? null;
}

export async function setBasePreset(name = "complet") {
  const data = await loadCopy("base-documentaire.json");
  const ids = data.presets[name] ?? data.presets.complet;
  const documents = ids.map((id) => {
    const doc = data.documents.find((candidate) => candidate.id === id);
    return { status: "ready", embedding: data.settings.embedding, ...doc };
  });
  store.set({ ragBase: { documents, settings: data.settings, reranker: data.reranker, embeddingModels: data.embedding_models } });
}

// Au premier montage d'un écran du module : la base complète, si aucun scénario n'en a posé une.
export async function ensureBase() {
  if (!getBase()) await setBasePreset("complet");
  return getBase();
}

// Modifie une copie de la base puis la publie (les trois écrans s'y abonnent).
export function updateBase(mutate) {
  const next = structuredClone(getBase());
  mutate(next);
  store.set({ ragBase: next });
}

export function subscribeBase(listener) {
  return store.select((state) => state.ragBase, (base) => base && listener(base));
}

// Seuls les documents `ready` s'interrogent et se comptent ; un document `indexing` n'est pas prêt.
export function baseCounts(base = getBase()) {
  const ready = base.documents.filter((doc) => doc.status === "ready");
  return {
    documents: ready.length,
    chunks: ready.reduce((sum, doc) => sum + doc.chunks, 0),
    indexing: base.documents.filter((doc) => doc.status === "indexing").length,
  };
}

export const documentsLabel = (count) => plural("docs.documents", count, { count: formatInteger(count) });
export const chunksLabel = (count) => plural("docs.chunks", count, { count: formatInteger(count) });

export function formatDateTime(iso) {
  return `${formatDate(iso)} ${formatTime(iso)}`;
}

export function embeddingName(base, tag) {
  return base.embeddingModels.find((model) => model.tag === tag)?.name ?? tag;
}
