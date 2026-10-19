// « Sur ce poste » : les modèles installés (EXPERIENCE.md, Modèles). Un `wl-data-table` lu depuis
// `GET /api/models` : nom, origine, usage, paramètres, taille, « tient en mémoire », « chargé » et
// débit mesuré sur ce poste. Le front ne calcule rien (AD-20) : `fits` et `short_gb` viennent de
// `hardware/`, le débit de la médiane des runs ; il met en forme et trie.
//
// - Tri initial : chargés d'abord, puis par nom. Un modèle chargé « tient » par définition : il est
//   déjà en mémoire (la mémoire libre du poste ne le compte plus).
// - Sous 1 024 px, Usage et Origine sont repliées ; un bouton au-dessus du tableau les affiche
//   (D-43).
// - Colonne « Actions » (story 5.4) : « Supprimer » ouvre le dialogue de confirmation de `models.js`
//   (`onDelete`). Il est `aria-disabled` (focalisable, clic sans effet) avec sa raison visible à côté :
//   « Utilisé par une réponse en cours » (le flux système dit quels modèles un run emploie) ou
//   Ollama muet.

import { element } from "../core/dom.js";
import { formatGb, formatRate, formatUnknown } from "../core/format.js";
import { t } from "../core/i18n.js";
import { store } from "../core/store.js";
import { nameCell, paramsText, usedBy } from "./models-format.js";

const COLLATOR = new Intl.Collator("fr", { numeric: true, sensitivity: "base" });
const SECONDARY = "models-secondary";

export function createInstalled({ onDelete, ollamaUp }) {
  let models = [];
  let loaded = null; // Set des tags chargés ; `null` : inconnu (Ollama muet)

  const title = element("h2", "", t("models.installed.title"));
  const toggle = element("button", "btn models-toggle", t("models.installed.secondary_show"));
  toggle.type = "button";
  toggle.setAttribute("aria-expanded", "false");
  const empty = element("p", "models-empty", t("models.installed.empty"));
  empty.hidden = true;
  const table = document.createElement("wl-data-table");
  const section = element("section", "models-section models-installed");
  section.setAttribute("aria-labelledby", "models-installed-title");
  title.id = "models-installed-title";
  title.tabIndex = -1; // reçoit le focus quand la ligne supprimée a disparu
  table.id = "models-installed-table";
  toggle.setAttribute("aria-controls", table.id);
  section.append(title, toggle, empty, table);

  toggle.addEventListener("click", () => {
    const shown = section.dataset.secondary === "shown";
    section.dataset.secondary = shown ? "" : "shown";
    toggle.setAttribute("aria-expanded", String(!shown));
    toggle.textContent = t(shown ? "models.installed.secondary_show" : "models.installed.secondary_hide");
  });

  const isLoaded = (model) => loaded !== null && loaded.has(model.tag);

  function fitsCell(model) {
    if (isLoaded(model) || model.fits === true) return t("models.installed.fits_yes");
    if (model.fits === false) {
      return model.short_gb === null || model.short_gb === undefined
        ? t("models.installed.fits_no", { missing: formatUnknown() })
        : t("models.installed.fits_no", { missing: formatGb(model.short_gb) });
    }
    return formatUnknown();
  }

  const fitsRank = (model) => (isLoaded(model) || model.fits === true ? 0 : model.fits === false ? 1 : 2);

  table.caption = t("models.installed.caption");
  table.columns = [
    { key: "name", label: t("models.installed.col_name"), sortable: true, value: (m) => m.name, cell: (m) => nameCell(m.name, m.tag) },
    {
      key: "origin",
      label: t("models.installed.col_origin"),
      className: SECONDARY,
      sortable: true,
      value: (m) => m.origin,
      cell: (m) => {
        const badge = document.createElement("wl-badge");
        badge.setAttribute("kind", m.origin);
        return badge;
      },
    },
    {
      key: "usage",
      label: t("models.installed.col_usage"),
      className: SECONDARY,
      sortable: true,
      value: (m) => t(`models.installed.usage_${m.kind}`),
    },
    {
      key: "params",
      label: t("models.installed.col_params"),
      sortable: true,
      numeric: true,
      value: (m) => m.params_total_b,
      cell: (m) => paramsText(m.params_total_b, m.params_active_b),
    },
    {
      key: "size",
      label: t("models.installed.col_size"),
      sortable: true,
      numeric: true,
      value: (m) => m.size_gb,
      cell: (m) => formatGb(m.size_gb),
    },
    {
      key: "fits",
      label: t("models.installed.col_fits"),
      sortable: true,
      value: fitsRank,
      cell: fitsCell,
    },
    {
      key: "loaded",
      label: t("models.installed.col_loaded"),
      sortable: true,
      value: (m) => (loaded === null ? null : isLoaded(m) ? 0 : 1),
      cell: (m) =>
        loaded === null
          ? formatUnknown()
          : t(isLoaded(m) ? "models.installed.loaded_yes" : "models.installed.loaded_no"),
    },
    {
      key: "rate",
      label: t("models.installed.col_rate"),
      sortable: true,
      numeric: true,
      value: (m) => m.throughput_tps,
      cell: (m) =>
        m.throughput_tps === null || m.throughput_tps === undefined
          ? t("models.installed.rate_none")
          : formatRate(m.throughput_tps),
    },
  ];

  let legends = 0;

  function actionsCell(model) {
    const box = element("div", "models-delete-cell");
    const button = element("button", "btn models-delete", t("models.installed.delete"));
    button.type = "button";
    button.dataset.tag = model.tag;
    button.setAttribute("aria-label", t("models.installed.delete_aria", { name: model.name }));
    let why = null;
    if (usedBy(store.get().system.modelsInUse, model.tag) !== null) why = t("models.installed.in_use");
    else if (!ollamaUp()) why = t("models.installed.delete_ollama_down");
    button.setAttribute("aria-disabled", String(why !== null));
    box.append(button);
    if (why !== null) {
      const legend = element("span", "help models-legend", why);
      legend.id = `models-delete-why-${++legends}`;
      button.setAttribute("aria-describedby", legend.id);
      box.append(legend);
    }
    button.addEventListener("click", () => {
      if (button.getAttribute("aria-disabled") !== "true") onDelete(model);
    });
    return box;
  }

  table.columns = [
    ...table.columns,
    { key: "actions", label: t("models.installed.col_actions"), cell: actionsCell },
  ];

  // Chargés d'abord, puis par nom.
  function ordered() {
    return [...models].sort(
      (a, b) =>
        Number(isLoaded(b)) - Number(isLoaded(a)) || COLLATOR.compare(a.name, b.name),
    );
  }

  function render() {
    empty.hidden = models.length > 0;
    table.hidden = models.length === 0;
    toggle.hidden = models.length === 0;
    table.rows = ordered();
  }

  // « Chargé » et « Supprimer » suivent le flux système : relus seulement quand l'ensemble des
  // modèles chargés ou employés par un run change (pas à chaque tick de 2 s).
  const unsubscribe = store.select(
    (state) => {
      const list = state.system.modelsLoaded;
      const used = Object.keys(state.system.modelsInUse).sort().join("|");
      return `${list === null ? "?" : list.map((m) => m.tag).sort().join("|")}#${used}`;
    },
    () => {
      const list = store.get().system.modelsLoaded;
      loaded = list === null ? null : new Set(list.map((m) => m.tag));
      if (models.length > 0) render();
    },
  );

  return {
    el: section,
    setModels(list) {
      models = list;
      render();
    },
    refresh: () => models.length > 0 && render(), // Ollama s'arrête ou revient : les boutons suivent
    dispose: unsubscribe,
  };
}
