// Onglets d'un module (UX-DR4) : les écrans du module, dans l'ordre du registre. L'écran courant
// porte `aria-current="page"` ; un écran à venir est un `<a>` sans `href`, `aria-disabled`,
// focalisable, avec sa raison en texte visible relié par `aria-describedby` (comme le menu des
// modules de la barre haute).

import { MODULES } from "./registry.js";
import { element } from "./dom.js";
import { t } from "./i18n.js";

let counter = 0;

export function screenTabs(moduleId, currentId) {
  const module = MODULES.find((candidate) => candidate.id === moduleId);
  const nav = element("nav", "screen-tabs");
  nav.setAttribute("aria-label", t("tabs.label", { module: t(`modules.${moduleId}`) }));
  const list = element("ul", "screen-tabs-list");
  for (const screen of module.screens) {
    const item = element("li", "screen-tab");
    const link = element("a", "screen-tab-link", t(`screens.${screen.id}`));
    if (screen.status === "available") {
      link.href = `#${screen.path}`;
      if (screen.id === currentId) link.setAttribute("aria-current", "page");
      item.append(link);
    } else {
      const reason = element("span", "screen-tab-reason", t("router.planned"));
      reason.id = `screen-tab-reason-${++counter}`;
      link.setAttribute("role", "link");
      link.setAttribute("aria-disabled", "true");
      link.tabIndex = 0;
      link.setAttribute("aria-describedby", reason.id);
      link.addEventListener("click", (event) => event.preventDefault());
      item.append(link, reason);
    }
    list.append(item);
  }
  nav.append(list);
  return nav;
}
