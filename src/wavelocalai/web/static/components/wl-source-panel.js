// <wl-source-panel> : les sources d'une réponse sur documents (UX-DR11, D-21, D-22, AD-7, AD-20).
//
//   panel.sources = [{n, doc_id, document, page, chunk_id, text, rank, relevance_label, raw_score,
//                     passage}, …]      // la liste de l'événement `sources` (ou d'une réponse rouverte)
//   panel.clear()                       // plus de source : « Les sources apparaissent ici… »
//   panel.open(n)                       // ouvre l'extrait de la source n (comme « Ouvrir l'extrait »)
//   panel.highlight(n)                  // met la source n en évidence (`null` : aucune), sans événement
//   événement `wl-source-link` (`detail.n`, ou `null` à la sortie) : une source est survolée ou
//   focalisée ; l'écran y met les marqueurs `[n]` de la réponse en évidence (citations vérifiées)
//
// Liste numérotée : document, page (si le document en a), libellé de pertinence (le score brut en
// aide), puis l'extrait, replié à trois lignes. « Ouvrir l'extrait » relit l'extrait entier au
// serveur (`GET /api/rag/chunks/{id}`) et surligne le passage que le serveur désigne ; le front ne
// choisit aucun passage. Une source sans texte (`text: null`, document supprimé depuis), ou dont
// l'extrait n'existe plus à l'ouverture (`404 chunk_not_found`), dit « extrait supprimé ».
//
// Les positions de `passage` sont des points de code Python (`str`), pas les unités UTF-16 de
// `String.slice` : le texte est découpé par `Array.from`, sinon un emoji décalerait le surlignage.
//
// Dès 1 024 px le panneau est toujours ouvert, sans bouton de repli (D-22) ; en deçà il est replié
// et se déplie par son titre. Sans Shadow DOM, sans `innerHTML` : le texte d'un document est un nœud
// de texte.

import { api, ApiError } from "../core/api.js";
import { element, icon } from "../core/dom.js";
import { formatInteger, formatNumber } from "../core/format.js";
import { t } from "../core/i18n.js";
import "./wl-error.js";

const WIDE = "(min-width: 1024px)";
let counter = 0;

function capitalize(text) {
  return text ? text[0].toLocaleUpperCase("fr-FR") + text.slice(1) : "";
}

// Le texte coupé en trois autour du passage (positions en points de code), ou null sans passage
// valable : l'extrait s'affiche alors entier, sans surlignage.
export function splitPassage(text, passage) {
  const { start, end } = passage ?? {};
  const chars = Array.from(text ?? "");
  const valid = Number.isInteger(start) && Number.isInteger(end);
  if (!valid || start < 0 || start >= end || end > chars.length) return null;
  return [
    chars.slice(0, start).join(""),
    chars.slice(start, end).join(""),
    chars.slice(end).join(""),
  ];
}

// Aide en bouton « i » (même motif que `wl-metric`) pour un texte hors d'une métrique.
function helpButton(label, text, id) {
  const button = element("button", "wl-metric-help-button");
  button.type = "button";
  button.setAttribute("aria-label", t("components.metric.help_for", { label }));
  button.setAttribute("aria-expanded", "false");
  button.setAttribute("aria-controls", id);
  button.append(icon("info"));
  const body = element("p", "wl-metric-help", text);
  body.id = id;
  body.hidden = true;
  button.addEventListener("click", () => {
    body.hidden = !body.hidden;
    button.setAttribute("aria-expanded", String(!body.hidden));
  });
  button.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !body.hidden) {
      event.stopPropagation();
      body.hidden = true;
      button.setAttribute("aria-expanded", "false");
    }
  });
  return [button, body];
}

export class WlSourcePanel extends HTMLElement {
  #uid = `wl-sources-${++counter}`;
  #dom = null;
  #sources = [];
  #items = new Map(); // n -> { toggle }
  #wide = null;
  #onWide = (event) => this.#syncOpen(event.matches);

  connectedCallback() {
    this.#build();
    this.#wide.addEventListener("change", this.#onWide);
    this.#syncOpen(this.#wide.matches);
  }

  disconnectedCallback() {
    this.#wide?.removeEventListener("change", this.#onWide);
  }

  get sources() {
    return this.#sources;
  }

