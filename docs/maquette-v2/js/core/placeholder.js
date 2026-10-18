// Écran « à construire » : titre, onglets du module, état vide. Sert aux routes dont l'écran n'est
// pas encore maquetté, pour que la navigation et les tests passent. Un agent d'écran remplace le
// module de son écran (js/screens/<écran>.js) et n'importe plus ce fichier.

import { element } from "./dom.js";

export function mountPlaceholder(host, ctx) {
  const parts = [element("h1", "", ctx.route.title)];
  if (ctx.route.module && ctx.routes.some((route) => route.module === ctx.route.module && route.tab)) {
    parts.push(ctx.tabs());
  }
  const values = Object.entries(ctx.params);
  const text = values.length
    ? `${ctx.t("states.empty_screen.text")} Paramètre de l'adresse : ${values.map(([key, value]) => `${key} = ${value}`).join(", ")}.`
    : ctx.t("states.empty_screen.text");
  parts.push(ctx.states.emptyState({ title: ctx.t("states.empty_screen.title"), text }));
  host.replaceChildren(...parts);
  return () => host.replaceChildren();
}
