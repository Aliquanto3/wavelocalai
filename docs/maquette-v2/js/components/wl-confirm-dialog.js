// <wl-confirm-dialog> (UX-DR12) : `<dialog>` natif, titre en question, conséquence chiffrée, focus
// sur « Annuler ». `await dialog.ask({title, consequence, confirmLabel, cancelLabel, details, note})`
// rend true (confirmé) ou false (Annuler, Échap, `close()`). `details` : liste `[{label, value}]`
// affichée en `dl` (validation d'un email : destinataire, objet, corps) ; `note` : mention sous la liste
// (délai de validation). `dialog.close(valeur = false)` ferme de l'extérieur (run terminé, validation
// expirée). Le message de résultat, au même verbe que le bouton, est affiché par l'appelant.
// Sans Shadow DOM.

import { element } from "../core/dom.js";
import { t } from "../core/i18n.js";

let counter = 0;

export class WlConfirmDialog extends HTMLElement {
  #dom = null;
  #resolve = null;

  connectedCallback() {
    if (this.#dom) return;
    const id = `wl-confirm-${++counter}`;
    const dialog = element("dialog", "wl-dialog");
    dialog.setAttribute("aria-labelledby", `${id}-title`);
    dialog.setAttribute("aria-describedby", `${id}-consequence`);
    const title = element("h2", "wl-dialog-title");
    title.id = `${id}-title`;
    const consequence = element("p", "wl-dialog-consequence");
    consequence.id = `${id}-consequence`;
    const details = element("dl", "wl-dialog-details");
    const note = element("p", "help wl-dialog-note");
    const actions = element("div", "wl-dialog-actions");
    const cancel = element("button", "btn", t("states.confirm.cancel"));
    cancel.type = "button";
    const confirm = element("button", "btn btn-primary", "");
    confirm.type = "button";
    actions.append(cancel, confirm);
    dialog.append(title, consequence, details, note, actions);
    this.replaceChildren(dialog);
    this.#dom = { dialog, title, consequence, details, note, cancel, confirm };

    cancel.addEventListener("click", () => this.#close(false));
    confirm.addEventListener("click", () => this.#close(true));
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      this.#close(false);
    });
    // Échap ferme le dialogue sans arrêter un run en cours (wl-run-status lit `defaultPrevented`).
    dialog.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        this.#close(false);
      }
    });
  }

  get open() {
    return this.#dom?.dialog.open ?? false;
  }

  // Ferme le dialogue ouvert comme « Annuler » (ou avec `value`) ; sans effet s'il est fermé.
  close(value = false) {
    if (this.#dom?.dialog.open || this.#resolve) this.#close(value);
  }

  ask({ title, consequence, confirmLabel, cancelLabel, details = [], note = "" }) {
    this.connectedCallback();
    const { dialog, title: heading, consequence: text, details: list, note: noteNode, cancel, confirm } = this.#dom;
    noteNode.textContent = note;
    noteNode.hidden = !note;
    heading.textContent = title;
    text.textContent = consequence ?? "";
    cancel.textContent = cancelLabel ?? t("states.confirm.cancel");
    confirm.textContent = confirmLabel;
    list.replaceChildren(
      ...details.map(({ label, value }) => {
        const row = element("div", "wl-dialog-row");
        row.append(element("dt", "", label), element("dd", "", value));
        return row;
      }),
    );
    list.hidden = details.length === 0;
    this.returnFocus = document.activeElement;
    this.#resolve?.(false);
    dialog.showModal();
    cancel.focus();
    return new Promise((resolve) => {
      this.#resolve = resolve;
    });
  }

  #close(value) {
    const { dialog } = this.#dom;
    if (dialog.open) dialog.close();
    const resolve = this.#resolve;
    this.#resolve = null;
    resolve?.(value);
    if (this.returnFocus?.isConnected) this.returnFocus.focus();
  }
}

if (!customElements.get("wl-confirm-dialog")) customElements.define("wl-confirm-dialog", WlConfirmDialog);
