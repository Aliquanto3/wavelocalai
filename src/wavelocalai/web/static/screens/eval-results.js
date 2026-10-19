// Résultats de l'évaluation (story 7.3, UX-DR13, UX-DR14, UX-DR29, AD-20) : le tableau (Modèle,
// Fidélité, Pertinence, Précision du contexte, Débit, CO2 ; aucune colonne « Global », décision du
// 2026-10-19) et la matrice fidélité × débit (CO2 en taille), derrière les segments « Tableau » (par
// défaut) · « Matrice ». Les cellules se remplissent au fil de `eval_metric` (« en cours » avant leur
// note) ; un score est un bouton qui déplie son détail ; « non évalué » dit sa raison, jamais 0.
//
//   const results = resultsView(uid, { nameOf, originOf, onOpen });
//   results.el  results.render(model)  results.reset()  results.focusScore(lane, metric)
//
// Le front ne calcule aucune note : il pose celles du serveur (`aggregate`, `summary`).

import { element } from "../core/dom.js";
import { co2Group, formatRate, formatScore, plural } from "../core/format.js";
import { t } from "../core/i18n.js";
import { segments } from "../components/segments.js";
import "../components/wl-badge.js";
import "../components/wl-chart-svg.js";
import "../components/wl-data-table.js";
import { METRICS, STOPPED_REASON } from "./eval-model.js";

let chosenSegment = "table"; // le choix tient pour la session de la page

function badge(origin) {
  const node = document.createElement("wl-badge");
  node.setAttribute("kind", ["local", "cloud"].includes(origin) ? origin : "unknown");
  return node;
}

const lower = (text) => (text ? text[0].toLocaleLowerCase("fr-FR") + text.slice(1) : text);

