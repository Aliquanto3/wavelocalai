// Repris de static/components/wl-error.js (avec le rendu `code` de feat/v2-ecran-chat) ; ajout : boutons.
// <wl-error> : affichage d'erreur unique (UX-DR16, AD-18). `el.error = {code, message, action,
// detail}` (l'enveloppe de l'API, telle quelle) affiche `message`, puis `action`, et `detail`
// replié sous « Détails techniques ». Le front n'invente ni message ni code. Sans Shadow DOM.
// L'attribut `alert` ajoute `role="alert"` (erreur qui surgit pendant que l'utilisateur agit).

import { element } from "../core/dom.js";
import { t } from "../core/i18n.js";

// Les textes du catalogue citent les commandes entre accents graves (`ollama serve`) : rendues
// en `<code>`, jamais telles quelles.
function richText(tag, className, text) {
  const node = element(tag, className);
  const parts = String(text ?? "").split("`");
  parts.forEach((part, index) => {
    if (!part) return;
    const code = index % 2 === 1 && index < parts.length - 1;
    node.append(code ? element("code", "", part) : document.createTextNode(part));
  });
  return node;
}

function detailText(detail) {
  if (detail === null || detail === undefined) return "";
  if (typeof detail === "string") return detail;
  const { technical, ...machine } = detail;
  const lines = [];
  if (technical) lines.push(String(technical));
  for (const [key, value] of Object.entries(machine)) lines.push(`${key} : ${JSON.stringify(value)}`);
  return lines.join("\n");
}

export class WlError extends HTMLElement {
  #error = null;

  get error() {
    return this.#error;
  }

  set error(value) {
    this.#error = value ?? null;
    if (this.isConnected) this.render();
  }

  connectedCallback() {
    this.render();
  }

  render() {
    const error = this.#error;
    this.className = "wl-error";
    if (this.hasAttribute("alert")) this.setAttribute("role", "alert");
    if (!error) {
      this.replaceChildren();
      this.hidden = true;
      return;
    }
    this.hidden = false;
    this.dataset.code = error.code ?? "";
    const parts = [richText("p", "wl-error-message", error.message)];
    if (error.action) parts.push(richText("p", "wl-error-action", error.action));
    const technical = detailText(error.detail);
    if (technical) {
      const details = element("details", "wl-error-details");
      details.append(
        element("summary", "", t("components.error.details")),
        element("pre", "wl-error-technical", technical),
      );
      parts.push(details);
    }
    // Maquette : boutons d'action prévus par le code (donnees/erreurs.json, champ `buttons`). Un clic
    // émet `wl-error-action` (`detail.id`, `detail.code`) ; un bouton à `href` est un lien.
    const buttons = Array.isArray(error.buttons) ? error.buttons : [];
    if (buttons.length) {
      const row = element("div", "wl-error-buttons");
      for (const spec of buttons) {
        const control = spec.href ? element("a", "btn", spec.label) : element("button", "btn", spec.label);
        if (spec.href) control.href = spec.href;
        else control.type = "button";
        control.dataset.action = spec.id;
        control.addEventListener("click", () => {
          this.dispatchEvent(
            new CustomEvent("wl-error-action", { bubbles: true, detail: { id: spec.id, code: error.code } }),
          );
        });
        row.append(control);
      }
      parts.splice(error.action ? 2 : 1, 0, row);
    }
    this.replaceChildren(...parts);
  }
}

if (!customElements.get("wl-error")) customElements.define("wl-error", WlError);
