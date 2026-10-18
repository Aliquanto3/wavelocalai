// Démarrage de la maquette : textes, catalogue d'erreurs, routes, coquille, barre haute, panneau
// Scénarios, routeur, puis flux système simulé. La coquille s'affiche sans attendre le « serveur »
// (AD-15) : le premier état du système arrive après un court délai (squelettes visibles).
// `window.__maquette` expose de quoi piloter la maquette (tests, panneau) : voir CONVENTIONS.md.

import { loadData } from "./core/data.js";
import { loadErrors } from "./core/errors.js";
import { applyTexts, loadTexts, plural, t } from "./core/i18n.js";
import { createRouter } from "./core/router.js";
import { store } from "./core/store.js";
import { initPanel } from "./scenarios/panel.js";
import { initShell, screenTabs } from "./shell/shell.js";
import { initTopbar } from "./shell/topbar.js";
import { sim } from "./sim/sim.js";
import * as system from "./sim/systeme.js";

function makeAnnouncer(region) {
  return (text) => {
    region.textContent = "";
    requestAnimationFrame(() => {
      region.textContent = text;
    });
  };
}

async function boot() {
  // En file:// : message d'index.html, sauf dans la page autonome (construire_autonome.py).
  if (location.protocol === "file:" && !window.__wlAutonome) return;
  await Promise.all([loadTexts(), loadErrors()]);
  const { modules, routes } = await loadData("routes.json");
  applyTexts();
  const components = await import("./components/index.js");
  const states = components.states;

  const setCurrent = initShell({ modules, routes });
  initTopbar();
  const announce = makeAnnouncer(document.getElementById("status-announcer"));

  let router = null;
  const makeContext = (route, params, host, { remount }) => ({
    route,
    params,
    host,
    store,
    sim,
    states,
    system,
    t,
    plural,
    data: loadData,
    announce,
    remount,
    navigate: (path) => router.navigate(path),
    reset: () => window.__maquette.reset(),
    routes: router.routes,
    // Onglets du module courant (Arène, Documents, Agents).
    tabs: () => {
      const module = modules.find((candidate) => candidate.id === route.module);
      return screenTabs(router.routes, route.module, route.slug, t("tabs.label", { module: module?.label ?? "" }));
    },
  });

  router = createRouter({
    main: document.getElementById("main"),
    announcer: document.getElementById("announcer"),
    routes,
    makeContext,
    onRoute: (current) => {
      setCurrent(current.route);
      panel.onRoute(current);
    },
  });
  const panel = await initPanel({ router, announce });
  window.__maquette = panel.api;
  await router.start();
  await system.startSystem();
  window.__maquette.ready = true;
  document.documentElement.dataset.ready = "true";
}

boot().catch((error) => {
  console.error("Maquette : échec du démarrage", error);
  const main = document.getElementById("main");
  const message = document.createElement("p");
  message.setAttribute("role", "alert");
  message.textContent = `La maquette n'a pas pu démarrer : ${error.message}`;
  main.replaceChildren(message);
});
