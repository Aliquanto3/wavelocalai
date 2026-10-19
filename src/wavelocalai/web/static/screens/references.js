// Références, `#/arene/references` (UX-DR13, UX-DR24, UX-DR25, AD-20, AD-22) : quel modèle pour quel
// usage, lu des résultats publiés du banc (`qb.results/1`) par `GET /api/references`, jamais avant le
// repère `shell-ready` (AD-15). Le serveur classe et désigne les meilleurs ; l'écran met en forme
// (`references-view.js`) et ne calcule aucun rang.
//
// - Une carte par usage publié (vue par défaut) ou le tableau équivalent (segments « Cartes · Tableau »).
// - Références indisponibles (fichier absent, autre format, aucun usage classé) : la raison du serveur,
//   jamais de carte vide. Ollama arrêté : les références restent lisibles, sans marque, avec un message.
// - « Comparer ces modèles » ouvre l'Arène présélectionnée (`references-compare.js`, D-19).

import { api, ApiError } from "../core/api.js";
import { element, icon } from "../core/dom.js";
import { formatDate, formatInteger } from "../core/format.js";
import { t } from "../core/i18n.js";
import { screenTabs } from "../core/screen-tabs.js";
import { shellReady } from "../core/shell-ready.js";
import { segments } from "../components/segments.js";
import "../components/wl-error.js";
import { cardsView, tableView } from "./references-view.js";

function sourceLine(references) {
  const machine = references.reference_machine;
  const vars = { source: references.source, version: references.bench_version ?? "" };
  if (!machine) return t("references.no_reference_machine", vars);
  const memory = machine.ram_gb === null ? "" : t("references.memory_value", { value: formatInteger(machine.ram_gb) });
  const details = {
    ...vars,
    machine: machine.label,
    memory,
    gpu: machine.gpu ?? t("references.gpu_none"),
    date: references.published ? formatDate(references.published) : "",
  };
  return t(references.published ? "references.source" : "references.source_no_date", details);
}

function unavailable(reason) {
  const box = element("div", "ref-unavailable");
  box.setAttribute("role", "status");
  box.append(icon("info"), element("h2", "", t("references.unavailable_title")), element("p", "", reason));
  return box;
}

function failure(error) {
  const problem = document.createElement("wl-error");
  const envelope = error instanceof ApiError ? error.envelope : null;
  problem.error = envelope ?? {
    code: "references_failed",
    message: t("references.failed"),
    action: t("references.failed_action"),
  };
  return problem;
}

export function mount(host) {
  const live = element("div", "sr-only");
  live.setAttribute("role", "status");
  live.setAttribute("aria-live", "polite");
  const intro = element("p", "help ref-source");
  intro.hidden = true;
  const notices = element("div", "ref-notices");
  const content = element("div", "ref-content");
  host.replaceChildren(
    element("h1", "", t("screens.arena-references")),
    screenTabs("arena", "arena-references"),
    element("p", "lead", t("references.lead")),
    intro,
    notices,
    content,
    live,
  );

  let alive = true;
  let data = null;
  let segment = "cards";
  const picker = segments({
    label: t("references.segment_label"),
    options: [
      { value: "cards", label: t("references.cards") },
      { value: "table", label: t("references.table") },
    ],
    value: segment,
    onChange(value) {
      segment = value;
      renderBody();
      live.textContent = t(value === "table" ? "references.announce_table" : "references.announce_cards");
    },
  });
  const body = element("div", "ref-body");

  function renderBody() {
    body.replaceChildren(segment === "table" ? tableView(data) : cardsView(data));
  }

  function render() {
    notices.replaceChildren();
    if (!data.available) {
      intro.hidden = true;
      content.replaceChildren(unavailable(data.reason));
      return;
    }
    intro.textContent = sourceLine(data);
    intro.hidden = false;
    if (!data.ollama_up) {
      const notice = element("p", "wl-notice wl-notice-info");
      notice.setAttribute("role", "status");
      notice.append(icon("info"), element("span", "", t("references.ollama_down")));
      notices.append(notice);
    }
    renderBody();
    content.replaceChildren(element("h2", "", t("references.title")), picker.root, body);
  }

  const loading = element("p", "help", t("references.loading"));
  loading.setAttribute("role", "status");
  content.replaceChildren(loading);

  // Lecture au montage puis à chaque retour sur l'écran (le routeur le garde monté) : les marques
  // « installé » suivent ce que le poste a installé entre-temps. Un échec de relecture garde l'écran.
  let reading = 0;
  function load() {
    const mine = ++reading;
    shellReady()
      .then(() => api.references())
      .then((references) => {
        if (!alive || mine !== reading) return;
        data = references;
        render();
      })
      .catch((error) => {
        if (alive && mine === reading && data === null) content.replaceChildren(failure(error));
      });
  }
  load();

  let wasHidden = host.hidden;
  const visibility = new MutationObserver(() => {
    if (host.hidden === wasHidden) return;
    wasHidden = host.hidden;
    if (!wasHidden) load();
  });
  visibility.observe(host, { attributes: true, attributeFilter: ["hidden"] });

  return () => {
    alive = false;
    visibility.disconnect();
    host.replaceChildren();
  };
}
