// Module « Accueil » : ses écrans et leur état (voir `core/registry.js`).

export const homeModule = {
  id: "home",
  icon: "home",
  screens: [
    {
      id: "home",
      path: "/",
      status: "available",
      load: () => import("../../screens/home.js"),
    },
  ],
};
