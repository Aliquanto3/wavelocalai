// Module « Modèles » : ses écrans et leur état (voir `core/registry.js`).
// `#/modeles/<tag>` (fiche d'un modèle, story 5.6) n'existe pas encore : sans `param`, cette adresse
// renvoie à l'Accueil comme une route inconnue ; la 5.6 lui donne son paramètre de chemin (`tag`).

export const modelsModule = {
  id: "models",
  icon: "deployed-code",
  screens: [
    {
      id: "models",
      path: "/modeles",
      status: "available",
      load: () => import("../../screens/models.js"),
    },
  ],
};