  set sources(list) {
    this.#build();
    this.#sources = Array.isArray(list) ? list : [];
    const { title, empty, list: listNode, live } = this.#dom;
    this.#items.clear();
    listNode.replaceChildren(...this.#sources.map((source) => this.#render(source)));
    empty.hidden = this.#sources.length > 0;
    const count = this.#sources.length;
    title.textContent = count
      ? t(count < 2 ? "components.sources.summary_one" : "components.sources.summary_other", {
          n: formatInteger(count),
        })
      : t("components.sources.summary_empty");
    // Annonce polie des sources trouvées, avant la réponse (jamais pendant le flux de tokens).
    live.textContent = "";
    if (this.#sources.length) requestAnimationFrame(() => (live.textContent = title.textContent));
  }

  clear() {
    this.sources = [];
  }

  highlight(n) {
    for (const item of this.#dom?.list.children ?? []) {
      item.classList.toggle("is-linked", n !== null && Number(item.dataset.n) === n);
    }
  }

  open(n) {
    const toggle = this.#items.get(n)?.toggle;
    if (!toggle) return;
    this.#dom.root.open = true;
    if (toggle.getAttribute("aria-expanded") !== "true") toggle.click();
  }

  #build() {
    if (this.#dom) return;
    this.classList.add("wl-source-panel"); // garde les classes posées par l'écran
    this.#wide = matchMedia(WIDE);
    const root = element("details", "wl-sources");
    const summary = element("summary", "wl-sources-summary");
    const title = element("h2", "wl-sources-title", t("components.sources.summary_empty"));
    summary.append(title);
    summary.addEventListener("click", (event) => {
      if (this.#wide.matches) event.preventDefault(); // toujours ouvert en large (D-22)
    });
    const empty = element("p", "help wl-sources-empty", t("components.sources.empty"));
    const list = element("ol", "wl-sources-list");
    const live = element("div", "sr-only");
    live.setAttribute("role", "status");
    root.append(summary, empty, list, live);
    this.replaceChildren(root);
    this.#dom = { root, summary, title, empty, list, live };
    this.#syncOpen(this.#wide.matches);
  }

  #syncOpen(wide) {
    const { root, summary } = this.#dom;
    root.open = wide;
    root.classList.toggle("is-wide", wide);
    summary.tabIndex = wide ? -1 : 0; // sans bouton de repli en large : rien à focaliser
  }

  #render(source) {
    const item = element("li", "wl-source");
    item.dataset.n = String(source.n);
    const link = (n) => this.dispatchEvent(new CustomEvent("wl-source-link", { detail: { n } }));
    item.addEventListener("pointerenter", () => link(source.n));
    item.addEventListener("pointerleave", () => link(null));
    item.addEventListener("focusin", () => link(source.n));
    item.addEventListener("focusout", () => link(null));
    const head = element("p", "wl-source-head");
    head.append(
      element("span", "wl-source-num", `[${source.n}]`),
      element("strong", "wl-source-doc", source.document),
    );
    if (Number.isInteger(source.page)) {
      head.append(element("span", "wl-source-page", t("components.sources.page", { page: source.page })));
    }
    item.append(head);
    if (source.text === null || source.text === undefined) {
      item.append(...this.#goneNodes(source));
      return item;
    }

    const relevance = element("p", "wl-source-relevance");
    relevance.append(
      element("span", "wl-source-rel", capitalize(source.relevance_label)),
      element("span", "help", t("components.sources.rank", { rank: source.rank })),
    );
    const [button, body] = helpButton(
      t("components.sources.raw_label"),
      t("components.sources.raw_help", { score: formatNumber(source.raw_score) }),
      `${this.#uid}-raw-${source.n}`,
    );
    relevance.append(button);
    item.append(relevance, body);

    const quoteId = `${this.#uid}-quote-${source.n}`;
    let quote = this.#quote(source.text, null, false, quoteId);
    const problem = document.createElement("wl-error");
    problem.hidden = true;
    const toggle = element("button", "btn wl-source-open", t("components.sources.open"));
    toggle.type = "button";
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-controls", quoteId);
    const setLabel = (opened) => {
      toggle.textContent = t(opened ? "components.sources.close" : "components.sources.open");
      toggle.setAttribute(
        "aria-label",
        t(opened ? "components.sources.close_for" : "components.sources.open_for", {
          n: source.n,
          document: source.document,
        }),
      );
    };
    setLabel(false);
    const show = (text, passage, opened) => {
      const next = this.#quote(text, passage, opened, quoteId);
      quote.replaceWith(next);
      quote = next;
      toggle.setAttribute("aria-expanded", String(opened));
      setLabel(opened);
    };
    toggle.addEventListener("click", async () => {
      if (toggle.getAttribute("aria-expanded") === "true") return show(source.text, null, false);
      problem.error = null;
      toggle.disabled = true;
      toggle.setAttribute("aria-busy", "true");
      try {
        const chunk = await api.chunk(source.chunk_id);
        // Les positions valent pour le texte du serveur au moment de la recherche : un extrait
        // différent (il ne l'est jamais, les extraits ne changent pas) n'est pas surligné.
        const text = typeof chunk?.text === "string" ? chunk.text : source.text;
        show(text, text === source.text ? source.passage : null, true);
      } catch (failure) {
        if (failure instanceof ApiError && failure.envelope?.code === "chunk_not_found") {
          item.replaceChildren(head, ...this.#goneNodes(source)); // le texte n'existe plus
          // Liste remplacée pendant la requête : l'entrée n de la nouvelle liste reste.
          if (this.#items.get(source.n)?.toggle === toggle) this.#items.delete(source.n);
        } else {
          problem.error =
            failure instanceof ApiError && failure.envelope
              ? failure.envelope
              : { code: "internal", message: t("components.sources.open_failed") };
        }
      } finally {
        toggle.disabled = false;
        toggle.removeAttribute("aria-busy");
      }
    });
    item.append(quote, toggle, problem);
    this.#items.set(source.n, { toggle });
    return item;
  }

  // « extrait supprimé » : le document n'est plus dans la base, le texte n'existe plus (AD-7).
  #goneNodes(source) {
    const gone = element("p", "wl-source-gone");
    gone.append(icon("warning"), element("span", "", t("components.sources.deleted")));
    return [gone, element("p", "help", t("components.sources.deleted_help", { document: source.document }))];
  }

  #quote(text, passage, opened, id) {
    const quote = element("blockquote", "wl-source-quote");
    quote.id = id;
    const parts = opened ? splitPassage(text, passage) : null;
    if (parts) {
      const [before, marked, after] = parts;
      quote.append(
        document.createTextNode(before),
        element("mark", "wl-source-mark", marked),
        document.createTextNode(after),
      );
    } else {
      quote.append(document.createTextNode(text));
    }
    quote.classList.toggle("is-open", opened);
    return quote;
  }
}

if (!customElements.get("wl-source-panel")) customElements.define("wl-source-panel", WlSourcePanel);
