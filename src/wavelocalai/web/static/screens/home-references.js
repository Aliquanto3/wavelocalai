// Carte « Références » de l'Accueil (story 5.8, UX-DR24, D-8, D-10) : « Références » en titre, « Quel
// modèle pour quel usage ? » en sous-titre, puis le meilleur score publié par le banc, en pourcentage
// avec son libellé « Part de réussite » en tête (D-5). Elle ouvre `#/arene/references`.
//
//   const card = referencesCard();   card?.el  card?.refresh()  card?.dispose()
//
// - Elle n'existe que si l'écran Références est disponible (registre) ; elle reste masquée et vide
//   (aucun lien dans la page) tant que le serveur n'a pas dit `available` : sans références publiées,
//   elle n'apparaît pas.
// - Un seul appel de lecture (`GET /api/references`), jamais avant le repère `shell-ready` (AD-6
//   amendé), relu à chaque affichage de l'Accueil, jamais en boucle. Aucun calcul : `top` vient du
//   serveur. Une panne laisse la carte masquée.
// - Sa propre icône (`leaderboard`), jamais celle de l'Arène (`swords`).

import { api } from "../core/api.js";
import { element, icon } from "../core/dom.js";
import { formatPercent } from "../core/format.js";
import { t } from "../core/i18n.js";
import { MODULES } from "../core/registry.js";
import { shellReady } from "../core/shell-ready.js";

export const REFERENCES_ICON = "leaderboard";

export function referencesCard() {
  const arena = MODULES.find((module) => module.id === "arena");
  const screen = arena?.screens.find((candidate) => candidate.id === "arena-references");
  if (screen?.status !== "available") return null;

  const link = element("a", "home-module-link");
  link.href = `#${screen.path}`;
  const summary = element("span", "home-module-summary");
  link.append(
    icon(REFERENCES_ICON),
    element("span", "home-module-name", t("home.references.name")),
    element("span", "home-module-long", t("home.references.long")),
    summary,
  );
  const el = element("li", "home-module home-references");
  el.hidden = true; // et vide : sans références, aucun lien n'existe sur l'Accueil

  let alive = true;
  let reading = 0;
  return {
    el,
    async refresh() {
      const mine = ++reading;
      await shellReady();
      if (!alive) return;
      try {
        const references = await api.references();
        if (!alive || mine !== reading) return;
        const top = references.available ? references.top : null;
        if (top) {
          summary.textContent = t("home.references.summary", {
            score: formatPercent(Math.round(top.score * 100)),
            model: top.name,
            usage: top.usage_label,
            source: references.source,
          });
        }
        el.replaceChildren(...(top ? [link] : []));
        el.hidden = !top;
      } catch {
        if (alive && mine === reading) {
          el.replaceChildren();
          el.hidden = true;
        }
      }
    },
    dispose() {
      alive = false;
    },
  };
}
