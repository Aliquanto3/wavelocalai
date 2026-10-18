// Références, `#/arene/references` (UX-DR13, UX-DR17, UX-DR24, UX-DR25, story 5.8, AD-22) : quel
// modèle pour quel usage, lu des résultats publiés du banc (`qb.results/1`), jamais recalculé.
//
// - Une carte par usage publié : groupe des meilleurs (intervalle, aucun rang dans un groupe à
//   égalité), débit sur la machine de référence, marque « installé » ou « autre version » pour les
//   modèles du poste ; un tableau équivalent (segments « Cartes · Tableau »).
// - Un `null` s'affiche « inconnu » ou « non classé », jamais 0 ; les fractions de 0 à 1 s'affichent en
//   pourcentage ; l'énergie n'est montrée que si `status = "measured"`.
// - Références indisponibles (fichier absent, format inconnu, aucun usage) : la raison s'affiche,
//   jamais de carte vide. Premier chargement : squelettes dans les cartes.

import { element, icon } from "../core/dom.js";
import { formatDate, formatInteger, formatNumber, formatPercent, formatRate } from "../core/format.js";
import { t } from "../core/i18n.js";
import { setMaquette, store } from "../core/store.js";
import { dataTable } from "../components/data-table.js";
import { handOff } from "../core/handoff.js";
import { segments } from "../components/segments.js";

let view = null;
let forced = null; // état imposé par un scénario : loading | absent | schema | empty

function waitUntil(condition, timeoutMs = 20000) {
  return new Promise((resolve, reject) => {
    const started = performance.now();
    const check = () => {
      if (condition()) return resolve();
      if (performance.now() - started > timeoutMs) return reject(new Error("Scénario : état jamais atteint"));
      setTimeout(check, 30);
    };
    check();
  });
}

