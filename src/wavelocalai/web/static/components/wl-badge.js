// <wl-badge kind="local|cloud|unknown|indicative|single-judge|unreliable|estimated|unmeasurable"> (UX-DR6).
// Origine d'un modèle : Local (vert, `computer`), Cloud (orange, `cloud`), Origine inconnue (gris,
// `help`). Étiquettes de fiabilité : « indicatif », « un seul juge », « note peu fiable » (avec
// l'icône `warning`), « estimé », « non mesurable ».
// Toujours un texte : la couleur et l'icône ne portent jamais seules le sens. Sans Shadow DOM.

import { icon, element } from "../core/dom.js";
import { t } from "../core/i18n.js";

const KINDS = {
  local: { icon: "computer", tone: "local", text: "components.badge.local" },
  cloud: { icon: "cloud", tone: "cloud", text: "components.badge.cloud" },
  unknown: { icon: "help", tone: "unknown", text: "components.badge.unknown" },
  indicative: { icon: null, tone: "label", text: "components.badge.indicative" },
  "single-judge": { icon: null, tone: "label", text: "components.badge.single_judge" },
  unreliable: { icon: "warning", tone: "warning", text: "components.badge.unreliable" },
  estimated: { icon: null, tone: "label", text: "components.badge.estimated" },
  unmeasurable: { icon: null, tone: "label", text: "components.badge.unmeasurable" },
};

export class WlBadge extends HTMLElement {
  static observedAttributes = ["kind"];

  connectedCallback() {
    this.render();
  }

  attributeChangedCallback() {
    if (this.isConnected) this.render();
  }

  render() {
    // Une origine absente ou inattendue est « inconnue » : jamais un badge Local par défaut.
    const kind = KINDS[this.getAttribute("kind")] ?? KINDS.unknown;
    this.className = `wl-badge wl-badge-${kind.tone}`;
    const parts = [];
    if (kind.icon) parts.push(icon(kind.icon));
    parts.push(element("span", "wl-badge-text", t(kind.text)));
    this.replaceChildren(...parts);
  }
}

if (!customElements.get("wl-badge")) customElements.define("wl-badge", WlBadge);
