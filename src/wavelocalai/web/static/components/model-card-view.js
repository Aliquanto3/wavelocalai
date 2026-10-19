// Vue de la fiche d'un modèle (story 5.6, UX-DR15, UX-DR27, AD-20, AD-22) : le même rendu sert le
// panneau de l'écran Modèles (`#/modeles/<tag>`) et le panneau « Fiche du modèle » ouvert depuis un
// `wl-model-picker`. Le front ne calcule rien : l'architecture, les paramètres, les phrases de
// « Pourquoi ce débit ? » et les lignes de « Sur d'autres postes » viennent de
// `GET /api/models/card/<tag>`. Il met en forme : une valeur absente s'affiche « inconnu », jamais 0,
// une fraction de 0 à 1 s'affiche en pourcentage, l'énergie seulement si `status = "measured"`.
//
//   renderModelCard(card, { onInstall?, installBlocked?, headingId })  ->  [nœuds]
//
// `onInstall(tag)` : le bouton « Installer ce modèle » (ou « Installer quand même » quand il ne tient
// pas, D-42) ; sans lui (panneau d'un autre écran), aucun bouton. `installBlocked` : la raison pour
// laquelle l'installation est impossible ici (une installation en cours, Ollama muet), le bouton reste
// focalisable (`aria-disabled`) et la raison est écrite.

import { element, icon } from "../core/dom.js";
import {
  formatGb,
  formatInteger,
  formatNumber,
  formatPercent,
  formatRate,
  formatUnknown,
} from "../core/format.js";
import { t } from "../core/i18n.js";
import "./wl-badge.js";
import "./wl-data-table.js";

const billions = (value) =>
  value === null || value === undefined ? formatUnknown() : `${formatNumber(value)}\u00a0B`;

// Une fraction de 0 à 1 publiée par le serveur, en pourcentage : « 40 % ». `null` : inconnu.
const fraction = (value) =>
  value === null || value === undefined ? formatUnknown() : formatPercent(Math.round(value * 100));

const yesNo = (value) =>
  value === true ? t("models.card.yes") : value === false ? t("models.card.no") : formatUnknown();

function traits(card) {
  const list = element("dl", "models-card-traits");
  const rows = [
    [t("models.card.arch"), card.architecture ? t(`models.card.arch_${card.architecture}`) : formatUnknown()],
    [t("models.card.params_total"), billions(card.params_total_b)],
    [t("models.card.params_active"), billions(card.params_active_b)],
    [t("models.card.quant"), card.quantization ?? formatUnknown()],
    [
      t("models.card.context"),
      card.context_length === null || card.context_length === undefined
        ? formatUnknown()
        : t("models.card.context_value", { value: formatInteger(card.context_length) }),
    ],
    [t("models.card.license"), card.license ?? formatUnknown()],
    [t("models.card.tools"), yesNo(card.tools_verified)],
    [t("models.card.reasoning"), yesNo(card.reasoning)],
  ];
  for (const [term, value] of rows) list.append(element("dt", "", term), element("dd", "", value));
  return [element("h3", "", t("models.card.traits")), list];
}

function whyBlock(card) {
  const box = element("details", "models-card-details");
  box.dataset.part = "why";
  box.append(element("summary", "", t("models.card.why_title")));
  if (card.why === null || card.why === undefined) {
    box.append(element("p", "", t(card.origin === "cloud" ? "models.card.why_cloud" : "models.card.why_not_installed")));
    return box;
  }
  const rate = card.why.measured_tps;
  box.append(
    element(
      "p",
      "",
      rate === null || rate === undefined
        ? t("models.card.why_none")
        : t("models.card.why_measured", { rate: formatRate(rate) }),
    ),
  );
  const list = element("ul", "models-card-why");
  for (const sentence of card.why.lines) list.append(element("li", "", sentence));
  box.append(list);
  return box;
}

function energyText(energy) {
  if (energy.status === "measured" && energy.wh_per_1k_tokens !== null) {
    return t("models.card.energy_value", { value: formatNumber(energy.wh_per_1k_tokens) });
  }
  return t(energy.status === "unvalidated" ? "models.card.energy_unvalidated" : "models.card.energy_not_measured");
}

function machineCell(row) {
  const cell = element("span", "models-name");
  cell.append(element("span", "models-name-text", row.label));
  return cell;
}

