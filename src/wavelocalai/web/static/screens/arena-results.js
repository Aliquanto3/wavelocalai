// Résultats de l'Arène (story 3.4, UX-DR13, UX-DR14, AD-10, AD-20) : le classement, puis la matrice
// qualité/débit/CO2 et son tableau. Ils se construisent au fil des résultats (chaque `judge_score`,
// `metrics` et `lane_status`, jamais à chaque token) et se figent à `run_ended`.
//
//   const results = resultsView(uid, lanesEl);   // `lanesEl` : le conteneur des `wl-arena-lane`
//   results.el  results.end(state, runId)  results.reset()
//
// La vue ne garde aucune donnée : elle relit les colonnes (statut, note, mesures) à chaque
// changement annoncé (`wl-lane-change`, regroupés par image). Rouvrir une comparaison terminée par son
// adresse rejoue le flux, donc remplit les colonnes et ce classement de la même façon (AD-5).
//
// - Classement : lanes notées par note décroissante (rang à égalité), avec badge d'origine, note,
//   débit et CO2 ; « non évalué » est listé sous elles avec sa raison, sans rang (jamais 0).
// - Verdict local/cloud (story 3.5, `arena-verdict.js`) : lu dans l'instantané du run à `run_ended`
//   d'une comparaison terminée normalement, jamais calculé ici.
// - Matrice (segments « Matrice · Tableau », Matrice par défaut, D-14) : `wl-chart-svg` ; le tableau
//   (`wl-data-table`) est derrière « Voir le tableau » ou le segment « Tableau ». Une seule unité de
//   CO2 pour toute la comparaison.

import { element } from "../core/dom.js";
import { t } from "../core/i18n.js";
import { segments } from "../components/segments.js";
import "../components/wl-badge.js";
import "../components/wl-chart-svg.js";
import "../components/wl-data-table.js";
import { verdictView } from "./arena-verdict.js";
import {
  co2GroupOf,
  co2Text,
  isScored,
  loadText,
  notEvaluatedCell,
  notEvaluatedLine,
  rankLanes,
  rateText,
  scoreText,
  SETTLED,
  splitPlotted,
  splitUnscored,
  totalText,
} from "./arena-results-data.js";

const NBSP = " ";
const PARTIAL = new Set(["cancelled", "interrupted", "error"]);
let chosenSegment = "matrix"; // le choix tient pour la session de la page

function badge(origin) {
  const node = document.createElement("wl-badge");
  node.setAttribute("kind", ["local", "cloud"].includes(origin) ? origin : "unknown");
  return node;
}

const fact = (label, value) => {
  const node = element("span", "arena-fact");
  node.append(element("span", "arena-fact-label", label), element("span", "arena-fact-value", value));
  return node;
};

