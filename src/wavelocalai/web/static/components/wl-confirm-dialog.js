// <wl-confirm-dialog> (UX-DR12, AD-20) : confirmation d'une action destructrice dans un `<dialog>`
// natif. Titre en question, conséquence chiffrée, focus sur « Annuler » (jamais sur l'action).
//
//   const confirmed = await dialog.ask({ title, consequence, confirmLabel, cancelLabel?, details? });
//
// `details` (facultatif) : `[{ label, value, long? }]`, ce que la personne valide, sous le titre
// (destinataire, objet, corps d'un email, story 6.4) ; une valeur `long` est en lecture seule,
// défilable au clavier. `consequence` vient après, en rappel.
//
// `ask` rend `true` (confirmé) ou `false` (« Annuler », Échap, `close()`). Le message de résultat,
// au même verbe que le bouton de confirmation, est affiché par l'appelant. Le focus revient à
// l'élément qui l'avait avant l'ouverture, s'il est encore dans la page. Sans Shadow DOM.

import { element } from "../core/dom.js";
import { t } from "../core/i18n.js";

let counter = 0;

// L'élément qui avait le focus à l'ouverture peut avoir été remplacé pendant que le dialogue était
// ouvert (une ligne de tableau reconstruite par un flux système, story 8.5) : son nœud d'origine
// n'est alors plus dans la page. On retrouve son équivalent par ce qui l'identifie (`id`, ou son
// tag et son `data-tag`, convention des lignes de tableau de l'app), plutôt que de perdre le focus.
function reacquire(el) {
  if (!el || el.isConnected) return el;
  if (el.id) return document.getElementById(el.id);
  const tag = el.dataset?.tag;
  const classes = [...(el.classList ?? [])].map((name) => `.${CSS.escape(name)}`).join("");
  if (!tag || !classes) return null;
  return document.querySelector(`${el.tagName.toLowerCase()}${classes}[data-tag="${CSS.escape(tag)}"]`);
}

export class WlConfirmDialog extends HTMLElement {
  #dom = null;
  #resolve = null;
  #returnFocus = null;

  connectedCallback() {
    if (this.#dom) return;
    const id = `wl-confirm-${++counter}`;
    const dialog = element("dialog", "wl-dialog");
    dialog.setAttribute("aria-labelledby", `${id}-title`);
    dialog.setAttribute("aria-describedby", `${id}-consequence`);
    const title = element("h2", "wl-dialog-title");
    title.id = `${id}-title`;
    const details = element("div", "wl-dialog-details");
    details.hidden = true;
    const consequence = element("p", "wl-dialog-consequence");
    consequence.id = `${id}-consequence`;
    const actions = element("div", "wl-dialog-actions");
    const cancel = element("button", "btn wl-dialog-cancel", t("components.confirm.cancel"));
    cancel.type = "button";
    const confirm = element("button", "btn wl-dialog-confirm");
    confirm.type = "button";
    actions.append(cancel, confirm);
    dialog.append(title, details, consequence, actions);
    this.replaceChildren(dialog);
    this.#dom = { dialog, title, details, consequence, cancel, confirm, id };

    cancel.addEventListener("click", () => this.#close(false));
    confirm.addEventListener("click", () => this.#close(true));
    // Échap (événement `cancel` du dialogue) ferme comme « Annuler ».
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      this.#close(false);
    });
  }

  get open() {
    return this.#dom?.dialog.open ?? false;
  }

  // Ferme le dialogue ouvert comme « Annuler » (ou avec `value`) ; sans effet s'il est fermé.
  close(value = false) {
    if (this.#dom?.dialog.open || this.#resolve) this.#close(value);
  }

  ask({ title, consequence, confirmLabel, cancelLabel, details = [] }) {
    this.connectedCallback();
    const { dialog, title: heading, consequence: text, cancel, confirm } = this.#dom;
    heading.textContent = title;
    this.#showDetails(details);
    text.textContent = consequence ?? "";
    cancel.textContent = cancelLabel ?? t("components.confirm.cancel");
    confirm.textContent = confirmLabel;
    this.#returnFocus = document.activeElement;
    this.#resolve?.(false); // une seconde demande referme la première comme « Annuler »
    return new Promise((resolve) => {
      this.#resolve = resolve;
      if (!dialog.open) dialog.showModal();
      cancel.focus();
    });
  }

  #showDetails(details) {
    const { details: list, id } = this.#dom;
    list.hidden = details.length === 0;
    list.replaceChildren(
      ...details.map(({ label, value, long = false }, index) => {
        const term = element("p", "wl-dialog-term", label);
        term.id = `${id}-term-${index}`;
        const body = element("div", long ? "wl-dialog-value wl-dialog-long" : "wl-dialog-value", value);
        if (long) {
          body.tabIndex = 0; // une zone qui défile se lit au clavier
          body.setAttribute("role", "group");
          body.setAttribute("aria-labelledby", term.id);
        }
        const field = element("div", "wl-dialog-field");
        field.append(term, body);
        return field;
      }),
    );
  }

  #close(value) {
    const { dialog } = this.#dom;
    if (dialog.open) dialog.close();
    const resolve = this.#resolve;
    this.#resolve = null;
    resolve?.(value);
    const back = this.#returnFocus;
    this.#returnFocus = null;
    if (back?.isConnected && typeof back.focus === "function") back.focus();
    // Rattrapage (story 8.5) : si le nœud d'origine a été remplacé pendant l'ouverture, ou si le
    // retour natif de `<dialog>` a laissé le focus sur `body`, on repose le focus sur l'équivalent
    // actuel une image plus tard -- seulement s'il est encore perdu, pour ne jamais écraser le focus
    // qu'un appelant a posé lui-même après `await ask()` (lignes de documents, approbations…).
    requestAnimationFrame(() => {
      const active = document.activeElement;
      if (active && active !== document.body && active.isConnected && !this.contains(active)) return;
      const target = reacquire(back);
      if (target?.isConnected && typeof target.focus === "function") target.focus();
    });
  }
}

if (!customElements.get("wl-confirm-dialog")) customElements.define("wl-confirm-dialog", WlConfirmDialog);
