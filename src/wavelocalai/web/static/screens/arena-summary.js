// Résumé de la comparaison lancée (D-16, story 3.2 puis 3.3) : il remplace la configuration jusqu'à
// `run_ended` et dit la question, les modèles comparés et le juge. Chaque ligne est une fonction qui
// rend `[libellé, contenu]`, ou `null` quand elle n'a rien à dire encore (le juge n'est connu qu'avec
// l'événement `judge`). Les noms et la question sont posés par `textContent`, jamais en HTML.

import { element } from "../core/dom.js";
import { t } from "../core/i18n.js";

function originBadge(origin) {
  const badge = document.createElement("wl-badge");
  badge.setAttribute("kind", ["local", "cloud"].includes(origin) ? origin : "unknown");
  return badge;
}

// Un modèle par puce : son nom et son badge Local ou Cloud.
export function modelsRow(lanes) {
  const models = element("ul", "arena-summary-models");
  for (const [tag, entry] of lanes) {
    const item = element("li", "arena-summary-model");
    item.append(element("span", "", entry.name), originBadge(entry.origin));
    item.dataset.tag = tag;
    models.append(item);
  }
  return [t("arena.summary.models"), models];
}

// Le juge : son nom et son badge, ou « Aucun juge » quand le serveur n'en a retenu aucun.
export function judgeRow(judge) {
  if (!judge) return null;
  const content = element("span", "arena-summary-judge");
  if (judge.none) content.append(t("arena.summary.no_judge"));
  else content.append(element("span", "", judge.name), originBadge(judge.origin));
  content.dataset.judge = judge.none ? "none" : "chosen";
  return [t("arena.summary.judge"), content];
}

// Le bloc : titre (reçoit le focus quand le formulaire se retire) et liste de lignes.
export function summaryView(uid) {
  const title = element("h2", "arena-summary-title", t("arena.summary.title"));
  title.tabIndex = -1;
  title.id = `${uid}-summary-title`;
  const list = element("dl", "arena-summary-list");
  const el = element("section", "arena-summary");
  el.setAttribute("aria-labelledby", title.id);
  el.hidden = true;
  el.append(title, list);
  return {
    el,
    title,
    render(rows) {
      list.replaceChildren(
        ...rows
          .map((row) => row())
          .filter(Boolean)
          .map(([label, content]) => {
            const item = element("div", "arena-summary-row");
            const value = element("dd", "");
            value.append(content);
            item.append(element("dt", "", label), value);
            return item;
          }),
      );
    },
  };
}