export function resultsView(uid, lanesEl) {
  const el = element("section", "arena-results");
  el.hidden = true;
  const rankingTitle = element("h2", "arena-results-title", t("arena.results.title"));
  rankingTitle.id = `${uid}-ranking-title`;
  const help = element("p", "help");
  const partial = element("p", "arena-results-partial");
  const ranking = element("div", "arena-ranking");
  const rankingBox = element("section", "arena-results-block");
  rankingBox.setAttribute("aria-labelledby", rankingTitle.id);
  rankingBox.append(rankingTitle, help, partial, ranking);

  const chartTitle = element("h2", "arena-results-title", t("arena.chart.title"));
  chartTitle.id = `${uid}-chart-title`;
  const body = element("div", "arena-chart-body");
  const chartBox = element("section", "arena-results-block");
  chartBox.setAttribute("aria-labelledby", chartTitle.id);
  const defs = element("details", "arena-chart-defs");
  defs.append(
    element("summary", "", t("arena.chart.defs_title")),
    ...["score", "rate", "load", "co2"].map((key) => element("p", "help", t(`arena.chart.def_${key}`))),
  );
  const seg = segments({
    label: t("arena.chart.segment_label"),
    options: [
      { value: "matrix", label: t("arena.chart.matrix") },
      { value: "table", label: t("arena.chart.table") },
    ],
    value: chosenSegment,
    onChange: (value) => {
      chosenSegment = value;
      draw();
    },
  });
  chartBox.append(chartTitle, seg.root, body, defs);
  const verdict = verdictView(uid, (tag) => lanes().find((lane) => lane.tag === tag)?.name);
  el.append(rankingBox, chartBox, verdict.el);

  let ended = false;
  let finalState = null;
  let group = null; // l'unité commune du CO2, lue par les cellules du tableau
  let frame = 0;
  let chartEl = null;
  let tableEl = null;
  const emptyEl = element("p", "help arena-chart-empty");

  const lanes = () =>
    [...lanesEl.querySelectorAll("wl-arena-lane")].map((lane) => ({
      tag: lane.tag,
      name: lane.name,
      origin: lane.origin,
      status: lane.status,
      score: lane.score,
      result: lane.result,
    }));

  // --- Classement ----------------------------------------------------------------------------
  function rankItem({ lane, rank, tied }) {
    const item = element("li", "arena-rank-item");
    item.dataset.tag = lane.tag;
    item.dataset.rank = String(rank);
    const number = element("span", "arena-rank-n");
    number.append(element("span", "sr-only", `${t("arena.results.rank")}${NBSP}`), String(rank));
    const who = element("span", "arena-rank-who");
    who.append(element("strong", "arena-rank-name", lane.name), badge(lane.origin));
    if (tied) who.append(element("span", "arena-rank-tie", t("arena.results.tie")));
    const facts = element("span", "arena-rank-facts");
    facts.append(
      fact(t("arena.results.fact_score"), scoreText(lane)),
      fact(t("arena.results.fact_rate"), rateText(lane, ended)),
      fact(t("arena.results.fact_co2"), co2Text(lane, group, ended)),
    );
    item.append(number, who, facts);
    return item;
  }

  function unscoredItem(lane) {
    const item = element("li", "arena-unranked-item");
    item.dataset.tag = lane.tag;
    item.append(element("strong", "", lane.name), badge(lane.origin), element("span", "arena-unranked-reason", notEvaluatedLine(lane)));
    return item;
  }

  function drawRanking(all) {
    const ranked = rankLanes(all);
    const { settled, pending } = splitUnscored(all, ended);
    help.textContent = t(ended ? "arena.results.help_frozen" : "arena.results.help_live");
    partial.hidden = !(ended && PARTIAL.has(finalState));
    if (!partial.hidden) partial.textContent = t(`arena.results.partial_${finalState}`);
    const children = [];
    if (ranked.length) {
      const list = element("ol", "arena-rank");
      list.append(...ranked.map(rankItem));
      children.push(list);
    } else {
      children.push(element("p", "help arena-rank-none", t("arena.results.none_yet")));
    }
    if (pending.length) {
      const key = pending.length === 1 ? "arena.results.pending_one" : "arena.results.pending_many";
      children.push(element("p", "help arena-rank-pending", t(key, { count: pending.length })));
    }
    if (settled.length) {
      const list = element("ul", "arena-unranked");
      list.setAttribute("aria-label", t("arena.results.unranked"));
      list.append(...settled.map(unscoredItem));
      children.push(element("h3", "arena-unranked-title", t("arena.results.unranked")), list);
    }
    ranking.replaceChildren(...children);
    rankingBox.dataset.frozen = String(ended);
  }

  // --- Matrice et tableau --------------------------------------------------------------------
  function drawChart(all) {
    const { plotted, missing } = splitPlotted(all);
    if (!plotted.length) {
      emptyEl.textContent = t(ended || missing.some((lane) => lane.result) ? "arena.chart.nothing_placed" : "arena.chart.empty");
      return emptyEl;
    }
    chartEl ??= document.createElement("wl-chart-svg");
    const points = plotted.map((lane) => ({ name: lane.name, x: lane.result.tps, y: lane.score.score, mg: lane.result.co2?.mg ?? null }));
    const described = plotted
      .map((lane) =>
        t("arena.chart.point", { name: lane.name, score: scoreText(lane), rate: rateText(lane, ended), co2: co2Text(lane, group, ended) }),
      )
      .join(" ");
    chartEl.chart = {
      title: t("arena.chart.svg_title"),
      desc: t("arena.chart.svg_desc", { points: described }),
      points,
      xAxis: { label: t("arena.chart.x_axis") },
      yAxis: { label: t("arena.chart.y_axis"), max: 100, ticks: [0, 20, 40, 60, 80, 100] },
      size: {
        title: t("arena.chart.size_legend"),
        format: (mg) => group.format(mg),
        unmeasurable: t("arena.chart.size_unmeasurable"),
        note: t("arena.chart.same_unit", { unit: group.unit }),
      },
      seeTable: {
        label: t("arena.chart.see_table"),
        onClick: () => {
          seg.select("table");
          tableEl?.querySelector(".wl-table-wrap")?.focus();
        },
      },
      missing: missing.length ? t("arena.chart.not_plotted", { names: missing.map((lane) => lane.name).join(", ") }) : null,
    };
    return chartEl;
  }

  const numeric = (key, label, value, cell) => ({ key, label, sortable: true, numeric: true, value, cell });

  function tableColumns() {
    return [
      { key: "name", label: t("arena.chart.col_model"), sortable: true, value: (lane) => lane.name },
      { key: "origin", label: t("arena.chart.col_origin"), cell: (lane) => badge(lane.origin) },
      numeric("score", t("arena.chart.col_score"), (lane) => (isScored(lane) ? lane.score.score : null), (lane) =>
        isScored(lane) ? scoreText(lane) : SETTLED.has(lane.status) || ended ? notEvaluatedCell(lane) : t("arena.results.in_progress"),
      ),
      numeric("rate", t("arena.chart.col_rate"), (lane) => lane.result?.tps ?? null, (lane) => rateText(lane, ended)),
      numeric("co2", t("arena.chart.col_co2"), (lane) => lane.result?.co2?.mg ?? null, (lane) => co2Text(lane, group, ended)),
      numeric("load", t("arena.chart.col_load"), (lane) => lane.result?.load_s ?? null, (lane) => loadText(lane, ended)),
      numeric("total", t("arena.chart.col_total"), (lane) => lane.result?.total_s ?? null, (lane) => totalText(lane, ended)),
    ];
  }

  function drawTable(all) {
    if (!tableEl) {
      tableEl = document.createElement("wl-data-table");
      tableEl.caption = t("arena.chart.caption");
      tableEl.columns = tableColumns();
    }
    // Les lignes dans l'ordre du classement : notées d'abord, puis les autres (ordre de lancement).
    const ranked = rankLanes(all).map(({ lane }) => lane);
    tableEl.rows = [...ranked, ...all.filter((lane) => !ranked.includes(lane))];
    return tableEl;
  }

  function draw() {
    const all = lanes();
    const started = all.some((lane) => lane.result || lane.score || SETTLED.has(lane.status));
    el.hidden = !started;
    if (!started) return;
    group = co2GroupOf(all);
    drawRanking(all);
    const view = chosenSegment === "table" ? drawTable(all) : drawChart(all);
    if (body.firstChild !== view) body.replaceChildren(view);
    if (chosenSegment !== seg.value) seg.select(chosenSegment, { silent: true });
  }

  // Après `run_ended`, le classement est figé : un changement tardif d'une colonne ne le refait pas.
  function schedule() {
    if (!frame && !ended) {
      frame = requestAnimationFrame(() => {
        frame = 0;
        draw();
      });
    }
  }

  lanesEl.addEventListener("wl-lane-change", schedule);
  return {
    el,
    // `run_ended` : le classement se fige (état final : ok, cancelled, error, interrupted) et le
    // verdict d'une comparaison finie normalement est lu dans l'instantané du run.
    end(state, runId) {
      ended = true;
      finalState = state;
      cancelAnimationFrame(frame);
      frame = 0;
      draw();
      if (state === "ok" && runId) verdict.load(runId);
    },
    reset() {
      verdict.reset();
      ended = false;
      finalState = null;
      cancelAnimationFrame(frame);
      frame = 0;
      el.hidden = true;
      ranking.replaceChildren();
      body.replaceChildren();
      chartEl = null;
      tableEl = null;
    },
  };
}
