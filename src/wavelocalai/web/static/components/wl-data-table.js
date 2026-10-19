// <wl-data-table> : tableau sémantique, triable au clavier (UX-DR13, AD-20). Sans Shadow DOM.
//
//   table.caption = "Documents de la base";           // nom accessible du tableau
//   table.columns = [{ key, label, sortable, numeric, value(row), cell(row) }];
//   table.rows = [...];                                // objets quelconques
//   table.sort = { key: "created_at", dir: "desc" };   // tri initial (facultatif)
//
// - `<table>` avec `<caption>`, `<th scope="col">` (colonnes) et `<th scope="row">` (première
//   colonne). Un en-tête triable est un bouton : Entrée ou Espace trie, `aria-sort` dit l'ordre.
// - `value(row)` donne la valeur de tri (nombre ou texte) ; `null` ou `undefined` passe en dernier,
//   dans les deux ordres. `cell(row)` rend le texte ou le nœud affiché (sinon `value`).
// - Le tableau garde le focus sur l'en-tête trié (aussi quand ses lignes changent) et annonce
//   l'ordre dans une zone polie.
// - Le front ne calcule aucune mesure : il trie et met en forme ce que l'API a donné (AD-20).

import { element, icon } from "../core/dom.js";
import { t } from "../core/i18n.js";

const COLLATOR = new Intl.Collator("fr", { numeric: true, sensitivity: "base" });

function compare(a, b) {
  if (typeof a === "number" && typeof b === "number") return a - b;
  return COLLATOR.compare(String(a), String(b));
}

export class WlDataTable extends HTMLElement {
  #caption = "";
  #columns = [];
  #rows = [];
  #sort = null;
  #announce = null;
  #slot = null;
  #refocus = null;

  get caption() {
    return this.#caption;
  }
  set caption(value) {
    this.#caption = value ?? "";
    this.#render();
  }
  get columns() {
    return this.#columns;
  }
  set columns(value) {
    this.#columns = value ?? [];
    this.#render();
  }
  get rows() {
    return this.#rows;
  }
  set rows(value) {
    this.#rows = value ?? [];
    this.#render();
  }
  get sort() {
    return this.#sort;
  }
  set sort(value) {
    this.#sort = value ?? null;
    this.#render();
  }

  connectedCallback() {
    this.#render();
  }

  // Les lignes dans l'ordre affiché.
  get sortedRows() {
    const sort = this.#sort;
    const column = sort && this.#columns.find((candidate) => candidate.key === sort.key);
    if (!column) return [...this.#rows];
    const value = column.value ?? ((row) => row[column.key]);
    const sign = sort.dir === "desc" ? -1 : 1;
    return this.#rows
      .map((row, index) => ({ row, index, key: value(row) }))
      .sort((a, b) => {
        const missingA = a.key === null || a.key === undefined;
        const missingB = b.key === null || b.key === undefined;
        if (missingA || missingB) return missingA === missingB ? a.index - b.index : missingA ? 1 : -1;
        return sign * compare(a.key, b.key) || a.index - b.index;
      })
      .map((entry) => entry.row);
  }

  #toggle(column) {
    const same = this.#sort?.key === column.key;
    const dir = same && this.#sort.dir === "asc" ? "desc" : "asc";
    this.#sort = { key: column.key, dir };
    this.#refocus = column.key;
    this.#render();
    this.#announce.textContent = t(dir === "asc" ? "components.table.sorted_asc" : "components.table.sorted_desc", {
      column: column.label,
    });
  }

  #render() {
    if (!this.isConnected) return;
    this.className = "wl-data-table";
    if (!this.#announce) {
      this.#announce = element("p", "sr-only");
      this.#announce.setAttribute("role", "status");
      this.#slot = element("div");
      this.replaceChildren(this.#slot, this.#announce); // la zone polie reste en place entre deux rendus
    }
    // Un nouveau rendu (lignes mises à jour pendant un import) remplace les nœuds : le focus d'un
    // en-tête de tri ou de la zone qui défile est rendu au nœud équivalent.
    const focused = this.contains(document.activeElement) ? document.activeElement : null;
    if (focused?.classList.contains("wl-table-sort")) this.#refocus ??= focused.dataset.key;
    const refocusWrap = focused?.classList.contains("wl-table-wrap") ?? false;
    // La position de défilement de la zone remplacée est gardée (lignes mises à jour en direct).
    const previous = this.#slot.querySelector(".wl-table-wrap");
    const scroll = previous ? { left: previous.scrollLeft, top: previous.scrollTop } : null;
    const table = element("table", "wl-table");
    table.append(element("caption", "sr-only", this.#caption));

    const head = element("tr");
    for (const column of this.#columns) {
      const th = element("th", column.numeric ? "wl-table-num" : "");
      th.scope = "col";
      if (column.sortable) {
        const active = this.#sort?.key === column.key;
        th.setAttribute("aria-sort", active ? (this.#sort.dir === "asc" ? "ascending" : "descending") : "none");
        const button = element("button", "wl-table-sort");
        button.type = "button";
        button.dataset.key = column.key;
        button.append(element("span", "", column.label));
        const arrow = icon("expand-more");
        arrow.classList.add("wl-table-arrow");
        arrow.dataset.dir = active ? this.#sort.dir : "";
        button.append(arrow);
        button.addEventListener("click", () => this.#toggle(column));
        th.append(button);
      } else {
        th.textContent = column.label;
      }
      head.append(th);
    }
    const thead = element("thead");
    thead.append(head);

    const body = element("tbody");
    for (const row of this.sortedRows) {
      const tr = element("tr");
      this.#columns.forEach((column, index) => {
        const cell = element(index === 0 ? "th" : "td", column.numeric ? "wl-table-num" : "");
        if (index === 0) cell.scope = "row";
        const content = column.cell ? column.cell(row) : (column.value ?? ((r) => r[column.key]))(row);
        if (content instanceof Node) cell.append(content);
        else cell.textContent = content ?? "";
        tr.append(cell);
      });
      body.append(tr);
    }
    table.append(thead, body);

    // Une zone qui défile se parcourt au clavier (axe : scrollable-region-focusable).
    const wrap = element("div", "wl-table-wrap");
    wrap.tabIndex = 0;
    wrap.setAttribute("role", "region");
    wrap.setAttribute("aria-label", this.#caption);
    wrap.append(table);
    this.#slot.replaceChildren(wrap);
    if (scroll) {
      wrap.scrollLeft = scroll.left;
      wrap.scrollTop = scroll.top;
    }

    if (refocusWrap) wrap.focus({ preventScroll: true });
    if (this.#refocus) {
      this.querySelector(`.wl-table-sort[data-key="${CSS.escape(this.#refocus)}"]`)?.focus();
      this.#refocus = null;
    }
  }
}

if (!customElements.get("wl-data-table")) customElements.define("wl-data-table", WlDataTable);
