// Navigation au clavier des onglets par modèle de l'Arène (sous 768 px) : flèches (en boucle), Début
// et Fin. Rend le tag de l'onglet à activer, ou `null` si la touche n'en change pas.

const MOVES = { ArrowRight: 1, ArrowLeft: -1 };

export function nextTab(key, order, tag) {
  if (key in MOVES) return order[(order.indexOf(tag) + MOVES[key] + order.length) % order.length];
  if (key === "Home") return order[0];
  if (key === "End") return order[order.length - 1];
  return null;
}

// Applique la touche : active l'onglet visé (`select(tag)`) sans faire défiler la page.
export function moveTab(event, order, tag, select) {
  const next = nextTab(event.key, order, tag);
  if (next === null) return;
  event.preventDefault();
  select(next);
}
