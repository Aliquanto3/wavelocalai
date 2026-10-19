// Registre des écrans (UX-DR4, décision de structure du 2026-10-18) : chaque écran est
// `available` (il a un module `load`) ou `planned` (visible, désactivé, avec sa raison). Une story
// qui livre un écran passe son `status` à "available" et lui donne son `load`.
// `param` : nom du paramètre de chemin (`#/arene/comparer/<run_id>`, `#/modeles/<tag>`). Les routes
// de la maquette (D-8) y sont déclarées `planned` : la story qui livre un écran n'a plus qu'à le
// passer à `available` et à lui donner son `load`. Le paramètre est toujours facultatif :
// `findScreen` accepte le chemin nu, que l'écran monte avec `params = {}` (nouvelle comparaison,
// liste des modèles), et c'est ce chemin nu que l'Accueil et le menu lient.
//
// Les modules sont déclarés un par fichier dans `core/routes/<module>.js` (`<module>Module`).
// Mode d'emploi : passer un écran à `available`, ou lui donner son `load`, ne touche que le fichier
// de son module. Une story qui ajoute un module crée son fichier, puis ajoute ici son import et
// une ligne dans `MODULES`, à la place qu'il occupe dans la navigation.

import { agentsModule } from "./routes/agents.js";
import { arenaModule } from "./routes/arena.js";
import { documentsModule } from "./routes/documents.js";
import { homeModule } from "./routes/home.js";
import { modelsModule } from "./routes/models.js";
import { sobrietyModule } from "./routes/sobriety.js";

// Ordre de la navigation.
export const MODULES = [
  homeModule,
  arenaModule,
  documentsModule,
  agentsModule,
  sobrietyModule,
  modelsModule,
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
