// Rendu des références (story 5.8, UX-DR13, UX-DR24, UX-DR25, AD-20, AD-22) : une carte par usage et le
// tableau équivalent. Le front met en forme ce que `GET /api/references` rend et ne décide de rien :
// le groupe des meilleurs, les marques « installé » et les modèles de « Comparer » viennent du serveur.
// Une fraction de 0 à 1 s'affiche en pourcentage, un `null` « inconnu » ou « non classé », jamais 0 ;
// l'énergie n'est rendue que si le serveur l'a donnée (`status = "measured"`). Ni bloc « autres
// modèles mesurés », ni lien vers le tableau du banc, ni légende des marques (décision du 2026-10-19).

import { element, icon } from "../core/dom.js";
import { formatInteger, formatNumber, formatPercent, formatRate, formatUnknown } from "../core/format.js";
import { t } from "../core/i18n.js";
import { openArenaWith } from "./references-compare.js";
import "../components/wl-data-table.js";

const percent = (fraction) => formatPercent(Math.round(fraction * 100));

function intervalText(entry) {
  if (entry.ci_low === null || entry.ci_high === null) return t("references.card.interval_unknown");
  return t("references.card.interval", { low: percent(entry.ci_low), high: percent(entry.ci_high) });
}

function energyText(entry) {
  if (entry.energy_wh_per_1k_tokens === null) return null;
  return t("references.card.energy", {
    value: formatNumber(entry.energy_wh_per_1k_tokens),
    count: formatInteger(1000),
  });
}

function mark(kind) {
  const span = element("span", "ref-mark");
  span.dataset.kind = kind;
  span.append(icon(kind === "installed" ? "check" : "warning"), element("span", "", t(`references.mark.${kind}`)));
  return span;
}

function modelItem(entry) {
  const head = element("div", "ref-model-head");
  head.append(element("strong", "ref-model-name", entry.name));
  if (entry.installed) head.append(mark(entry.installed));
  const facts = element("p", "ref-facts");
  facts.append(
    element("span", "ref-score", t("references.card.score", { value: percent(entry.score) })),
    element("span", "ref-interval", intervalText(entry)),
  );
  const rate = element(
    "p",
    "ref-line",
    entry.decode_tok_s === null
      ? t("references.card.rate_unknown")
      : t("references.card.rate", { rate: formatRate(entry.decode_tok_s) }),
  );
  const item = element("li", "ref-model");
  item.dataset.tag = entry.tag;
  item.append(head, facts, rate);
  const energy = energyText(entry);
  if (energy) item.append(element("p", "ref-line", energy));
  return item;
}

// « Comparer ces modèles » : actif avec les modèles du groupe installés (le serveur les nomme), sinon
// désactivé (`aria-disabled`, il reste focalisable) avec sa raison visible, reliée au bouton.
function compareLine(usage) {
  const line = element("p", "ref-compare");
  const button = element("button", "btn ref-compare-button");
  button.type = "button";
  button.dataset.usage = usage.id;
  button.append(icon("swords"), element("span", "", t("references.card.compare")));
  line.append(button);
  const { tags, reason } = usage.compare;
  if (tags.length === 0) {
    const why = element("span", "help ref-compare-reason", reason ?? "");
    why.id = `ref-compare-reason-${usage.id}`;
    button.setAttribute("aria-disabled", "true");
    button.setAttribute("aria-describedby", why.id);
    line.append(why);
  } else {
    button.addEventListener("click", () => openArenaWith(tags));
  }
  return line;
}

function card(usage) {
  const article = element("article", "ref-card");
  article.dataset.usage = usage.id;
  const group = usage.entries.filter((entry) => entry.group === "best");
  const list = element("ul", "ref-group");
  list.append(...group.map(modelItem));
  const alone = usage.best_count === 1;
  article.append(
    element("h3", "ref-card-title", usage.label),
    element("p", "help", usage.description),
    element("p", "help ref-measure", usage.measure),
    element("p", "ref-group-title", t(alone ? "references.card.best_one" : "references.card.best_group")),
    list,
    element("p", "help", t(alone ? "references.card.alone" : "references.card.tie")),
    compareLine(usage),
  );
  return article;
}

export function cardsView(references) {
  const grid = element("div", "ref-grid");
  grid.append(...references.usages.map(card));
  return grid;
}

function groupText(entry, usage) {
  if (entry.group === "best") return t(usage.best_count === 1 ? "references.group.best_one" : "references.group.best");
  return t(entry.group === "other" ? "references.group.other" : "references.group.none");
}

export function tableView(references) {
  const rows = references.usages.flatMap((usage) => usage.entries.map((entry) => ({ usage, entry })));
  const table = document.createElement("wl-data-table");
  table.caption = t("references.caption");
  table.columns = [
    { key: "model", label: t("references.col.model"), sortable: true, value: (row) => row.entry.name, cell: (row) => row.entry.name },
    { key: "usage", label: t("references.col.usage"), sortable: true, value: (row) => row.usage.label, cell: (row) => row.usage.label },
    { key: "group", label: t("references.col.group"), cell: (row) => groupText(row.entry, row.usage) },
    {
      key: "score",
      label: t("references.col.score"),
      sortable: true,
      numeric: true,
      value: (row) => row.entry.score,
      cell: (row) => (row.entry.score === null ? t("references.unranked") : percent(row.entry.score)),
    },
    {
      key: "interval",
      label: t("references.col.interval"),
      cell: (row) => (row.entry.score === null ? t("references.unranked") : intervalText(row.entry)),
    },
    {
      key: "rate",
      label: t("references.col.rate"),
      sortable: true,
      numeric: true,
      value: (row) => row.entry.decode_tok_s,
      cell: (row) => (row.entry.decode_tok_s === null ? formatUnknown() : formatRate(row.entry.decode_tok_s)),
    },
    {
      key: "energy",
      label: t("references.col.energy"),
      numeric: true,
      cell: (row) => (row.entry.energy_wh_per_1k_tokens === null ? t("references.energy_none") : formatNumber(row.entry.energy_wh_per_1k_tokens)),
    },
    {
      key: "here",
      label: t("references.col.here"),
      cell: (row) => {
        if (row.entry.installed) return mark(row.entry.installed);
        return references.ollama_up ? t("references.here_none") : t("references.here_unknown");
      },
    },
  ];
  table.rows = rows;
  return table;
}
