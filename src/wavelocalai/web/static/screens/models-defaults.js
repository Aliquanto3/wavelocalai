// « Modèles proposés par défaut » (story 5.4, décision Q2, UX-DR27, AD-9, AD-15, AD-20) : une ligne
// par usage (Conversation, Arène, Juge, Agent, Documents), le modèle proposé avec son badge d'origine
// et la raison que le serveur en donne (`GET /api/models/defaults`). Le choix est explicite, jamais
// retenu sans geste.
//
// - « Changer » remplace la cellule Modèle par `wl-model-picker` filtré sur les modèles éligibles à
//   l'usage (`eligible-only` : un modèle inéligible n'est pas proposé, plutôt que refusé à
//   « Enregistrer », décision du 2026-10-19) ; l'Arène en demande 2 ou 3. « Enregistrer » écrit par
//   `PUT /api/models/defaults/{usage}` ; « Annuler » n'écrit rien.
// - « Revenir au choix automatique » (seulement pour un choix de la personne) efface la préférence.
// - Un choix cloud tant que le cloud n'est pas autorisé est dit « inactif » : la règle s'applique.
// - Aucun calcul (AD-20) : modèles, raison et éligibilité viennent du serveur.
// - Le tableau n'est redessiné que sur un geste ou une relecture : un sélecteur ouvert ne l'est pas
//   par un tick du flux système.

import { api, ApiError } from "../core/api.js";
import { element } from "../core/dom.js";
import { t } from "../core/i18n.js";
import "../components/index.js";

const PURPOSES = ["chat", "arena", "judge", "agent", "rag"];
const LIST = new Intl.ListFormat("fr", { style: "long", type: "conjunction" });

