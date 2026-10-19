// Bouton « Fiche du modèle » à côté de chaque `wl-model-picker` (décision du 2026-10-19, n° 17), hors
// de la liste d'options. Un observateur du document place un bouton juste après chaque sélecteur
// qui apparaît, sans que les écrans aient à le faire (Chat, Arène, Documents, défauts, et ceux des
// Epics 6 et 7) ; `wl-model-picker.js`, déjà long, n'en sait rien.
//
// - Le bouton ouvre la fiche du modèle choisi dans le panneau de `model-card-drawer.js`, sans
//   changer d'URL. Aucun modèle choisi : pas de bouton.
// - Mode `multi` (l'Arène : deux ou trois modèles) : un bouton par modèle choisi, nommé « Fiche : <nom> ».
// - Le bouton suit le choix (`wl-model-change`) et la liste relue (`wl-models-loaded`, qui peut
//   donner un nom à un tag). Un sélecteur retiré de la page emporte ses boutons.
// - `data-no-card` sur le sélecteur : aucun bouton.

import { element, icon } from "../core/dom.js";
import { t } from "../core/i18n.js";
import { openModelCardDrawer } from "./model-card-drawer.js";

const SELECTOR = "wl-model-picker";
const buttonsOf = new WeakMap(); // sélecteur -> conteneur de ses boutons

function nameOf(picker, tag) {
  return picker.modelFor?.(tag)?.name ?? tag;
}

function render(picker, box) {
  const tags = picker.values;
  const multi = picker.multi;
  const buttons = tags.map((tag) => {
    const name = nameOf(picker, tag);
    const button = element("button", "btn models-card-open");
    button.type = "button";
    button.dataset.tag = tag;
    button.append(icon("info"), element("span", "", t(multi ? "models.card.open_button_named" : "models.card.open_button", { name })));
    button.setAttribute("aria-label", t("models.card.open_button_aria", { name }));
    button.addEventListener("click", () => openModelCardDrawer(tag, { opener: button }));
    return button;
  });
  box.replaceChildren(...buttons);
  box.hidden = buttons.length === 0;
}

function attach(picker) {
  if (picker.hasAttribute("data-no-card")) return;
  const known = buttonsOf.get(picker);
  if (known) {
    if (!known.isConnected) picker.after(known); // le parent a été vidé puis refait
    return;
  }
  const box = element("div", "models-card-open-box");
  buttonsOf.set(picker, box);
  picker.after(box);
  const update = () => render(picker, box);
  picker.addEventListener("wl-model-change", update);
  picker.addEventListener("wl-models-loaded", update);
  update();
}

function detach(picker) {
  const box = buttonsOf.get(picker);
  if (!box) return;
  // Un sélecteur déplacé puis remis dans la page (même tick) garde ses boutons.
  queueMicrotask(() => {
    if (picker.isConnected) return;
    box.remove();
    buttonsOf.delete(picker);
  });
}

function each(node, action) {
  if (node.nodeType !== Node.ELEMENT_NODE) return;
  if (node.matches(SELECTOR)) action(node);
  node.querySelectorAll?.(SELECTOR).forEach(action);
}

export function watchModelPickers(root = document.documentElement) {
  const observer = new MutationObserver((records) => {
    for (const record of records) {
      record.addedNodes.forEach((node) => each(node, attach));
      record.removedNodes.forEach((node) => each(node, detach));
    }
  });
  observer.observe(root, { childList: true, subtree: true });
  root.querySelectorAll(SELECTOR).forEach(attach);
  return () => observer.disconnect();
}

watchModelPickers();