function referenceTable(card) {
  const table = document.createElement("wl-data-table");
  table.caption = t("models.card.others_caption", { name: card.name });
  table.columns = [
    { key: "machine", label: t("models.card.col_machine"), cell: machineCell },
    {
      key: "rate",
      label: t("models.card.col_rate"),
      numeric: true,
      cell: (row) => formatRate(row.decode_tok_s),
    },
    {
      key: "ram",
      label: t("models.card.col_ram"),
      numeric: true,
      cell: (row) =>
        row.memory.ram_peak_gb === null
          ? formatUnknown()
          : t("models.card.ram_value", {
              used: formatGb(row.memory.ram_peak_gb),
              share: fraction(row.memory.ram_fraction),
            }),
    },
    {
      key: "vram",
      label: t("models.card.col_vram"),
      numeric: true,
      cell: (row) => (row.gpu === null ? t("models.card.no_gpu") : fraction(row.memory.gpu_fraction)),
    },
    { key: "energy", label: t("models.card.col_energy"), cell: (row) => energyText(row.energy) },
  ];
  table.rows = card.references.rows;
  const region = element("div", "models-card-scroll");
  region.setAttribute("role", "region");
  region.setAttribute("aria-label", t("models.card.others_region"));
  region.tabIndex = 0;
  region.append(table);
  return region;
}

function othersBlock(card, notice) {
  const refs = card.references;
  const box = element("details", "models-card-details");
  box.dataset.part = "others";
  box.append(element("summary", "", t("models.card.others_title")));
  if (!refs.available) {
    box.append(
      element("p", "models-strong", t("models.card.unavailable_title")),
      element("p", "", t("models.card.unavailable_text", { reason: refs.reason ?? "" })),
    );
    return box;
  }
  if (refs.version === "not_published" || refs.rows.length === 0) {
    box.append(element("p", "", t("models.card.not_published")));
    return box;
  }
  if (refs.version === "other_version") {
    box.append(notice(t("models.card.other_version"), t("models.card.other_version_note")));
  } else if (refs.version === "unknown") {
    box.append(element("p", "help", t("models.card.unknown_version_note")));
  }
  box.append(referenceTable(card));
  if (!refs.pc_pro_published) box.append(element("p", "help", t("models.card.no_pc_pro")));
  box.append(
    element(
      "p",
      "help",
      refs.bench_version
        ? t("models.card.source", { version: refs.bench_version })
        : t("models.card.source_no_version"),
    ),
    element("p", "help", t("models.card.unit_note")),
  );
  return box;
}

// Un avertissement en texte (jamais la couleur seule) : « Autre version : … ».
function warning(label, text) {
  const box = element("p", "models-card-warning");
  box.append(icon("warning"), element("strong", "", label), `\u00a0: ${text}`);
  return box;
}

function installBlock(card, { onInstall, installBlocked }) {
  const parts = [element("p", "models-card-note", t("models.card.not_installed"))];
  if (!onInstall) return parts;
  const anyway = card.fits === false;
  if (anyway) {
    const missing = formatGb(card.short_gb);
    parts.push(element("p", "models-card-note", t("models.card.doesnt_fit", { missing })));
  }
  const button = element(
    "button",
    "btn models-install-named models-card-install",
    t(anyway ? "models.catalog.install_anyway" : "models.card.install_here"),
  );
  button.type = "button";
  button.dataset.action = "card-install";
  button.setAttribute("aria-disabled", String(Boolean(installBlocked)));
  parts.push(button);
  if (installBlocked) {
    const reason = element("p", "help models-card-reason", installBlocked);
    reason.id = `models-card-reason-${card.tag.replace(/[^A-Za-z0-9_-]/g, "-")}`;
    button.setAttribute("aria-describedby", reason.id);
    parts.push(reason);
  }
  button.addEventListener("click", () => {
    if (button.getAttribute("aria-disabled") !== "true") onInstall(card.tag);
  });
  return parts;
}

export function renderModelCard(card, options = {}) {
  const head = element("div", "models-card-head");
  const title = element("h2", "models-card-title", card.name);
  title.id = options.headingId ?? "models-card-title";
  title.tabIndex = -1; // reçoit le focus à l'ouverture de la fiche
  const badge = document.createElement("wl-badge");
  badge.setAttribute("kind", card.origin === "cloud" ? "cloud" : "local");
  head.append(title, badge);
  const parts = [head];
  if (card.name !== card.tag) parts.push(element("code", "models-tag", card.tag));
  if (!card.installed && card.origin !== "cloud") parts.push(...installBlock(card, options));
  parts.push(...traits(card), whyBlock(card), othersBlock(card, warning));
  return parts;
}
