// Démarrage de la coquille : textes, barre haute, routeur. La coquille s'affiche seule, Ollama
// arrêté ou non (AD-15) : rien n'attend l'API avant le repère `shell-ready`. Le flux système
// (état d'Ollama, CO2 de session, connexion) se branche juste après ; les écrans appellent l'API
// eux-mêmes.

import { applyTexts, loadTexts } from "./core/i18n.js";
import { createRouter } from "./core/router.js";
import { initShell } from "./core/shell.js";
import { startSystem } from "./core/system.js";
import { initTopbar } from "./core/topbar.js";
import "./core/theme.js";

async function boot() {
  try {
    await loadTexts();
  } catch (error) {
    console.error(error);
  }
  applyTexts();
  try {
    await import("./components/index.js"); // après les textes : les composants les lisent à l'affichage
  } catch (error) {
    console.error(error); // un composant en échec ne doit pas empêcher la coquille de s'afficher
  }
  const setCurrent = initShell();
  let system = null;
  initTopbar(() => system);
  const router = createRouter({
    main: document.getElementById("main"),
    announcer: document.getElementById("announcer"),
    onRoute: setCurrent,
  });
  await router.start();
  // Repère de mesure (budget de 300 ms, AD-15) : la coquille et l'écran courant sont rendus.
  performance.mark("shell-ready");
  system = startSystem();
}

boot();
