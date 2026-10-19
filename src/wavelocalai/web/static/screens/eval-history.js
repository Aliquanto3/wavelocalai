// Évaluations passées (story 7.3, décision du 2026-10-19) : la liste de `GET /api/rag/eval/runs`, les
// plus récentes d'abord, chacune un lien vers `#/documents/evaluation/<run_id>`. Rouvrir relit le
// résultat enregistré, sans relancer de modèle. Le serveur ne liste pas une évaluation effacée ; le
// début de la question est posé par `textContent`, jamais en HTML.
//
//   const history = historyView(uid, nameOf);   history.el  history.refresh()  history.render()

import { api } from "../core/api.js";
import { element } from "../core/dom.js";
import { formatDateTime, plural } from "../core/format.js";
import { t } from "../core/i18n.js";

const STATUSES = ["ok", "cancelled", "error", "interrupted", "running"];

export function historyView(uid, nameOf) {
  const title = element("h2", "eval-history-title", t("evaluation.history.title"));
  title.id = `${uid}-history-title`;
  const help = element("p", "help", t("evaluation.history.help"));
  const list = element("ul", "eval-history-list");
  const el = element("section", "eval-history");
  el.setAttribute("aria-labelledby", title.id);
  el.hidden = true;
  el.append(title, help, list);

  let runs = [];
  let ticket = 0;

  function item(run) {
    const models = (run.models ?? []).map((tag) => nameOf(tag) ?? tag).join(", ");
    const state = STATUSES.includes(run.status) ? run.status : "interrupted";
    const link = element("a", "eval-history-link");
    link.href = `#/documents/evaluation/${encodeURIComponent(run.run_id)}`;
    link.append(
      element("span", "eval-history-when", formatDateTime(run.started_at)),
      element("span", "eval-history-models", models),
      element("span", "eval-history-count", plural("evaluation.history.questions", run.question_count ?? 1)),
      element("span", "eval-history-state", t(`evaluation.history.status.${state}`)),
    );
    if (run.question) link.append(element("span", "eval-history-question", run.question));
    const entry = element("li", "eval-history-item");
    entry.dataset.runId = run.run_id;
    entry.append(link);
    return entry;
  }

  function render() {
    list.replaceChildren(...runs.map(item));
    el.hidden = runs.length === 0;
  }

  return {
    el,
    render,
    async refresh() {
      const mine = ++ticket;
      try {
        const body = await api.evalRuns();
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
