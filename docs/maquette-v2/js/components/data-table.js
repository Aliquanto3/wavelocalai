// Tableau sémantique triable au clavier (UX-DR13), commun à l'Arène, au Banc d'essai, aux Références,
// à la Sobriété, aux Modèles, à la Base documentaire et à l'Évaluation.
//
//   dataTable({caption, regionLabel, columns, rows, sort, onSort, sortLabel, className, id, rowClass, extra})
//
// - `<table>` avec légende (masquée), en-têtes `scope="col"`, en-tête de ligne `scope="row"` pour la
//   colonne `header: true`. Le conteneur défile dans sa largeur (focusable, `role="region"`) : la page
//   ne défile jamais horizontalement.
// - Colonnes : `{key, label, value(row)?, cell(row), header?, numeric?, className?}` (`className` :
//   classe de l'en-tête et des cellules de la colonne, pour la masquer en petit écran par exemple). Une colonne qui a `value`
//   est triable : son en-tête est un bouton, `aria-sort` sur la colonne triée, flèche qui tourne.
//   Une valeur inconnue (`null`) reste en bas, quel que soit le sens.
// - `sort` : `{key, dir: "asc" | "desc"}` (rien de trié par défaut). Sans `onSort`, le tableau trie
//   lui-même ; avec `onSort(key)`, l'écran garde l'état et reconstruit le tableau.
// - `sortLabel(label, state)` : nom accessible du bouton (`state` : "asc", "desc" ou null) ; par
//   défaut « Trier par <colonne> », complété de « trié par ordre croissant » sur la colonne triée.
// - `className` : préfixe des classes propres à l'écran (`<p>-table-wrap`, `<p>-table`, `<p>-sort`),
//   ajoutées aux classes communes `wl-table-wrap`, `wl-table`, `wl-sort`.
// - `id` : les boutons de tri portent `data-fid="sort:<id>:<key>"` (focus rendu après reconstruction).
// - `rowClass(row)` : classe d'une ligne ; `extra(row)` : nœud affiché dans une ligne pleine largeur
//   sous la ligne (erreur, progression).

import { element, icon } from "../core/dom.js";
import { t } from "../core/i18n.js";

const defaultSortLabel = (label, dir) =>
  `${t("components.table.sort_by", { column: label })}${dir ? `, ${t(`components.table.sorted_${dir}`)}` : ""}`;

function compare(column, dir) {
  const sign = dir === "desc" ? -1 : 1;
  return (a, b) => {
    const x = column.value(a);
    const y = column.value(b);
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    const order = typeof x === "string" ? x.localeCompare(y, "fr-FR") : x - y;
    return order * sign;
  };
}

const cellClass = (column) => [column.className, column.numeric ? "is-numeric" : ""].filter(Boolean).join(" ");

export function sortRows(rows, columns, sort) {
  const column = columns.find((candidate) => candidate.key === sort?.key);
  return column?.value ? [...rows].sort(compare(column, sort.dir)) : [...rows];
}

export function dataTable({
  caption,
  regionLabel = caption,
  columns,
  rows,
  sort = null,
  onSort = null,
  sortLabel = defaultSortLabel,
  className = "",
  id = "",
  rowClass = null,
  extra = null,
}) {
  const prefixed = (base) => (className ? `wl-${base} ${className}-${base}` : `wl-${base}`);
  let state = sort ? { ...sort } : { key: null, dir: "asc" };
  const wrap = element("div", prefixed("table-wrap"));
  wrap.tabIndex = 0;
  wrap.setAttribute("role", "region");
  wrap.setAttribute("aria-label", regionLabel);
  const table = element("table", prefixed("table"));
  table.append(element("caption", "sr-only", caption));
  const head = element("tr");
  const headers = new Map();
  for (const column of columns) {
    const th = element("th", cellClass(column));
    th.scope = "col";
    if (column.value) {
      const button = element("button", prefixed("sort"));
      button.type = "button";
      button.dataset.key = column.key;
      if (id) button.dataset.fid = `sort:${id}:${column.key}`;
      button.append(element("span", "", column.label), icon("expand-more"));
      button.addEventListener("click", () => {
        if (onSort) return onSort(column.key);
        state = state.key === column.key ? { key: column.key, dir: state.dir === "asc" ? "desc" : "asc" } : { key: column.key, dir: "asc" };
        renderBody();
      });
      th.append(button);
    } else {
      th.append(column.label);
    }
    headers.set(column.key, th);
    head.append(th);
  }
  const thead = element("thead");
  thead.append(head);
  const tbody = element("tbody");
  table.append(thead, tbody);
  wrap.append(table);

  function renderHead() {
    for (const column of columns) {
      const th = headers.get(column.key);
      const button = th.querySelector("button");
      if (!button) continue;
      const active = state.key === column.key;
      if (active) th.setAttribute("aria-sort", state.dir === "asc" ? "ascending" : "descending");
      else th.removeAttribute("aria-sort");
      if (active) button.dataset.dir = state.dir;
      else delete button.dataset.dir;
      if (sortLabel) button.setAttribute("aria-label", sortLabel(column.label, active ? state.dir : null));
    }
  }

  function renderBody() {
    renderHead();
    const list = onSort ? rows : sortRows(rows, columns, state);
    tbody.replaceChildren();
    for (const row of list) {
      const tr = element("tr", rowClass?.(row) ?? "");
      for (const column of columns) {
        const cell = element(column.header ? "th" : "td", cellClass(column));
        if (column.header) cell.scope = "row";
        cell.dataset.label = column.label;
        const content = column.cell(row);
        if (content instanceof Node) cell.append(content);
        else if (content !== null && content !== undefined) cell.textContent = content;
        tr.append(cell);
      }
      tbody.append(tr);
      const more = extra?.(row);
      if (more) {
        const trExtra = element("tr", "wl-table-extra");
        const td = element("td");
        td.colSpan = columns.length;
        td.append(more);
        trExtra.append(td);
        tbody.append(trExtra);
      }
    }
  }

  renderBody();
  return wrap;
}
