// <wl-metric label="Débit" value="38" unit="tokens/s" help="…" provisional> (UX-DR7).
// Libellé, valeur avec son unité en `metric-value`, aide derrière un `<button aria-describedby>`,
// état « provisoire » en italique (et dit en toutes lettres). La valeur arrive déjà mise en forme
// par `core/format.js` : le composant ne calcule rien. Sans Shadow DOM.

import { icon, element } from "../core/dom.js";
import { t } from "../core/i18n.js";

let counter = 0;

export class WlMetric extends HTMLElement {
  static observedAttributes = ["label", "value", "unit", "help", "provisional"];

  connectedCallback() {
    this.render();
  }

  attributeChangedCallback() {
    if (this.isConnected) this.render();
  }

  render() {
    const label = this.getAttribute("label") ?? "";
    const help = this.getAttribute("help");
    const provisional = this.hasAttribute("provisional");
    this.className = "wl-metric";
    this.dataset.provisional = String(provisional);
    this.helpId ??= `wl-metric-help-${++counter}`;

    const head = element("div", "wl-metric-head");
    head.append(element("span", "wl-metric-label", label));
    const children = [head];

    if (help) {
      const button = element("button", "wl-metric-help-button");
      button.type = "button";
      button.setAttribute("aria-label", t("components.metric.help_for", { label }));
      button.setAttribute("aria-describedby", this.helpId);
      button.setAttribute("aria-expanded", "false");
      button.append(icon("info"));
      const text = element("p", "wl-metric-help", help);
      text.id = this.helpId;
      text.hidden = true;
      button.addEventListener("click", () => {
        text.hidden = !text.hidden;
        button.setAttribute("aria-expanded", String(!text.hidden));
      });
      button.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !text.hidden) {
          event.stopPropagation();
          text.hidden = true;
          button.setAttribute("aria-expanded", "false");
        }
      });
      head.append(button);
      children.push(text);
    }

    const value = element("p", "wl-metric-value");
    value.append(element("span", "wl-metric-number", this.getAttribute("value") ?? ""));
    const unit = this.getAttribute("unit");
    if (unit) value.append(" ", element("span", "wl-metric-unit", unit));
    if (provisional) value.append(" ", element("span", "wl-metric-flag", `(${t("components.metric.provisional")})`));
    children.splice(1, 0, value);
    this.replaceChildren(...children);
  }
}

if (!customElements.get("wl-metric")) customElements.define("wl-metric", WlMetric);