export async function mount(host, ctx) {
  const data = await ctx.data("references.json");
  const state = { segment: "cards", phase: "loading", availability: "ok" };
  let timer = null;

  const intro = element("div", "rf-intro");
  const noticeBox = element("div", "rf-notices");
  const content = element("div", "rf-content");
  host.replaceChildren(element("h1", "", ctx.route.title), ctx.tabs(), element("p", "lead", t("references.lead")), intro, noticeBox, content);

  const availability = () => {
    if (forced === "absent") return "absent";
    if (forced === "schema") return "schema";
    if (forced === "empty" || !data.usages.length) return "empty";
    if (data.schema !== "qb.results/1") return "schema";
    return "ok";
  };

  const installedMarks = () => {
    const { noLocalModel, ollamaDown } = store.get().maquette;
    return !noLocalModel && !ollamaDown;
  };

  const percent = (fraction) => formatPercent(fraction * 100);

  function mark(kind) {
    const span = element("span", "rf-mark");
    span.dataset.kind = kind;
    span.append(icon(kind === "installed" ? "check" : "warning"), element("span", "", t(`references.mark.${kind}`)));
    return span;
  }

  function rateText(entry) {
    return entry.tps_ref == null ? t("references.card.rate_unknown") : t("references.card.rate", { rate: formatRate(entry.tps_ref) });
  }

  function energyText(entry) {
    // `energy` ne s'affiche que si l'état dit « measured » (AD-22).
    if (entry.energy?.status !== "measured") return null;
    return t("references.card.energy", { value: formatNumber(entry.energy.wh_per_100) });
  }

  function modelOf(entry) {
    return data.models[entry.model];
  }

  // « Comparer ces modèles » : l'Arène s'ouvre sur les modèles installés du groupe (décision 19).
  function compareAction(usage, best) {
    const tags = installedMarks() ? best.filter((entry) => modelOf(entry).installed).map((entry) => entry.model) : [];
    const line = element("p", "rf-compare");
    const button = element("button", "btn rf-compare-button", "");
    button.type = "button";
    button.append(icon("swords"), element("span", "", t("references.card.compare")));
    button.dataset.usage = usage.id;
    line.append(button);
    if (tags.length === 0) {
      const reason = element("span", "help", t(installedMarks() ? "references.card.compare_none" : "references.card.compare_unknown"));
      reason.id = `rf-compare-reason-${usage.id}`;
      button.disabled = true;
      button.setAttribute("aria-describedby", reason.id);
      line.append(reason);
    } else {
      button.addEventListener("click", () => {
        handOff("arena-models", tags);
        ctx.navigate("/arene/comparer");
      });
    }
    return line;
  }

  function buildCard(usage) {
    const card = element("article", "rf-card");
    card.dataset.usage = usage.id;
    const best = usage.results.filter((entry) => entry.group === "best");
    const ranked = usage.results.filter((entry) => entry.score != null);
    const unranked = usage.results.filter((entry) => entry.score == null);
    const group = element("ul", "rf-group");
    for (const entry of [...best].sort((a, b) => modelOf(a).name.localeCompare(modelOf(b).name, "fr-FR"))) {
      const model = modelOf(entry);
      const item = element("li", "rf-model");
      const head = element("div", "rf-model-head");
      head.append(element("strong", "rf-model-name", model.name));
      if (installedMarks() && model.installed) head.append(mark(model.installed));
      const facts = element("p", "rf-facts");
      facts.append(
        element("span", "rf-score", percent(entry.score)),
        element("span", "rf-interval", t("references.card.interval", { low: formatInteger(entry.interval[0] * 100), high: percent(entry.interval[1]) })),
      );
      const lines = [head, facts, element("p", "rf-line", rateText(entry))];
      const energy = energyText(entry);
      if (energy) lines.push(element("p", "rf-line", energy));
      item.append(...lines);
      group.append(item);
    }
    const title = element("p", "rf-group-title", t(best.length > 1 ? "references.card.best_group" : "references.card.best_one"));
    const heading = element("h3", "rf-card-title", usage.label);
    const tie = element("p", "help", best.length > 1 ? t("references.card.tie") : t("references.card.alone"));
    const footer = [];
    const others = ranked.length - best.length;
    if (others > 0) {
      const line = element("p", "rf-footer");
      const button = element("button", "btn rf-see-table", t("references.card.see_table"));
      button.type = "button";
      button.addEventListener("click", () => {
        picker.select("table");
        content.querySelector(".rf-table-wrap")?.focus();
      });
      line.append(element("span", "", t("references.card.others", { count: formatInteger(others) })), button);
      footer.push(line);
    }
    if (unranked.length) footer.push(element("p", "help", t("references.card.unranked", { names: unranked.map((entry) => modelOf(entry).name).join(", ") })));
    card.append(heading, element("p", "help", usage.description), element("p", "help", t("references.card.measure", { metric: usage.metric, count: formatInteger(usage.questions) })), title, group, tie, compareAction(usage, best), ...footer);
    return card;
  }

  function buildTable() {
    const rows = data.usages.flatMap((usage) => usage.results.map((entry) => ({ usage, entry, model: modelOf(entry) })));
    const groupText = (entry) => t(`references.group.${entry.group ?? "none"}`);
    return dataTable({
      caption: t("references.caption"),
      className: "rf",
      columns: [
        { key: "usage", label: t("references.col.usage"), value: (row) => row.usage.label, cell: (row) => row.usage.label },
        { key: "model", label: t("references.col.model"), header: true, value: (row) => row.model.name, cell: (row) => row.model.name },
        { key: "group", label: t("references.col.group"), cell: (row) => groupText(row.entry) },
        { key: "score", label: t("references.col.score"), value: (row) => row.entry.score, cell: (row) => (row.entry.score == null ? t("references.unknown_score") : percent(row.entry.score)) },
        { key: "interval", label: t("references.col.interval"), cell: (row) => (row.entry.interval ? t("references.card.interval", { low: formatInteger(row.entry.interval[0] * 100), high: percent(row.entry.interval[1]) }) : t("references.unknown_score")) },
        { key: "rate", label: t("references.col.rate"), value: (row) => row.entry.tps_ref, cell: (row) => (row.entry.tps_ref == null ? t("format.unknown") : formatRate(row.entry.tps_ref)) },
        { key: "energy", label: t("references.col.energy"), cell: (row) => (energyText(row.entry) ? t("references.card.energy", { value: formatNumber(row.entry.energy.wh_per_100) }) : t("references.energy_none")) },
        {
          key: "here",
          label: t("references.col.here"),
          cell: (row) => (installedMarks() && row.model.installed ? mark(row.model.installed) : installedMarks() ? t("references.here_none") : t("format.unknown")),
        },
      ],
      rows,
    });
  }

  const picker = segments({
    label: t("references.segment_label"),
    options: [
      { value: "cards", label: t("references.cards") },
      { value: "table", label: t("references.table") },
    ],
    value: state.segment,
    className: "rf",
    onChange: (value) => {
      state.segment = value;
      renderContent();
      ctx.announce(t(value === "table" ? "references.announce_table" : "references.announce_cards"));
    },
  });

  function renderIntro() {
    const machine = data.reference_machine;
    const text = t("references.source", {
      source: data.source,
      campaign: data.campaign,
      date: formatDate(data.published),
      machine: machine.label,
      memory: `${formatInteger(machine.memory_gb)} Go`,
      gpu: machine.gpu === "aucun" ? t("references.gpu_none") : machine.gpu,
    });
    intro.replaceChildren(element("p", "help rf-source", text));
    intro.hidden = state.availability !== "ok" || state.phase !== "ready";
  }

  function renderContent() {
    noticeBox.replaceChildren();
    if (state.phase === "loading") {
      content.replaceChildren(ctx.states.loading({ lines: 4, slowAfterMs: 2500, slowText: t("references.loading_slow") }));
      renderIntro();
      return;
    }
    renderIntro();
    if (state.availability !== "ok") {
      content.replaceChildren(
        ctx.states.emptyState({
          title: t("references.unavailable.title"),
          text: t(`references.unavailable.${state.availability}`, { schema: "qb.results/2" }),
          level: 2,
          iconName: "info",
        }),
      );
      return;
    }
    if (store.get().maquette.ollamaDown) noticeBox.append(ctx.states.notice(t("references.ollama_down"), { tone: "warning" }));
    const heading = element("h2", "", t("references.title"));
    const body = state.segment === "table" ? buildTable() : (() => {
      const grid = element("div", "rf-grid");
      grid.append(...data.usages.map(buildCard));
      return grid;
    })();
    const legend = element("dl", "rf-legend");
    if (installedMarks()) {
      for (const kind of ["installed", "other_version"]) {
        const row = element("div", "rf-legend-row");
        row.append(element("dt", "", t(`references.mark.${kind}`)), element("dd", "", t(`references.mark_help.${kind}`)));
        legend.append(row);
      }
    }
    content.replaceChildren(heading, picker.root, body, ...(legend.children.length ? [legend] : []));
  }

  function show() {
    state.availability = availability();
    state.phase = forced === "loading" ? "loading" : "ready";
    renderContent();
  }

  // Premier chargement : squelettes, puis les cartes (lecture du fichier, budget de 300 ms côté serveur).
  renderContent();
  timer = setTimeout(show, 600 / (store.get().maquette.speed || 1));

  const unsubscribe = store.select(
    (current) => `${current.maquette.noLocalModel}|${current.maquette.ollamaDown}`,
    () => {
      if (state.phase === "ready") renderContent();
    },
  );

  view = {
    host,
    get phase() {
      return state.phase;
    },
    get availability() {
      return state.availability;
    },
    get segment() {
      return state.segment;
    },
    showSegment: (value) => picker.select(value),
    sortBy(key) {
      content.querySelector(`.rf-sort[data-key="${key}"]`)?.click();
    },
  };

  return () => {
    view = null;
    clearTimeout(timer);
    unsubscribe();
  };
}

