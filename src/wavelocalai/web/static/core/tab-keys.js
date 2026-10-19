// Clavier d'une rangée d'onglets (WAI-ARIA APG) : flèches gauche et droite (en boucle), Début, Fin.
// Rend le tag de l'onglet à activer, ou `null` si la touche n'en désigne aucun.

const MOVES = { ArrowRight: 1, ArrowLeft: -1 };

export function nextTab(key, order, tag) {
  const at = order.indexOf(tag);
  if (key in MOVES) return order[(at + MOVES[key] + order.length) % order.length];
  if (key === "Home") return order[0];
  if (key === "End") return order[order.length - 1];
  return null;
}
