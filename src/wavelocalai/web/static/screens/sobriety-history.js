// Sobriété, section « Historique » (story 5.2, UX-DR13, UX-DR14, UX-DR15, UX-DR26, AD-13, AD-20) :
// les émissions de chaque session close, lues sur `GET /api/carbon/history?window=7d|30d|all`.
//
// - Segments « 7 jours · 30 jours · Tout » (7 jours par défaut) et « Graphique · Tableau »
//   (Graphique par défaut, Tableau sous 640 px, D-39). Le choix tient pour la session de la page.
// - Graphique : `wl-chart-svg` en barres, une par session, début en abscisse, mg en ordonnée ; une
//   session sans mesure garde sa place, marquée « non mesuré », sans barre (aucune donnée tracée
//   entre deux mesures). « Voir le tableau » mène au même contenu en `wl-data-table`, triable au
//   clavier. Une seule unité, le milligramme, jamais mélangée avec le g de la section « session ».
// - Le serveur donne les totaux, l'écran les met en forme (`core/format.js`) : aucun calcul de
//   métrique ici (AD-20). La session en cours n'y figure qu'une fois close : une phrase le dit sous
//   le graphique (D-37).
// - Lecture : après le repère `shell-ready` (AD-15), à chaque changement de période, de réponse
//   (`carbon_updated` : un run actif pendant une remise à zéro finit dans sa session close) et de
//   remise à zéro ; jamais en boucle. Une réponse tardive d'une lecture périmée ne touche à rien.
//   Sans session sur la période, une seule lecture de plus sur `all` dit si des sessions plus
//   anciennes existent.

import { api } from "../core/api.js";
import { element } from "../core/dom.js";
import { formatCo2, formatDateTime, formatInteger, formatShortDateTime } from "../core/format.js";
import { t } from "../core/i18n.js";
import { shellReady } from "../core/shell-ready.js";
import { segments } from "../components/segments.js";
import "../components/wl-chart-svg.js";
import "../components/wl-data-table.js";

const NARROW = "(max-width: 639.98px)";
const WINDOWS = ["7d", "30d", "all"];

// Les choix tiennent pour la session de la page (EXPERIENCE.md, « Segments »).
let chosenWindow = "7d";
let chosenView = null; // « chart » ou « table » ; sinon celui que la largeur propose

const mg = (value) => formatCo2(value, { unit: "mg" });
const total = (value) => (value === null ? t("sobriety.history.not_measured") : mg(value));

function timeCell(iso) {
  const node = element("time", "", formatDateTime(iso));
  node.dateTime = iso;
  return node;
}

function tableColumns() {
  const numeric = (key, label, value, cell) => ({ key, label: t(`sobriety.history.col_${label}`), sortable: true, numeric: true, value, cell });
  return [
    { key: "start", label: t("sobriety.history.col_start"), sortable: true, value: (s) => Date.parse(s.started_at), cell: (s) => timeCell(s.started_at) },
    { key: "end", label: t("sobriety.history.col_end"), sortable: true, value: (s) => Date.parse(s.ended_at), cell: (s) => timeCell(s.ended_at) },
    numeric("total", "total", (s) => s.total_mg, (s) => total(s.total_mg)),
    numeric("local", "local", (s) => s.local_mg, (s) => (s.local_mg === 0 ? t("sobriety.history.no_local") : total(s.local_mg))),
    numeric("cloud", "cloud", (s) => s.cloud_mg, (s) => (s.cloud_mg === 0 ? t("sobriety.history.no_cloud") : total(s.cloud_mg))),
    numeric("unmeasurable", "unmeasurable", (s) => s.unmeasurable_runs, (s) => formatInteger(s.unmeasurable_runs)),
  ];
}

