// <wl-skeleton lines="3" slow-after="2500" slow-text="…"> : squelette de premier chargement (UX-DR17,
// 03 §3.8 : jamais d'écran blanc). Après `slow-after` ms (2 500 par défaut), un message dit que le
// chargement est plus long que prévu (texte par défaut : le premier chargement d'un modèle prend de
// 8 à 26 s). `aria-busy` est porté par le conteneur de l'appelant ; le texte caché dit « Chargement… ».

import { element } from "../core/dom.js";
import { t } from "../core/i18n.js";
import { store } from "../core/store.js";

export class WlSkeleton extends HTMLElement {
  #timer = null;

  connectedCallback() {
    const count = Math.max(1, Number(this.getAttribute("lines") ?? 3));
    this.className = "wl-skeleton";
    const bars = element("div", "wl-skeleton-bars");
    bars.setAttribute("aria-hidden", "true");
    for (let i = 0; i < count; i++) bars.append(element("span", "wl-skeleton-bar"));
    const label = element("span", "sr-only", t("states.loading"));
    const slow = element("p", "help wl-skeleton-slow");
    slow.setAttribute("role", "status");
    slow.hidden = true;
    this.replaceChildren(bars, label, slow);
    const after = Number(this.getAttribute("slow-after") ?? 2500) / (store.get().maquette.speed || 1);
    this.#timer = setTimeout(() => {
      slow.textContent = this.getAttribute("slow-text") || t("states.slow_loading");
      slow.hidden = false;
    }, after);
  }

  disconnectedCallback() {
    clearTimeout(this.#timer);
  }
}

if (!customElements.get("wl-skeleton")) customElements.define("wl-skeleton", WlSkeleton);
