// Données simulées de la maquette (`donnees/`) : un `fetch` par fichier, gardé en mémoire. Les chemins
// sont relatifs à `donnees/` (« routes.json », « commun/modeles.json », « flux/chat-libre-reponse.json »).

const ROOT = new URL("../../donnees/", import.meta.url);
const cache = new Map();

export function loadData(path) {
  if (!cache.has(path)) {
    const pending = fetch(new URL(path, ROOT)).then((response) => {
      if (!response.ok) throw new Error(`Données introuvables (${response.status}) : donnees/${path}`);
      return response.json();
    });
    pending.catch(() => cache.delete(path)); // un échec n'est pas gardé
    cache.set(path, pending);
  }
  return cache.get(path);
}

// Copie profonde, pour qu'un écran ne modifie jamais les données partagées en cache.
export async function loadCopy(path) {
  return structuredClone(await loadData(path));
}
