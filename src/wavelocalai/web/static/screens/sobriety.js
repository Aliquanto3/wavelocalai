// Sobriété et matériel, `#/sobriete` (UX-DR26, AD-6, AD-10, AD-15, AD-20) : la machine et la session
// en direct. Santé du système (`sobriety-health.js`), empreinte carbone de la session
// (`sobriety-carbon.js`), puis deux panneaux repliés (`sobriety-details.js`). L'historique et la
// remise à zéro du compteur sont ceux de la story 5.2.
//
// - Les valeurs viennent du store, rempli par le flux système (`core/system.js`) : l'écran ne
//   calcule aucune mesure et n'appelle l'API qu'à l'ouverture d'un panneau replié.
// - Onglet masqué (`visibilitychange`) : le flux est fermé par `core/system.js` ; l'écran cesse de
//   lire le store, garde ses dernières valeurs et le dit. Au retour, le flux est rouvert et relit
//   `GET /api/carbon/session` (les `carbon_updated` manqués ne se rejouent pas) ; l'écran reprend.
// - Le routeur garde l'écran monté quand on le quitte : masqué, il ne relit rien, et il relit ses
//   panneaux ouverts quand il redevient visible.

import { element } from "../core/dom.js";
import { t } from "../core/i18n.js";
import { store } from "../core/store.js";
import "../components/index.js";
import { buildCarbon } from "./sobriety-carbon.js";
import { buildDetails, METHOD_ID } from "./sobriety-details.js";
import { buildHealth } from "./sobriety-health.js";

export function mount(host) {
  const details = buildDetails();
  const health = buildHealth();
  const carbon = buildCarbon({ onMethod: () => details.openMethod(), methodId: METHOD_ID });

  host.replaceChildren(
    element("h1", "", t("screens.sobriety")),
    element("p", "lead", t("sobriety.lead")),
    health.section,
    carbon.section,
    details.identity,
    details.method,
  );

  let paused = false;
  let previousCarbon = store.get().carbon;

  function render(state) {
    health.render(state, { paused });
    carbon.render(state);
    if (state.carbon !== previousCarbon) {
      previousCarbon = state.carbon;
      details.carbonChanged(host.hidden);
    }
  }

  let unsubscribe = null;
  function resume() {
    paused = false;
    host.dataset.live = "true";
    if (!unsubscribe) unsubscribe = store.subscribe(render);
    render(store.get());
  }
  function pause() {
    unsubscribe?.();
    unsubscribe = null;
    paused = true;
    host.dataset.live = "false";
    render(store.get()); // les dernières valeurs restent, la légende le dit
  }
  function onVisibility() {
    if (document.hidden) pause();
    else resume();
  }

  // L'écran redevient visible (le routeur lève `hidden`) : panneaux ouverts relus.
  let wasHidden = host.hidden;
  const visibility = new MutationObserver(() => {
    if (host.hidden === wasHidden) return;
    wasHidden = host.hidden;
    if (!wasHidden) details.shown();
  });
  visibility.observe(host, { attributes: true, attributeFilter: ["hidden"] });

  document.addEventListener("visibilitychange", onVisibility);
  if (document.hidden) pause();
  else resume();

  return () => {
    visibility.disconnect();
    document.removeEventListener("visibilitychange", onVisibility);
    details.dispose();
    unsubscribe?.();
    unsubscribe = null;
    delete host.dataset.live;
    host.replaceChildren();
  };
}
