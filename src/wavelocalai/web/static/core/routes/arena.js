// Module « Arène » : ses écrans et leur état (voir `core/registry.js`).

export const arenaModule = {
  id: "arena",
  icon: "swords",
  screens: [
    {
      id: "arena-chat",
      path: "/arene/chat",
      status: "available",
      load: () => import("../../screens/chat.js"),
    },
    {
      id: "arena-compare",
      path: "/arene/comparer",
      param: "run_id",
      status: "available",
      load: () => import("../../screens/arena.js"),
    },
    {
      id: "arena-bench",
      path: "/arene/banc",
      param: "run_id",
      status: "available",
      load: () => import("../../screens/bench.js"),
    },
    {
      id: "arena-references",
      path: "/arene/references",
      status: "available",
      load: () => import("../../screens/references.js"),
    },
  ],
};
