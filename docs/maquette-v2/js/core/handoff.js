// Passage de relais entre deux écrans gardés en mémoire (un écran ne s'importe pas l'autre) :
// `handOff(clé, valeur)` dépose, `takeHandOff(clé)` reprend une fois. Exemple : « Comparer ces
// modèles » (Références) présélectionne les modèles de l'Arène (décision 19).

const parcels = new Map();

export function handOff(key, value) {
  parcels.set(key, value);
}

export function takeHandOff(key) {
  const value = parcels.get(key);
  parcels.delete(key);
  return value;
}
