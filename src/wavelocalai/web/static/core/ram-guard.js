// Garde-fou mémoire côté écran (story 4.8) : ce que partagent le Chat, l'Arène et, avec la 4.5,
// l'écran Discussion. `wl-error` rend l'erreur `ram_guard` et ses deux boutons ; l'écran n'a que
// trois choses à faire, qui sont ici :
// 1. reconnaître l'erreur (`isRamGuard`) pour garder la question (dans le champ et l'historique) ;
// 2. écouter « Prendre un modèle plus petit » (`onSmallerModel`) et choisir `detail.suggested_model`
//    dans son `wl-model-picker`, sans relancer : la personne renvoie sa question ;
// 3. ne rien calculer : besoin, mémoire libre et modèle proposé viennent du serveur (AD-20).

export const isRamGuard = (error) => error?.code === "ram_guard";

// `handler(tag, source)` : le tag du modèle proposé, et l'élément qui a émis (pour retrouver la
// colonne d'une Arène). L'événement `wl-use-model` est émis par `wl-error` et remonte à l'écran.
export function onSmallerModel(host, handler) {
  host.addEventListener("wl-use-model", (event) => {
    const tag = event.detail?.model;
    if (tag) handler(tag, event.target);
  });
}

// Sélecteur multiple : `model` remplace `failed` (sans doublon : s'il y est déjà, `failed` s'efface).
// Rend les noms à annoncer.
export function swapModel(picker, failed, model) {
  const chosen = picker.values;
  const index = chosen.indexOf(failed);
  if (index >= 0) chosen[index] = model;
  else chosen.push(model);
  picker.values = chosen;
  const name = (tag) => picker.modelFor(tag)?.name ?? tag;
  return { model: name(model), old: name(failed ?? "") };
}
