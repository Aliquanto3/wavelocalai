// Panneau « Scénarios » (outil de la maquette, hors charte mais accessible) : états globaux, scénarios
// exportés par l'écran courant (`export const scenarios = [{id, label, run(ctx)}]`) et parcours de
// bout en bout (donnees/parcours.json). Replié par défaut ; Échap le referme et rend le focus au bouton.
// Rend aussi l'API de pilotage exposée sur `window.__maquette` (tests et panneau).

import { element } from "../core/dom.js";
import { setMaquette, store } from "../core/store.js";
import { GLOBALS, resetGlobals } from "./global.js";
import { loadParcours, runParcours } from "./parcours.js";

const OPEN_KEY = "wl.maquette.panel";

function readOpen() {
  try {
    return localStorage.getItem(OPEN_KEY) === "1";
  } catch {
    return false;
  }
}

function writeOpen(open) {
  try {
    localStorage.setItem(OPEN_KEY, open ? "1" : "0");
  } catch {
    // Sans stockage, le panneau se replie au rechargement.
  }
}

export async function initPanel({ router, announce }) {
  const root = document.getElementById("maquette-panel");
  const toggle = element("button", "mq-toggle", "Scénarios (maquette)");
  toggle.type = "button";
  toggle.setAttribute("aria-expanded", "false");
  toggle.setAttribute("aria-controls", "mq-panel");
  const panel = element("div", "mq-panel");
  panel.id = "mq-panel";
  panel.hidden = true;
  root.append(toggle, panel);

  const title = element("h2", "mq-title", "Scénarios de la maquette");
  const intro = element("p", "mq-intro", "Outil de la maquette, absent du produit : il force un état ou rejoue un flux.");
  const globals = element("section", "mq-section");
  globals.append(element("h3", "", "États globaux"));
  const screen = element("section", "mq-section");
  const screenTitle = element("h3", "", "Écran courant");
  const screenList = element("ul", "mq-list");
  screen.append(screenTitle, screenList);
  const journeys = element("section", "mq-section");
  const journeyList = element("ul", "mq-list");
  journeys.append(element("h3", "", "Parcours de bout en bout"), journeyList);
  const status = element("p", "mq-status");
  status.setAttribute("role", "status");
  panel.append(title, intro, globals, screen, journeys, status);

  const say = (text) => {
    status.textContent = text;
  };

  // --- Ouverture -------------------------------------------------------------------------------
  const setOpen = (open) => {
    panel.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    writeOpen(open);
  };
  toggle.addEventListener("click", () => setOpen(panel.hidden));
  root.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) {
      event.preventDefault(); // n'arrête pas un run (wl-run-status lit `defaultPrevented`)
      setOpen(false);
      toggle.focus();
    }
  });
  setOpen(readOpen());

  // --- États globaux ---------------------------------------------------------------------------
  const refreshers = [];
  for (const spec of GLOBALS) {
    const row = element("div", "mq-row");
    const id = `mq-global-${spec.id}`;
    if (spec.type === "toggle") {
      const label = element("label");
      const input = element("input");
      input.type = "checkbox";
      input.id = id;
      input.addEventListener("change", () => spec.set(input.checked));
      label.append(input, element("span", "", spec.label));
      row.append(label);
      refreshers.push(() => {
        input.checked = Boolean(spec.get());
      });
    } else if (spec.type === "choice") {
      const label = element("label", "", spec.label);
      label.htmlFor = id;
      const select = element("select");
      select.id = id;
      for (const option of spec.options) {
        const node = element("option", "", option.label);
        node.value = option.value;
        select.append(node);
      }
      select.addEventListener("change", () => spec.set(select.value));
      row.append(label, select);
      refreshers.push(() => {
        select.value = spec.get();
      });
    } else {
      const button = element("button", "", spec.label);
      button.type = "button";
      button.id = id;
      button.addEventListener("click", () => {
        spec.run();
        say(`État appliqué : ${spec.label}.`);
      });
      row.append(button);
    }
    globals.append(row);
  }
  const reset = element("button", "", "Réinitialiser la maquette");
  reset.type = "button";
  reset.addEventListener("click", () => api.reset());
  globals.append(reset);
  const refresh = () => refreshers.forEach((fn) => fn());
  store.subscribe(refresh);
  document.addEventListener("wl-theme-change", refresh);
  document.addEventListener("wl-projection-change", refresh);
  refresh();

  // --- Scénarios de l'écran courant ------------------------------------------------------------
  function currentScenarios() {
    const current = router.current();
    if (!current) return [];
    const module = router.module(current.route.screen);
    const list = Array.isArray(module?.scenarios) ? module.scenarios : [];
    // Un scénario peut se limiter à certaines routes de l'écran (`routes: ["arene-resultat"]`).
    return list.filter((scenario) => !scenario.routes || scenario.routes.includes(current.route.slug));
  }

  async function runScenario(id) {
    const current = router.current();
    const scenario = currentScenarios().find((candidate) => candidate.id === id);
    if (!scenario) throw new Error(`Scénario inconnu pour ${current?.route.slug} : ${id}`);
    say(`Scénario en cours : ${scenario.label}…`);
    await scenario.run(current.entry.ctx);
    say(`Scénario joué : ${scenario.label}.`);
    announce(`Scénario joué : ${scenario.label}.`);
  }

  function renderScreen(current) {
    screenTitle.textContent = `Écran courant : ${current.route.title}`;
    const list = currentScenarios();
    if (!list.length) {
      screenList.replaceChildren(element("li", "mq-empty", "Aucun scénario déclaré pour cet écran."));
      return;
    }
    screenList.replaceChildren(
      ...list.map((scenario) => {
        const item = element("li");
        const button = element("button", "", scenario.label);
        button.type = "button";
        button.dataset.scenario = scenario.id;
        button.addEventListener("click", () => runScenario(scenario.id).catch((error) => say(String(error))));
        item.append(button);
        return item;
      }),
    );
  }

  // --- Parcours --------------------------------------------------------------------------------
  const parcours = await loadParcours();
  let stopJourney = null;
  journeyList.replaceChildren(
    ...parcours.map((journey) => {
      const item = element("li");
      const button = element("button", "", journey.label);
      button.type = "button";
      button.dataset.parcours = journey.id;
      button.addEventListener("click", () => api.runParcours(journey.id));
      item.append(button);
      return item;
    }),
  );
  const stopButton = element("button", "", "Arrêter le parcours");
  stopButton.type = "button";
  stopButton.hidden = true;
  stopButton.addEventListener("click", () => stopJourney?.());
  journeys.append(stopButton);

  const api = {
    ready: false,
    routes: () => router.routes.map(({ slug, path, title, screen, example, module }) => ({ slug, path, title, screen, example, module })),
    current: () => {
      const current = router.current();
      return current ? { slug: current.route.slug, screen: current.route.screen, params: current.params } : null;
    },
    navigate: (path) => router.navigate(path),
    scenarios: () => currentScenarios().map(({ id, label }) => ({ id, label })),
    runScenario,
    globals: () => GLOBALS.map(({ id, label, type, options }) => ({ id, label, type, options })),
    async setGlobal(id, value) {
      const spec = GLOBALS.find((candidate) => candidate.id === id);
      if (!spec) throw new Error(`État global inconnu : ${id}`);
      if (spec.type === "action") spec.run();
      else spec.set(value);
      refresh();
    },
    setSpeed: (speed) => setMaquette({ speed }),
    parcours: () => parcours.map(({ id, label }) => ({ id, label })),
    async runParcours(id) {
      const journey = parcours.find((candidate) => candidate.id === id);
      if (!journey) throw new Error(`Parcours inconnu : ${id}`);
      stopButton.hidden = false;
      const result = runParcours(journey, { router, runScenario, currentScenarios, say });
      stopJourney = result.stop;
      try {
        return await result.done;
      } finally {
        stopButton.hidden = true;
        stopJourney = null;
      }
    },
    async reset() {
      resetGlobals();
      const current = router.current();
      if (current) await router.remount(current.route.screen);
      say("Maquette réinitialisée.");
    },
    openPanel: () => setOpen(true),
  };

  return {
    api,
    onRoute: (current) => renderScreen(current),
  };
}