// --- Scénarios ----------------------------------------------------------------------------------

// Repart de l'état d'ouverture ; `state` impose un état (absent, schema, empty, loading) avant lecture.
async function fresh(ctx, state = null, setup = () => {}) {
  forced = null;
  await ctx.reset();
  setup();
  forced = state;
  await ctx.remount();
  await waitUntil(() => view !== null);
  if (state !== "loading") await waitUntil(() => view !== null && view.phase === "ready");
}

export const scenarios = [
  { id: "cartes", label: "Une carte par usage : groupe des meilleurs, intervalle, débit, marque « installé »", run: (ctx) => fresh(ctx) },
  {
    id: "tableau",
    label: "Le même contenu en tableau",
    async run(ctx) {
      await fresh(ctx);
      view.showSegment("table");
    },
  },
  {
    id: "tableau-trie",
    label: "Tableau trié au clavier par réussite (décroissante)",
    async run(ctx) {
      await fresh(ctx);
      view.showSegment("table");
      view.sortBy("score");
      view.sortBy("score");
    },
  },
  {
    id: "comparer-ces-modeles",
    label: "« Comparer ces modèles » : l'Arène s'ouvre présélectionnée sur les modèles installés du groupe",
    async run(ctx) {
      await fresh(ctx);
      view.host.querySelector(".rf-compare-button:not(:disabled)").click();
      await waitUntil(() => document.querySelector('section.screen[data-screen="arene"]:not([hidden]) wl-model-picker') !== null);
    },
  },
  { id: "chargement", label: "Premier chargement : squelettes dans les cartes", run: (ctx) => fresh(ctx, "loading") },
  { id: "indisponible-fichier-absent", label: "Fichier de résultats absent : raison affichée, aucune carte vide", run: (ctx) => fresh(ctx, "absent") },
  { id: "indisponible-format", label: "Format de résultats inconnu (autre version de schéma) : raison affichée", run: (ctx) => fresh(ctx, "schema") },
  { id: "aucun-usage-publie", label: "Fichier valide mais aucun usage publié : raison affichée", run: (ctx) => fresh(ctx, "empty") },
  { id: "aucun-modele-installe", label: "Aucun modèle local installé : aucune marque « installé »", run: (ctx) => fresh(ctx, null, () => setMaquette({ noLocalModel: true })) },
  {
    id: "ollama-arrete",
    label: "Ollama arrêté : les références restent lisibles, les marques ne sont pas vérifiées",
    run: (ctx) => fresh(ctx, null, () => ctx.system.setOllamaDown(true)),
  },
];
