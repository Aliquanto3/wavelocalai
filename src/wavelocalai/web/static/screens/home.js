// Accueil : la coquille seulement. Les cartes d'état arrivent avec la story 1.9 et les suivantes.

import { t } from "../core/i18n.js";

export function mount(host) {
  const title = document.createElement("h1");
  title.textContent = t("screens.home");
  const lead = document.createElement("p");
  lead.className = "lead";
  lead.textContent = t("home.lead");
  host.replaceChildren(title, lead);
  return () => host.replaceChildren();
}
