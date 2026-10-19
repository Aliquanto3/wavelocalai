// Panneau « Fiche du modèle » ouvert depuis un `wl-model-picker` (décision du 2026-10-19, n° 17) : la
// même fiche que l'écran Modèles, en panneau à droite de l'écran courant, sans changer d'URL.
//
// - Un seul panneau à la fois ; « Fermer la fiche » et Échap le ferment, le focus revient au bouton
//   qui l'avait ouvert. Pas modal : le reste de la page reste lisible, mais le panneau couvre sa droite.
// - Le lien « Ouvrir dans l'écran Modèles » mène à `#/modeles/<tag>` et ferme le panneau.
// - Un modèle pas installé n'a pas de bouton d'installation ici : l'installation vit dans l'écran
//   Modèles (le lien y mène).

import { element, icon } from "../core/dom.js";
import { t } from "../core/i18n.js";
import { createCardLoader } from "./model-card-loader.js";

let opened = null; // { aside, close }
let counter = 0;

export function closeModelCardDrawer() {
  opened?.close();
}

export function openModelCardDrawer(tag, { opener = null } = {}) {
  closeModelCardDrawer();
  const id = `models-card-drawer-${++counter}`;
  const aside = element("aside", "models-card-drawer");
  aside.id = id;
  aside.setAttribute("aria-labelledby", `${id}-title`);
  const bar = element("div", "models-card-drawer-bar");
  const close = element("button", "btn models-card-close");
  close.type = "button";
  close.append(icon("close"), element("span", "", t("models.card.close")));
  const open = element("a", "btn", t("models.card.open_models"));
  open.href = `#/modeles/${encodeURIComponent(tag)}`;
  bar.append(open, close);
  const body = element("div", "models-card-body");
  aside.append(bar, body);
  document.body.append(aside);

  const loader = createCardLoader({ container: body, headingId: `${id}-title` });

  function dispose() {
    document.removeEventListener("keydown", onKey, true);
    removeEventListener("hashchange", dispose);
    loader.clear();
    aside.remove();
    if (opened?.aside === aside) opened = null;
  }
  function closeAndRestore() {
    dispose();
    if (opener?.isConnected) opener.focus();
  }
  function onKey(event) {
    if (event.key === "Escape" && !event.defaultPrevented) {
      event.preventDefault();
      closeAndRestore();
    }
  }
  close.addEventListener("click", closeAndRestore);
  document.addEventListener("keydown", onKey, true);
  addEventListener("hashchange", dispose); // un changement d'écran referme le panneau (sans rendre le focus)

  opened = { aside, close: dispose };
  loader.open(tag).then(() => {
    if (opened?.aside === aside) loader.heading?.focus({ preventScroll: true });
  });
  return aside;
}
