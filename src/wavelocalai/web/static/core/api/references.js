// Appel « références » (story 5.8) : quel modèle pour quel usage, lu des résultats publiés du banc.

export function referencesApi(request) {
  return {
    // Cartes par usage, groupe des meilleurs, débit, marques et cibles de « Comparer » : tout est
    // décidé par le serveur (AD-20). `available: false` porte sa raison ; jamais une erreur pour un
    // fichier absent ou d'un autre format.
    references: () => request("/api/references"),
  };
}
