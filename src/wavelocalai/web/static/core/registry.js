// Registre des écrans (UX-DR4, décision de structure du 2026-10-18) : chaque écran est
// `available` (il a un module `load`) ou `planned` (visible, désactivé, avec sa raison). Une story
// qui livre un écran passe son `status` à "available" et lui donne son `load`.
// `param` : nom du paramètre de chemin (`#/arene/comparer/<run_id>`, `#/modeles/<tag>`). Les routes
// de la maquette (D-8) y sont déclarées `planned` : la story qui livre un écran n'a plus qu'à le
// passer à `available` et à lui donner son `load`. Le paramètre est toujours facultatif :
// `findScreen` accepte le chemin nu, que l'écran monte avec `params = {}` (nouvelle comparaison,
// liste des modèles), et c'est ce chemin nu que l'Accueil et le menu lient.

export const MODULES = [
  {
    id: "home",
    icon: "home",
    screens: [
      {
        id: "home",
        path: "/",
        status: "available",
        load: () => import("../screens/home.js"),
      },
    ],
  },
  {
    id: "arena",
    icon: "swords",
    screens: [
      {
        id: "arena-chat",
        path: "/arene/chat",
        status: "available",
        load: () => import("../screens/chat.js"),
      },
      {
        id: "arena-compare",
        path: "/arene/comparer",
        param: "run_id",
        status: "available",
        load: () => import("../screens/arena.js"),
      },
      { id: "arena-bench", path: "/arene/banc", param: "run_id", status: "planned" },
      { id: "arena-references", path: "/arene/references", status: "planned" },
    ],
  },
  {
    id: "documents",
    icon: "description",
    screens: [
      {
        id: "documents-chat",
        path: "/documents",
        status: "available",
        load: () => import("../screens/documents.js"),
      },
      {
        id: "documents-base",
        path: "/documents/base",
        status: "available",
        load: () => import("../screens/documents-base.js"),
      },
      {
        id: "documents-evaluation",
        path: "/documents/evaluation",
        param: "run_id",
        status: "planned",
      },
    ],
  },
  {
    id: "agents",
    icon: "smart-toy",
    screens: [
      { id: "agents-solo", path: "/agents/seul", status: "planned" },
      { id: "agents-crew", path: "/agents/equipe", param: "run_id", status: "planned" },
    ],
  },
  {
    id: "sobriety",
    icon: "eco",
    screens: [{ id: "sobriety", path: "/sobriete", status: "planned" }],
  },
  {
    id: "models",
    icon: "deployed-code",
    screens: [{ id: "models", path: "/modeles", param: "tag", status: "planned" }],
  },
];

export const SCREENS = MODULES.flatMap((module) =>
  module.screens.map((screen) => ({ ...screen, module: module.id })),
);

// Un module est disponible dès qu'un de ses écrans l'est ; son lien mène au premier.
export function entryScreen(module) {
  return module.screens.find((screen) => screen.status === "available") ?? null;
}

// L'écran d'un chemin (`/arene/comparer/abc`) et ses paramètres, ou null si le chemin est inconnu.
export function findScreen(path) {
  for (const screen of SCREENS) {
    if (path === screen.path) return { screen, params: {} };
    if (screen.param && path.startsWith(`${screen.path}/`)) {
      const value = path.slice(screen.path.length + 1);
      if (value && !value.includes("/")) {
        try {
          return { screen, params: { [screen.param]: decodeURIComponent(value) } };
        } catch {
          return null;
        }
      }
    }
  }
  return null;
}
