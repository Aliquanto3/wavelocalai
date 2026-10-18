// Démarrage de la coquille : textes, barre haute, routeur. Aucun appel à `/api/` : la coquille
// s'affiche seule, Ollama arrêté ou non (AD-15). Les écrans appellent l'API eux-mêmes.

import { applyTexts, loadTexts } from "./core/i18n.js";
import { createRouter } from "./core/router.js";
import { initShell } from "./core/shell.js";
import "./core/theme.js";

async function boot() {
  try {
    await loadTexts();
  } catch (error) {
    console.error(error);
  }
  applyTexts();
  const setCurrent = initShell();
  const router = createRouter({
    main: document.getElementById("main"),
    announcer: document.getElementById("announcer"),
    onRoute: setCurrent,
  });
  await router.start();
  // Repère de mesure (budget de 300 ms, AD-15) : la coquille et l'écran courant sont rendus.
  performance.mark("shell-ready");
}

boot();
