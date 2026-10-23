// Module « Modèles » : ses écrans et leur état (voir `core/registry.js`).
// `#/modeles/<tag>` (fiche d'un modèle, story 5.6) : le tag, encodé en un seul segment (`/` en `%2F`),
// ouvre le panneau de la fiche ; `update` de l'écran suit l'adresse sans le remonter.

export const modelsModule = {
  id: "models",
  icon: "deployed-code",
  screens: [
    {
      id: "models",
      path: "/modeles",
      param: "tag",
      status: "available",
      load: () => import("../../screens/models.js"),
    },
  ],
};
