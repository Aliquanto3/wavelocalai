// « Catalogue installable » : les modèles de `config/models_catalog.json` que ce poste n'a pas
// (un modèle supprimé y revient), lus depuis `GET /api/models/catalog` avec la mémoire nécessaire et
// `fits` calculés par le serveur (AD-20 : le front ne calcule rien).
//
// - Un modèle qui ne tient pas reste installable : son bouton devient « Installer quand même »
//   (nom accessible « Installer <tag> quand même : il ne tient pas dans la mémoire libre »), et sa
//   ligne dit « Ne tient pas : 6,1 Go nécessaires, 4,8 Go libres » (D-42). Un clic installe : aucune
//   confirmation, c'est le seul geste qui télécharge (AD-17).
// - Pendant une installation, les autres boutons sont `aria-disabled` (focalisables, clic sans
//   effet) et la raison est écrite sous le titre. La cellule de la ligne installée porte la barre
//   de progression et « Annuler » ; l'échec (`pull_failed`) reste dans la ligne.
// - Ordre initial : celui du serveur (ceux qui tiennent d'abord, puis la mémoire nécessaire).

import { element } from "../core/dom.js";
import { formatGb, formatUnknown } from "../core/format.js";
import { t } from "../core/i18n.js";
import { nameCell, paramsText } from "./models-format.js";

export function createCatalog({ pull, ollamaUp, onInstall }) {
  let rows = [];
  let free = null;

  const title = element("h2", "", t("models.catalog.title"));
  title.id = "models-catalog-title";
  const reason = element("p", "help models-reason");
  reason.id = "models-catalog-reason";
  reason.hidden = true;
  const empty = element("p", "models-empty", t("models.catalog.empty"));
  empty.hidden = true;
  const table = document.createElement("wl-data-table");
  const section = element("section", "models-section models-catalog");
  section.setAttribute("aria-labelledby", title.id);
  section.append(title, reason, empty, table);

  // La raison pour laquelle « Installer » est désactivé : une installation en cours, ou Ollama muet.
  function blocked() {
    if (pull.busy) {
      const tag = pull.activeTag;
      return t("models.catalog.busy", { tag: tag ?? "…" });
    }
    return ollamaUp() ? null : t("models.catalog.ollama_down");
  }

  function fitsCell(model) {
    if (model.fits === true) return t("models.catalog.fits_yes");
    if (model.fits === false) {
      const needed = formatGb(model.required_gb ?? model.needed_gb);
      return free === null || free === undefined
        ? t("models.catalog.fits_no_nofree", { needed })
        : t("models.catalog.fits_no", { needed, free: formatGb(free) });
    }
    return formatUnknown();
  }

  function installButton(model, why) {
    const anyway = model.fits === false;
    const button = element(
      "button",
      "btn models-install",
      t(anyway ? "models.catalog.install_anyway" : "models.catalog.install"),
    );
    button.type = "button";
    button.setAttribute(
      "aria-label",
      t(anyway ? "models.catalog.install_anyway_aria" : "models.catalog.install_aria", {
        tag: model.tag,
      }),
    );
    button.dataset.tag = model.tag;
    button.setAttribute("aria-disabled", String(why !== null));
    if (why !== null) button.setAttribute("aria-describedby", reason.id);
    button.addEventListener("click", () => {
      if (button.getAttribute("aria-disabled") !== "true") onInstall(model.tag);
    });
    return button;
  }

  function actionCell(model) {
    if (pull.activeTag === model.tag) return pull.progress.el;
    if (pull.doneTag === model.tag) return pull.doneNode; // installé : la ligne part à la relecture
    const cell = element("div", "models-install-cell");
    cell.append(installButton(model, blocked()));
    if (pull.failedTag === model.tag) cell.append(pull.failureNode);
    return cell;
  }

  table.caption = t("models.catalog.caption");
  table.columns = [
    {
      key: "name",
      label: t("models.catalog.col_name"),
      sortable: true,
      value: (m) => m.name,
      cell: (m) => nameCell(m.name, m.tag),
    },
    {
      key: "params",
      label: t("models.catalog.col_params"),
      sortable: true,
      numeric: true,
      value: (m) => m.params_total_b,
      cell: (m) => paramsText(m.params_total_b, m.params_active_b),
    },
    {
      key: "needed",
      label: t("models.catalog.col_needed"),
      sortable: true,
      numeric: true,
      value: (m) => m.required_gb,
      cell: (m) => formatGb(m.required_gb ?? m.needed_gb),
    },
    {
      key: "fits",
      label: t("models.catalog.col_fits"),
      sortable: true,
      value: (m) => (m.fits === true ? 0 : m.fits === false ? 1 : 2),
      cell: fitsCell,
    },
    { key: "actions", label: t("models.catalog.col_actions"), sortable: false, cell: actionCell },
  ];

  // Relit l'état (installation en cours ou non) : les boutons et la raison suivent. Pas à chaque
  // pourcentage : la barre se met à jour sur place.
  function render() {
    const why = blocked();
    reason.hidden = why === null;
    reason.textContent = why ?? "";
    empty.hidden = rows.length > 0;
    table.hidden = rows.length === 0;
    table.rows = rows;
  }

  return {
    el: section,
    render,
    find: (tag) => rows.find((row) => row.tag === tag) ?? null,
    setData(list) {
      rows = list.models;
      free = list.free_gb;
      render();
    },
  };
}