export function createDefaults({ say, allowCloud }) {
  let rows = []; // { purpose, tags, reason, source, inactive }
  let index = new Map(); // tag -> modèle de `GET /api/models`
  let editing = null; // { purpose, picker, warning, node } : la ligne dont le sélecteur est ouvert

  const title = element("h2", "section-label", t("models.defaults.title"));
  title.id = "models-defaults-title";
  const problem = document.createElement("wl-error");
  const table = document.createElement("wl-data-table");
  table.caption = t("models.defaults.caption");
  const section = element("section", "models-section models-defaults");
  section.setAttribute("aria-labelledby", title.id);
  section.append(title, problem, table);

  const usage = (purpose) => t(`models.defaults.purpose_${purpose}`);
  const nameOf = (tag) => index.get(tag)?.name ?? tag;

  // L'enveloppe du serveur, ou celle du texte de secours quand il ne répond pas.
  const saveFailed = () => ({
    code: "internal",
    message: t("models.defaults.save_failed"),
    action: t("models.defaults.save_failed_action"),
  });
  const readFailed = () => ({
    code: "internal",
    message: t("models.defaults.read_failed"),
    action: t("models.defaults.read_failed_action"),
  });
  const envelopeOf = (failure, fallback) =>
    failure instanceof ApiError && failure.envelope ? failure.envelope : fallback();

  function modelCell(row) {
    if (editing?.purpose === row.purpose) return editing.node;
    const box = element("div", "models-default-model");
    if (row.tags.length === 0) box.append(element("span", "", t("models.defaults.none")));
    for (const tag of row.tags) {
      const item = element("span", "models-default-item");
      item.append(element("span", "models-name-text", nameOf(tag)));
      const badge = document.createElement("wl-badge");
      badge.setAttribute("kind", index.get(tag)?.origin ?? "unknown");
      item.append(badge);
      box.append(item);
    }
    if (row.inactive.length) {
      const names = LIST.format(row.inactive.map(nameOf));
      box.append(element("span", "help", t("models.defaults.inactive", { name: names })));
    }
    return box;
  }

  function button(label, aria, purpose, kind, handler) {
    const node = element("button", "btn", label);
    node.type = "button";
    node.dataset.purpose = purpose;
    node.dataset.action = kind;
    node.setAttribute("aria-label", t(aria, { usage: usage(purpose) }));
    node.addEventListener("click", handler);
    return node;
  }

  function actionsCell(row) {
    const box = element("div", "models-default-actions");
    const { purpose } = row;
    if (editing?.purpose === purpose) {
      const save = button(t("models.defaults.save"), "models.defaults.save_aria", purpose, "save", () => submit(row));
      save.classList.add("models-install-named");
      box.append(save, button(t("models.defaults.cancel"), "models.defaults.cancel_aria", purpose, "cancel", () => stop(purpose)));
      return box;
    }
    box.append(button(t("models.defaults.change"), "models.defaults.change_aria", purpose, "change", () => edit(row)));
    if (row.source === "preference" || row.inactive.length) {
      box.append(button(t("models.defaults.revert"), "models.defaults.revert_aria", purpose, "revert", () => revert(row)));
    }
    return box;
  }

  table.columns = [
    { key: "usage", label: t("models.defaults.col_usage"), cell: (row) => usage(row.purpose) },
    { key: "model", label: t("models.defaults.col_model"), cell: modelCell },
    { key: "reason", label: t("models.defaults.col_reason"), cell: (row) => row.reason },
    { key: "actions", label: t("models.defaults.col_actions"), cell: actionsCell },
  ];

  const focusAction = (purpose, kind) =>
    section.querySelector(`button[data-purpose="${purpose}"][data-action="${kind}"]`)?.focus();

  // --- Le sélecteur d'une ligne --------------------------------------------------------------
  function edit(row) {
    const arena = row.purpose === "arena";
    const picker = document.createElement("wl-model-picker");
    picker.setAttribute("purpose", row.purpose);
    picker.setAttribute("eligible-only", "");
    if (arena) picker.setAttribute("multi", "");
    const label = arena ? "models.defaults.picker_label_arena" : "models.defaults.picker_label";
    picker.setAttribute("label", t(label, { usage: usage(row.purpose) }));
    picker.values = row.tags;
    const warning = document.createElement("wl-error");
    const node = element("div", "models-default-editor");
    node.append(picker, warning);
    picker.addEventListener("wl-model-change", () => {
      warning.error = null;
    });
    editing = { purpose: row.purpose, picker, warning, node };
    render();
    picker.querySelector("input")?.focus();
  }

  function stop(purpose) {
    editing = null;
    render();
    focusAction(purpose, "change");
  }

  async function submit(row) {
    const { picker, warning } = editing;
    const tags = picker.values;
    const arena = row.purpose === "arena";
    if (arena ? tags.length < 2 || tags.length > 3 : tags.length !== 1) {
      warning.error = {
        code: "invalid_request",
        message: t(arena ? "models.defaults.arena_count" : "models.defaults.nothing_chosen"),
      };
      return;
    }
    try {
      const saved = await api.setModelDefault(row.purpose, tags, allowCloud());
      const names = LIST.format(saved.tags.map(nameOf));
      say(t("models.defaults.saved", { usage: usage(row.purpose), name: names }));
    } catch (failure) {
      warning.error = envelopeOf(failure, saveFailed);
      return;
    }
    editing = null;
    await load(null);
    focusAction(row.purpose, "change");
  }

  async function revert(row) {
    problem.error = null;
    try {
      await api.clearModelDefault(row.purpose);
      say(t("models.defaults.reverted", { usage: usage(row.purpose) }));
    } catch (failure) {
      problem.error = envelopeOf(failure, saveFailed);
      return;
    }
    await load(null);
    focusAction(row.purpose, "change");
  }

  // --- Lecture ---------------------------------------------------------------------------------
  function render() {
    table.rows = rows;
  }

  // Relit les cinq usages. `models` : la liste de `GET /api/models` (noms et badges) ; `null` garde
  // celle de la dernière lecture. Un sélecteur ouvert reste ouvert.
  async function load(models) {
    if (models) index = new Map(models.map((model) => [model.tag, model]));
    const cloud = allowCloud();
    const results = await Promise.allSettled(PURPOSES.map((purpose) => api.modelDefaults(purpose, cloud)));
    const first = results.find((result) => result.status === "rejected");
    const everyFailed = results.every((result) => result.status === "rejected");
    // `no_model` (aucun modèle de conversation) est une réponse : sa phrase dit quoi faire. Toute
    // autre panne de tous les usages (serveur muet) est une erreur de lecture.
    const silent = everyFailed && first.reason?.envelope?.code !== "no_model";
    problem.error = silent ? envelopeOf(first.reason, readFailed) : null;
    if (silent) return;
    rows = results.map((result, position) => {
      const purpose = PURPOSES[position];
      if (result.status === "fulfilled") {
        const { tags, reason, source, inactive = [] } = result.value;
        return { purpose, tags, reason, source, inactive };
      }
      const message = result.reason?.envelope?.message ?? t("models.defaults.no_model");
      return { purpose, tags: [], reason: message, source: "rule", inactive: [] };
    });
    if (editing === null) render(); // un sélecteur ouvert n'est pas redessiné sous la personne
  }

  return {
    el: section,
    load,
    // Les noms d'usage dont le défaut est un choix de la personne pour ce modèle (D-41).
    usagesOf: (tag) =>
      rows.filter((row) => row.source === "preference" && row.tags.includes(tag)).map((row) => usage(row.purpose)),
    nameOf,
  };
}
