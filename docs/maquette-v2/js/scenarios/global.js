// États globaux du panneau Scénarios : chacun agit sur le store ou le simulateur, comme le ferait
// le vrai serveur (Ollama arrêté, connexion perdue…) ou la personne (thème, projection, cloud).
// `type` : "toggle" (case), "action" (bouton) ou "choice" (liste). `get()` rend la valeur affichée.

import { INITIAL_MAQUETTE, setMaquette, store } from "../core/store.js";
import { getProjection, getTheme, setProjection, setTheme } from "../core/theme.js";
import { sim } from "../sim/sim.js";
import { loseConnection, restoreConnection, setOllamaDown } from "../sim/systeme.js";

const maquette = () => store.get().maquette;

export const GLOBALS = [
  {
    id: "ollama-arrete",
    label: "Ollama arrêté",
    type: "toggle",
    get: () => maquette().ollamaDown,
    set: (on) => setOllamaDown(on),
  },
  {
    id: "cloud",
    label: "Cloud autorisé",
    type: "toggle",
    get: () => store.get().allowCloud,
    set: (on) => store.set({ allowCloud: on }),
  },
  {
    id: "connexion-perdue",
    label: "Connexion au serveur perdue",
    type: "toggle",
    get: () => store.get().connection.status !== "open",
    set: (on) => (on ? loseConnection() : restoreConnection()),
  },
  {
    id: "serveur-redemarre",
    label: "Le serveur redémarre",
    type: "action",
    run: () => sim.restartServer(),
  },
  {
    id: "garde-fou-memoire",
    label: "Garde-fou mémoire (prochain run local bloqué)",
    type: "toggle",
    get: () => maquette().ramGuard,
    set: (on) => setMaquette({ ramGuard: on }),
  },
  {
    id: "chargement-lent",
    label: "Premier chargement lent (14 s)",
    type: "toggle",
    get: () => maquette().slowLoad,
    set: (on) => setMaquette({ slowLoad: on }),
  },
  {
    id: "aucun-modele-local",
    label: "Aucun modèle local installé",
    type: "toggle",
    get: () => maquette().noLocalModel,
    set: (on) => setMaquette({ noLocalModel: on }),
  },
  {
    id: "onglet-masque",
    label: "Onglet du navigateur masqué (mises à jour en pause)",
    type: "toggle",
    get: () => maquette().livePaused,
    set: (on) => setMaquette({ livePaused: on }),
  },
  {
    id: "theme",
    label: "Thème",
    type: "choice",
    options: [
      { value: "light", label: "Clair" },
      { value: "dark", label: "Sombre" },
      { value: "system", label: "Système" },
    ],
    get: () => getTheme(),
    set: (value) => setTheme(value),
  },
  {
    id: "projection",
    label: "Mode projection",
    type: "toggle",
    get: () => getProjection(),
    set: (on) => setProjection(on),
  },
  {
    id: "vitesse",
    label: "Vitesse du simulateur",
    type: "choice",
    options: [
      { value: "1", label: "Réelle" },
      { value: "3", label: "× 3" },
      { value: "10", label: "× 10" },
      { value: "50", label: "Instantanée" },
    ],
    get: () => String(maquette().speed),
    set: (value) => setMaquette({ speed: Number(value) || 1 }),
  },
];

// Remet la maquette à son état d'ouverture (sauf thème, projection et vitesse).
export function resetGlobals() {
  sim.reset();
  const { speed } = maquette();
  setMaquette({ ...INITIAL_MAQUETTE, speed });
  store.set({ allowCloud: false, serverRestarted: false });
  setOllamaDown(false);
  restoreConnection();
}
