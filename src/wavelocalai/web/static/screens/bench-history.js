// Tests passés du Banc d'essai (story 7.4, décision du 2026-10-19, n° 14) : la liste de `GET
// /api/bench/runs`, les plus récents d'abord, chacun un lien vers `#/arene/banc/<run_id>`. Rouvrir
// relit le résultat enregistré, sans relancer de modèle. L'entrée est posée par `textContent`, jamais
// en HTML.
//
//   const history = historyView(uid, { scenarioName, modelName });   history.el  history.refresh()

import { api } from "../core/api.js";
import { element } from "../core/dom.js";
import { formatDateTime } from "../core/format.js";
import { t } from "../core/i18n.js";

const STATUSES = ["ok", "cancelled", "error", "interrupted", "running"];

export function historyView(uid, { scenarioName, modelName }) {
  const title = element("h2", "bc-history-title", t("bench.history.title"));
  title.id = `${uid}-history-title`;
  const help = element("p", "help", t("bench.history.help"));
  const list = element("ul", "bc-history-list");
  const el = element("section", "bc-history");
  el.setAttribute("aria-labelledby", title.id);
  el.hidden = true;
  el.append(title, help, list);

  let runs = [];
  let ticket = 0;

  function item(run) {
    const state = STATUSES.includes(run.status) ? run.status : "interrupted";
    const link = element("a", "bc-history-link");
    link.href = `#/arene/banc/${encodeURIComponent(run.run_id)}`;
    const verdict = run.format_ok === null || run.format_ok === undefined ? null : t(run.format_ok ? "bench.history.format_ok" : "bench.history.format_ko");
    const options = [run.force_format ? t("bench.history.forced") : null, run.concise ? t("bench.history.concise") : null].filter(Boolean);
    link.append(
      element("span", "bc-history-when", formatDateTime(run.started_at)),
      element("span", "bc-history-scenario", scenarioName(run.scenario)),
      element("span", "bc-history-model", modelName(run.model) ?? run.model ?? ""),
      element("span", "bc-history-state", t(`bench.history.status.${state}`)),
    );
    if (verdict) link.append(element("span", "bc-history-verdict", verdict));
    if (options.length) link.append(element("span", "bc-history-options", options.join(" · ")));
    if (run.input) link.append(element("span", "bc-history-input", run.input));
    const entry = element("li", "bc-history-item");
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
        const body = await api.benchRuns();
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
