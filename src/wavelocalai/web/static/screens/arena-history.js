// Comparaisons précédentes (story 3.6, AD-5) : la liste de `GET /api/arena/runs`, les plus récentes
// d'abord, chacune un lien vers `#/arene/comparer/<run_id>`. Rouvrir reconstruit l'écran depuis la base
// (colonnes, notes, classement, matrice, verdict) sans relancer de modèle. Le serveur ne liste pas
// une comparaison effacée ; le début de la question est posé par `textContent`, jamais en HTML.
//
//   const history = historyView(uid, nameOf);   history.el  history.refresh(message?)  history.render()
//
// `refresh(message)` relit la liste et dit `message` dans la zone polie (« Comparaison effacée »).

import { api } from "../core/api.js";
import { element } from "../core/dom.js";
import { formatDateTime } from "../core/format.js";
import { t } from "../core/i18n.js";

const STATUSES = ["ok", "cancelled", "error", "interrupted", "running"];

export function historyView(uid, nameOf) {
  const title = element("h2", "arena-history-title", t("arena.history.title"));
  title.id = `${uid}-history-title`;
  const help = element("p", "help", t("arena.history.help"));
  const list = element("ul", "arena-history-list");
  const status = element("p", "arena-history-status");
  status.setAttribute("role", "status");
  status.hidden = true;
  const el = element("section", "arena-history");
  el.setAttribute("aria-labelledby", title.id);
  el.hidden = true;
  el.append(title, help, list, status);

  let runs = [];
  let ticket = 0;

  function item(run) {
    const models = run.models.map((tag) => nameOf(tag) ?? tag).join(", ");
    const state = STATUSES.includes(run.status) ? run.status : "interrupted";
    const link = element("a", "arena-history-link");
    link.href = `#/arene/comparer/${encodeURIComponent(run.run_id)}`;
    link.append(
      element("span", "arena-history-when", formatDateTime(run.started_at)),
      element("span", "arena-history-models", models),
      element("span", "arena-history-state", t(`arena.history.status.${state}`)),
    );
    if (run.question) link.append(element("span", "arena-history-question", run.question));
    const entry = element("li", "arena-history-item");
    entry.dataset.runId = run.run_id;
    entry.append(link);
    return entry;
  }

  function render() {
    list.replaceChildren(...runs.map(item));
    el.hidden = runs.length === 0 && status.hidden;
  }

  return {
    el,
    render,
    async refresh(message = "") {
      const mine = ++ticket;
      status.textContent = message;
      status.hidden = message === "";
      try {
        const body = await api.arenaRuns();
        if (mine !== ticket) return;
        runs = Array.isArray(body?.runs) ? body.runs : [];
      } catch {
        if (mine !== ticket) return;
        runs = []; // liste illisible : l'écran fonctionne sans, le lancement n'en dépend pas
      }
      render();
    },
  };
}
