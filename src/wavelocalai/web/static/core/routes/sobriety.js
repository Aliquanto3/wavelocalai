// Module « Sobriété » : ses écrans et leur état (voir `core/registry.js`).

export const sobrietyModule = {
  id: "sobriety",
  icon: "eco",
  screens: [
    {
      id: "sobriety",
      path: "/sobriete",
      status: "available",
      load: () => import("../../screens/sobriety.js"),
    },
  ],
};
