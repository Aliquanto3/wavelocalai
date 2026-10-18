// Parcours de bout en bout (donnees/parcours.json) : une suite d'étapes `{route, scenario, pause_ms,
// note}`. Le joueur va sur la route, joue le scénario de l'écran s'il existe, attend `pause_ms`
// (divisé par la vitesse du simulateur), puis passe à l'étape suivante. Un scénario absent (écran
// encore « à construire ») est sauté et compté, sans arrêter le parcours.

import { loadData } from "../core/data.js";
import { store } from "../core/store.js";

export async function loadParcours() {
  return (await loadData("parcours.json")).parcours;
}

export function runParcours(journey, { router, runScenario, currentScenarios, say }) {
  let stopped = false;
  let wake = null;
  const sleep = (ms) =>
    new Promise((resolve) => {
      const timer = setTimeout(resolve, ms / (store.get().maquette.speed || 1));
      wake = () => {
        clearTimeout(timer);
        resolve();
      };
    });

  const done = (async () => {
    const result = { played: [], skipped: [] };
    for (const [index, step] of journey.steps.entries()) {
      if (stopped) break;
      const label = `Étape ${index + 1} sur ${journey.steps.length}`;
      await router.navigate(step.route);
      const known = currentScenarios().some((scenario) => scenario.id === step.scenario);
      if (step.scenario && known) {
        say(`${label} : ${step.note ?? step.scenario}`);
        await runScenario(step.scenario);
        result.played.push(`${step.route} ${step.scenario}`);
      } else if (step.scenario) {
        say(`${label} : scénario à construire (${step.scenario}).`);
        result.skipped.push(`${step.route} ${step.scenario}`);
      } else {
        say(`${label} : ${step.note ?? step.route}`);
      }
      await sleep(step.pause_ms ?? 1500);
    }
    say(stopped ? "Parcours arrêté." : `Parcours terminé : ${journey.label}.`);
    return result;
  })();

  return {
    done,
    stop() {
      stopped = true;
      wake?.();
    },
  };
}