export function buildHistory() {
  const title = element("h2", "section-label", t("sobriety.history.title"));
  title.id = "sob-history-title";

  const windowSegments = segments({
    label: t("sobriety.history.window_label"),
    options: WINDOWS.map((value) => ({ value, label: t(`sobriety.history.window_${value}`) })),
    value: chosenWindow,
    onChange: (value) => {
      chosenWindow = value;
      data = null;
      draw();
      read();
    },
  });
  const narrow = window.matchMedia(NARROW);
  chosenView ??= narrow.matches ? "table" : "chart"; // D-39 : Tableau par défaut sous 640 px
  const viewSegments = segments({
    label: t("sobriety.history.view_label"),
    options: [
      { value: "chart", label: t("sobriety.history.view_chart") },
      { value: "table", label: t("sobriety.history.view_table") },
    ],
    value: chosenView,
    onChange: (value) => {
      chosenView = value;
      draw();
    },
  });
  const controls = element("div", "sob-controls");
  controls.append(windowSegments.root, viewSegments.root);

  const skeleton = element("span", "sob-skeleton");
  skeleton.append(element("span", "sr-only", t("sobriety.history.loading")));
  const body = element("div", "sob-history-body");
  const note = element("p", "help sob-history-note", t("sobriety.history.current_note"));
  const box = element("div", "sob-history");
  box.append(body, note);
  const section = element("section", "sob-section");
  section.setAttribute("aria-labelledby", title.id);
  section.append(title, controls, box);

  let chartEl = null;
  let tableEl = null;
  let data = null; // { sessions, older } de la période choisie, ou null tant qu'elle n'est pas lue
  let failed = false;
  let alive = true;
  let ticket = 0;

  function notice(text) {
    const node = element("p", "sob-empty");
    node.textContent = text;
    return node;
  }

  function failure() {
    const retry = element("button", "btn", t("sobriety.history.retry"));
    retry.type = "button";
    retry.addEventListener("click", () => {
      failed = false;
      draw();
      read();
    });
    const wrap = element("div", "sob-history-failed");
    wrap.append(notice(t("sobriety.history.failed")), retry);
    return wrap;
  }

  function drawChart(sessions) {
    chartEl ??= document.createElement("wl-chart-svg");
    const bars = sessions.map((session) => ({
      label: formatShortDateTime(session.started_at),
      value: session.total_mg,
      name: t("sobriety.history.chart_bar", { start: formatDateTime(session.started_at), total: total(session.total_mg) }),
    }));
    chartEl.chart = {
      title: t("sobriety.history.chart_title"),
      desc: t("sobriety.history.chart_desc", { sessions: bars.map((bar) => bar.name).join(" ") }),
      bars,
      unmeasured: t("sobriety.history.unmeasured"),
      xAxis: { label: t("sobriety.history.axis_x") },
      yAxis: { label: t("sobriety.history.axis_y") },
      note: t("sobriety.history.unit_note"),
      seeTable: {
        label: t("sobriety.history.see_table"),
        onClick: () => {
          viewSegments.select("table");
          tableEl?.querySelector(".wl-table-wrap")?.focus();
        },
      },
      missing: null,
    };
    return chartEl;
  }

  function drawTable(sessions) {
    if (!tableEl) {
      tableEl = document.createElement("wl-data-table");
      tableEl.caption = t("sobriety.history.table_caption");
      tableEl.columns = tableColumns();
      tableEl.sort = { key: "start", dir: "desc" }; // la plus récente d'abord
    }
    tableEl.rows = sessions;
    return tableEl;
  }

  function draw() {
    box.setAttribute("aria-busy", String(data === null && !failed));
    note.hidden = data === null;
    let view;
    if (failed) view = failure();
    else if (data === null) view = skeleton;
    else if (data.sessions.length === 0 && data.older) view = notice(t("sobriety.history.empty_window"));
    else if (data.sessions.length === 0) view = notice(t("sobriety.history.empty"));
    else view = chosenView === "table" ? drawTable(data.sessions) : drawChart(data.sessions);
    if (body.firstChild !== view || body.childNodes.length !== 1) body.replaceChildren(view);
    if (viewSegments.value !== chosenView) viewSegments.select(chosenView, { silent: true });
    // Sans session, aucun choix d'affichage à faire.
    viewSegments.root.hidden = data !== null && data.sessions.length === 0;
  }

  async function read() {
    const mine = ++ticket;
    const wanted = chosenWindow;
    await shellReady();
    if (!alive || mine !== ticket) return;
    try {
      const { sessions } = await api.carbonHistory(wanted);
      let older = false;
      if (sessions.length === 0 && wanted !== "all") {
        try {
          older = (await api.carbonHistory("all")).sessions.length > 0;
        } catch {
          older = false; // la phrase de l'historique vide dit déjà ce qu'il faut
        }
      }
      if (!alive || mine !== ticket) return;
      data = { sessions, older };
      failed = false;
    } catch {
      if (!alive || mine !== ticket) return;
      failed = true;
      data = null;
    }
    draw();
  }

  draw();
  return {
    section,
    // Premier chargement, après `shell-ready`.
    start: read,
    // Une remise à zéro, une réponse de plus ou le retour de l'écran : l'historique est relu.
    refresh: read,
    dispose() {
      alive = false;
    },
  };
}
