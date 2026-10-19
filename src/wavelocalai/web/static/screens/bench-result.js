// Résultat d'un essai du Banc d'essai (story 7.4, UX-DR13, UX-DR17, AD-20) : l'étape du run
// (`wl-run-status` piloté), la réponse en flux, puis, à la fin, le verdict de format en clair, la
// « Sortie mise en forme » et la rangée de mesures (débit D3, CO₂, durée), enfin « Relancer le test »
// et « Modifier le test ». Le front ne valide ni ne mesure rien : verdict, JSON mis en forme et
// mesures viennent de l'instantané du run (`format_verdict`, `metrics`), comme pour un essai rouvert.
//
//   const result = resultView(uid);   result.el  result.status
//   result.show({ phase, text, snapshot, hasSchema })    result.onAction((kind) => …)

import { icon, element } from "../core/dom.js";
import { formatDuration, formatRate } from "../core/format.js";
import { t } from "../core/i18n.js";
import { renderMarkdown } from "../core/markdown.js";
import { co2Metric, metric } from "../components/wl-chat-thread.js";
import "../components/wl-error.js";
import "../components/wl-run-status.js";

export function resultView(uid) {
  const status = document.createElement("wl-run-status");
  status.setAttribute("driven", "");
  const streamTitle = element("h3", "", t("bench.result.answer"));
  streamTitle.id = `${uid}-stream-title`;
  const stream = element("pre", "bc-stream");
  stream.tabIndex = 0;
  stream.setAttribute("aria-labelledby", streamTitle.id);
  const verdictBox = element("div", "bc-verdict");
  const formatted = element("div", "bc-formatted");
  const metrics = element("div", "bc-metrics");
  const actions = element("div", "bc-actions");
  const rerun = element("button", "btn", t("bench.actions.rerun"));
  rerun.type = "button";
  const edit = element("button", "btn", t("bench.actions.edit"));
  edit.type = "button";
  actions.append(rerun, edit);

  const el = element("section", "bc-result");
  el.setAttribute("aria-labelledby", `${uid}-result-title`);
  el.hidden = true;
  const title = element("h2", "", t("bench.result.title"));
  title.id = `${uid}-result-title`;
  el.append(title, status, streamTitle, stream, verdictBox, formatted, metrics, actions);

  function verdictView(verdict, hasSchema) {
    if (!hasSchema) return [element("h3", "", t("bench.verdict.title")), element("p", "help", t("bench.verdict.none"))];
    if (!verdict) return [];
    const line = element("p", "bc-verdict-line");
    line.dataset.ok = String(verdict.ok);
    line.setAttribute("role", "status");
    line.append(icon(verdict.ok ? "check" : "error"), element("span", "", verdict.message));
    return [
      element("h3", "", t("bench.verdict.title")),
      line,
      element("p", "help", t(verdict.forced ? "bench.verdict.forced" : "bench.verdict.asked")),
    ];
  }

  function formattedView({ text, verdict, hasSchema }) {
    if (!text) return [];
    const body = element("div", "bc-formatted-body");
    if (hasSchema && verdict?.formatted) {
      const pre = element("pre", "bc-json", verdict.formatted);
      pre.tabIndex = 0;
      pre.setAttribute("aria-label", t("bench.formatted.title"));
      body.append(pre);
    } else if (hasSchema) {
      const pre = element("pre", "bc-json", text);
      pre.tabIndex = 0;
      pre.setAttribute("aria-label", t("bench.formatted.title"));
      body.append(element("p", "help", t("bench.formatted.raw")), pre);
    } else {
      body.className = "bc-md wl-md";
      body.append(renderMarkdown(text));
    }
    return [element("h3", "", t("bench.formatted.title")), body];
  }

  function metricsView(measures) {
    if (!measures) return [];
    const nodes = [
      metric(t("bench.metric.rate"), formatRate(measures.tps), { help: t("bench.metric.rate_help") }),
      co2Metric(measures.co2),
      metric(t("bench.metric.total"), formatDuration(measures.total_s), { help: t("bench.metric.total_help") }),
    ];
    if (measures.origin !== "cloud") {
      nodes.push(
        metric(t("bench.metric.load"), measures.load_s == null ? t("bench.metric.already") : formatDuration(measures.load_s), {
          help: t("bench.metric.load_help"),
        }),
      );
    }
    return nodes;
  }

  return {
    el,
    status,
    // `phase` : `running` (réponse en flux) ou `done` (verdict, sortie mise en forme, mesures, actions).
    show({ phase, text = "", verdict, hasSchema = false, measures = null, ok = true }) {
      const done = phase === "done";
      el.hidden = phase === "idle";
      if (stream.textContent !== text) stream.textContent = text;
      stream.hidden = !text;
      streamTitle.hidden = !text;
      verdictBox.replaceChildren(...(done && ok ? verdictView(verdict, hasSchema) : []));
      formatted.replaceChildren(...(done && ok ? formattedView({ text, verdict, hasSchema }) : []));
      formatted.hidden = formatted.childElementCount === 0;
      const nodes = done ? metricsView(measures) : [];
      metrics.replaceChildren(...nodes);
      metrics.hidden = nodes.length === 0;
      actions.hidden = !done;
    },
    onAction(handler) {
      rerun.addEventListener("click", () => handler("rerun"));
      edit.addEventListener("click", () => handler("edit"));
    },
  };
}
