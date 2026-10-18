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
    this.replaceChildren(...parts);
  }
}

if (!customElements.get("wl-error")) customElements.define("wl-error", WlError);
