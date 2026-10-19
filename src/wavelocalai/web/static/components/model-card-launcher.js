// Bouton « Fiche du modèle » à côté de chaque `wl-model-picker` (décision du 2026-10-19, n° 17), hors
// de la liste d'options. Un observateur du document place un bouton juste après chaque sélecteur
// qui apparaît, sans que les écrans aient à le faire (Chat, Arène, Documents, défauts, et ceux des
// Epics 6 et 7) ; `wl-model-picker.js`, déjà long, n'en sait rien.
//
// - Le bouton ouvre la fiche du modèle choisi dans le panneau de `model-card-drawer.js`, sans
//   changer d'URL. Aucun modèle choisi : pas de bouton.
// - Mode `multi` (l'Arène : deux ou trois modèles) : un bouton par modèle choisi, nommé « Fiche : <nom> ».
// - Le bouton suit le choix (`wl-model-change`), la liste relue (`wl-models-loaded`, qui peut
//   donner un nom à un tag) et les choix posés par le code (`picker.values = …` : garde-fou
//   mémoire, reprise d'une configuration), qui ne lèvent aucun événement mais redessinent le
//   sélecteur : un observateur de son sous-arbre relit alors le choix, et ne refait les boutons que
//   s'il a changé. Un sélecteur retiré de la page emporte ses boutons ; déplacé, ses boutons le suivent.
// - `data-no-card` sur le sélecteur : aucun bouton.

import { element, icon } from "../core/dom.js";
import { t } from "../core/i18n.js";
import { openModelCardDrawer } from "./model-card-drawer.js";

const SELECTOR = "wl-model-picker";
const buttonsOf = new WeakMap(); // sélecteur -> conteneur de ses boutons
const stopOf = new WeakMap(); // sélecteur -> retrait de ses écouteurs

function nameOf(picker, tag) {
  return picker.modelFor?.(tag)?.name ?? tag;
}

const shownKey = new WeakMap(); // conteneur -> choix et noms affichés

function render(picker, box) {
  const tags = picker.values;
  const multi = picker.multi;
  const key = JSON.stringify([multi, tags.map((tag) => [tag, nameOf(picker, tag)])]);
  if (shownKey.get(box) === key) return; // rien n'a changé : les boutons (et leur focus) restent
  shownKey.set(box, key);
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
    // Le parent a été vidé puis refait, ou le sélecteur a été déplacé : ses boutons le suivent.
    if (known.previousElementSibling !== picker) picker.after(known);
    return;
  }
  const box = element("div", "models-card-open-box");
  buttonsOf.set(picker, box);
  picker.after(box);
  const update = () => render(picker, box);
  picker.addEventListener("wl-model-change", update);
  picker.addEventListener("wl-models-loaded", update);
  const redraws = new MutationObserver(update);
  redraws.observe(picker, { childList: true, subtree: true });
  stopOf.set(picker, () => {
    redraws.disconnect();
    picker.removeEventListener("wl-model-change", update);
    picker.removeEventListener("wl-models-loaded", update);
  });
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
    stopOf.get(picker)?.();
    stopOf.delete(picker);
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