export function resultsView(uid, { nameOf, originOf, onOpen }) {
  const title = element("h2", "eval-results-title", t("evaluation.results.title"));
  title.id = `${uid}-results-title`;
  const partial = element("p", "eval-partial");
  partial.hidden = true;
  const body = element("div", "eval-results-body");
  const seg = segments({
    label: t("evaluation.results.segment_label"),
    options: [
      { value: "table", label: t("evaluation.results.table") },
      { value: "matrix", label: t("evaluation.results.matrix") },
    ],
    value: chosenSegment,
    onChange: (value) => {
      chosenSegment = value;
      if (latest) render(latest);
    },
  });
  const defs = element("details", "eval-defs");
  defs.append(
    element("summary", "", t("evaluation.results.defs_title")),
    ...[...METRICS, "rate", "co2"].map((metric) => {
      const line = element("p", "help");
      line.append(element("strong", "", `${t(`evaluation.results.col_${metric}`)} : `), t(`evaluation.results.def_${metric}`));
      return line;
    }),
    element("p", "help", t("evaluation.results.method")),
  );
  const el = element("section", "eval-results");
  el.setAttribute("aria-labelledby", title.id);
  el.hidden = true;
  el.append(title, partial, seg.root, body, defs);

  let latest = null;
  let openTarget = null; // { lane, metric } du détail ouvert : son bouton porte `aria-expanded`
  let tableEl = null;
  let chartEl = null;
  const emptyEl = element("p", "help eval-matrix-empty");

  const scoreText = (score) => formatScore(score);

  function ofQuestions(aggregate) {
    const parts = [];
    if (aggregate.not_evaluated > 0) parts.push(plural("evaluation.results.not_evaluated_count", aggregate.not_evaluated));
    if (aggregate.pending > 0) parts.push(t("evaluation.results.pending_count", { n: aggregate.pending }));
    const base = plural("evaluation.results.of_questions", aggregate.total, { total: aggregate.total });
    return parts.length ? `${base} (${parts.join(", ")})` : base;
  }

  function reasonOf(model, cell) {
    const reason = cell.reason ?? (model.partial ? STOPPED_REASON : null);
    return t("evaluation.results.not_evaluated", { reason: lower(reason) || t("evaluation.results.reason_unknown") });
  }

  function metricCell(model, lane, metric) {
    const cell = model.cell(lane.tag, metric);
    const box = element("span", "eval-cell");
    if (cell.kind === "score") {
      const score = element("button", "eval-score", scoreText(cell.aggregate.score));
      score.type = "button";
      score.dataset.lane = lane.tag;
      score.dataset.metric = metric;
      const isOpen = openTarget && openTarget.lane === lane.tag && openTarget.metric === metric;
      score.setAttribute("aria-expanded", String(Boolean(isOpen)));
      score.setAttribute(
        "aria-label",
        t("evaluation.results.open_detail", { name: lane.name, metric: t(`evaluation.results.col_${metric}`) }) + ` (${scoreText(cell.aggregate.score)})`,
      );
      score.addEventListener("click", () => onOpen({ lane: lane.tag, metric, trigger: () => focusScore(lane.tag, metric) }));
      box.append(score);
      if (model.isSet) box.append(element("span", "help eval-cell-count", ofQuestions(cell.aggregate)));
    } else if (cell.kind === "unevaluated") {
      box.append(element("span", "eval-unevaluated", reasonOf(model, cell)));
      if (model.isSet && cell.aggregate) box.append(element("span", "help eval-cell-count", ofQuestions(cell.aggregate)));
    } else {
      box.append(element("span", "eval-progress", t("evaluation.results.in_progress")));
    }
    return box;
  }

  function measureTexts(model, rows) {
    const group = co2Group(rows.map((row) => row.measures.co2mg).filter((mg) => typeof mg === "number"));
    const ended = model.ended !== null;
    const none = () => t(ended ? "evaluation.results.not_measured" : "evaluation.results.in_progress");
    // « n sur m » une fois le run fini, quand des réponses n'ont pas de mesure (comptes du serveur).
    const of = (counted) => (ended && counted ? ` (${plural("evaluation.results.measured_of", counted.n, { total: counted.total })})` : "");
    return {
      group,
      rate: (row) => (typeof row.measures.rate === "number" ? formatRate(row.measures.rate) + of(row.measures.rateOf) : none()),
      co2: (row) => {
        if (typeof row.measures.co2mg === "number") {
          const value = group.format(row.measures.co2mg);
          const text = row.measures.co2estimated ? t("components.thread.co2_estimated", { value }) : value;
          return text + of(row.measures.co2Of);
        }
        return row.measures.co2unmeasurable ? t("components.thread.co2_unmeasurable") : none();
      },
    };
  }

  function columns(model, texts) {
    const set = model.isSet;
    const metric = (id) => ({
      key: id,
      label: t(`evaluation.results.col_${id}`),
      sortable: true,
      numeric: true,
      value: (row) => model.cell(row.tag, id).aggregate?.score ?? null,
      cell: (row) => metricCell(model, row, id),
    });
    return [
      {
        key: "name",
        label: t("evaluation.results.col_model"),
        sortable: true,
        value: (row) => row.name,
        cell: (row) => {
          const box = element("span", "eval-model");
          box.append(element("span", "eval-model-name", row.name), badge(row.origin));
          return box;
        },
      },
      ...METRICS.map(metric),
      {
        key: "rate",
        label: t(set ? "evaluation.results.col_rate_set" : "evaluation.results.col_rate"),
        sortable: true,
        numeric: true,
        value: (row) => row.measures.rate,
        cell: (row) => texts.rate(row),
      },
      {
        key: "co2",
        label: t(set ? "evaluation.results.col_co2_set" : "evaluation.results.col_co2"),
        sortable: true,
        numeric: true,
        value: (row) => row.measures.co2mg,
        cell: (row) => texts.co2(row),
      },
    ];
  }

  function drawTable(model, rows, texts) {
    if (!tableEl) {
      tableEl = document.createElement("wl-data-table");
      tableEl.caption = t("evaluation.results.caption");
    }
    tableEl.columns = columns(model, texts); // les cellules lisent le modèle courant
    tableEl.rows = rows;
    return tableEl;
  }

  function drawMatrix(model, rows, texts) {
    const plotted = rows.filter((row) => {
      const cell = model.cell(row.tag, "faithfulness");
      return cell.kind === "score" && typeof row.measures.rate === "number";
    });
    const missing = rows.filter((row) => !plotted.includes(row));
    if (!plotted.length) {
      emptyEl.textContent = t(model.ended ? "evaluation.matrix.nothing_placed" : "evaluation.matrix.empty");
      return emptyEl;
    }
    chartEl ??= document.createElement("wl-chart-svg");
    const score = (row) => model.cell(row.tag, "faithfulness").aggregate.score;
    const points = plotted.map((row) => ({ name: row.name, x: row.measures.rate, y: score(row), mg: row.measures.co2mg }));
    const described = plotted
      .map((row) =>
        t("evaluation.matrix.point", { name: row.name, score: scoreText(score(row)), rate: texts.rate(row), co2: texts.co2(row) }),
      )
      .join(" ");
    chartEl.chart = {
      title: t("evaluation.matrix.svg_title"),
      desc: t("evaluation.matrix.svg_desc", { points: described }),
      points,
      xAxis: { label: t("evaluation.matrix.x_axis") },
      yAxis: { label: t("evaluation.matrix.y_axis"), max: 100, ticks: [0, 20, 40, 60, 80, 100] },
      size: {
        title: t("evaluation.matrix.size_legend"),
        format: (mg) => texts.group.format(mg),
        unmeasurable: t("evaluation.matrix.size_unmeasurable"),
        note: t("evaluation.matrix.same_unit", { unit: texts.group.unit }),
      },
      seeTable: {
        label: t("evaluation.matrix.see_table"),
        onClick: () => {
          seg.select("table");
          tableEl?.querySelector(".wl-table-wrap")?.focus();
        },
      },
      missing: missing.length ? t("evaluation.matrix.not_plotted", { names: missing.map((row) => row.name).join(", ") }) : null,
    };
    return chartEl;
  }

  function focusScore(lane, metric) {
    const buttons = [...el.querySelectorAll(".eval-score")];
    buttons.find((node) => node.dataset.lane === lane && node.dataset.metric === metric)?.focus();
  }

  function render(model) {
    latest = model;
    const rows = model.lanes.map((tag) => ({
      tag,
      name: nameOf(tag),
      origin: originOf(tag),
      measures: model.measures(tag),
    }));
    el.hidden = rows.length === 0;
    if (!rows.length) return;
    const isPartial = model.partial && model.ended !== null;
    title.textContent = t(isPartial ? "evaluation.results.partial_title" : "evaluation.results.title");
    partial.hidden = !isPartial;
    partial.textContent = isPartial ? t("evaluation.results.partial_help") : "";
    const texts = measureTexts(model, rows);
    const active = document.activeElement;
    const keep = active?.classList?.contains("eval-score") ? { ...active.dataset } : null;
    const view = chosenSegment === "matrix" ? drawMatrix(model, rows, texts) : drawTable(model, rows, texts);
    if (body.firstChild !== view) body.replaceChildren(view);
    if (chosenSegment !== seg.value) seg.select(chosenSegment, { silent: true });
    if (keep && document.activeElement !== active) focusScore(keep.lane, keep.metric);
  }

  return {
    el,
    render,
    focusScore,
    // Le détail ouvert ({ lane, metric }, ou null) : son bouton porte `aria-expanded`.
    setOpen(target) {
      openTarget = target;
      if (latest) render(latest);
    },
    reset() {
      latest = null;
      el.hidden = true;
      body.replaceChildren();
      tableEl = null;
      chartEl = null;
    },
  };
}
