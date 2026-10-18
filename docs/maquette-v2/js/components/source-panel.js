// Panneau de sources (UX-DR11), commun à la Discussion et à l'Évaluation de la qualité.
//
// Liste numérotée : document, page, pertinence en clair (rang + libellé, score brut en aide),
// extrait cité replié à trois lignes, « Ouvrir l'extrait » pour l'extrait entier avec son passage
// surligné. Une source sans texte (`text: null`) dit « extrait supprimé ». À droite dès 1 024 px
// (le parent le place), dessous et replié en deçà.
//
//   panel.setSources(liste)     sources de l'événement `sources` (ou d'une réponse rouverte)
//   panel.highlight(n)          met la source n en évidence (survol d'un marqueur [n])
//   panel.open(n)               ouvre l'extrait de la source n
//   panel.onLink = (n|null) => …   appelé quand la personne survole ou focalise une source
//
// `prefix` : clés de textes du résumé (`summary_empty`, `summary_one|many`, `empty`) ; par défaut
// `components.sources` (« N sources utilisées »), `docs.extracts` pour les extraits communs.

import { element, icon } from "../core/dom.js";
import { formatInteger, formatNumber } from "../core/format.js";
import { plural, t } from "../core/i18n.js";
import { helpToggle } from "./help-toggle.js";

let panelCounter = 0;

function capitalize(text) {
  return text ? text[0].toLocaleUpperCase("fr-FR") + text.slice(1) : text;
}

function buildQuote(source, opened) {
  const quote = element("blockquote", "wl-source-quote");
  const text = source.text ?? "";
  const passage = source.passage && text.includes(source.passage) ? source.passage : null;
  if (!opened || !passage) {
    quote.append(document.createTextNode(text));
    return quote;
  }
  const at = text.indexOf(passage);
  const mark = element("mark", "wl-source-mark", passage);
  quote.append(document.createTextNode(text.slice(0, at)), mark, document.createTextNode(text.slice(at + passage.length)));
  return quote;
}

export function createSourcePanel({ prefix = "components.sources", autoOpen = true } = {}) {
  const uid = `wl-sources-${++panelCounter}`;
  const root = element("details", "wl-sources");
  const summary = element("summary", "wl-sources-summary");
  const title = element("span", "wl-sources-title");
  summary.append(title);
  const empty = element("p", "help wl-sources-empty", t(`${prefix}.empty`));
  const list = element("ol", "wl-sources-list");
  const live = element("div", "sr-only");
  live.setAttribute("role", "status");
  root.append(summary, empty, list, live);

  const panel = {
    root,
    onLink: null,
    sources: [],
    setSources(sources) {
      panel.sources = Array.isArray(sources) ? sources : [];
      list.replaceChildren(...panel.sources.map(renderSource));
      empty.hidden = panel.sources.length > 0;
      const count = panel.sources.length;
      title.textContent = count ? plural(`${prefix}.summary`, count, { count: formatInteger(count) }) : t(`${prefix}.summary_empty`);
      // Annonce polie des sources trouvées, avant la réponse (jamais pendant le flux de tokens).
      live.textContent = "";
      if (count) requestAnimationFrame(() => (live.textContent = title.textContent));
    },
    highlight(n) {
      for (const item of list.children) item.classList.toggle("is-linked", n !== null && Number(item.dataset.n) === n);
    },
    open(n) {
      const item = list.querySelector(`[data-n="${n}"]`);
      if (!item) return;
      root.open = true;
      const toggle = item.querySelector(".wl-source-open");
      if (toggle && toggle.getAttribute("aria-expanded") !== "true") toggle.click();
    },
    clear() {
      panel.setSources([]);
    },
  };

  function renderSource(source) {
    const item = element("li", "wl-source");
    item.dataset.n = String(source.n);
    const head = element("p", "wl-source-head");
    head.append(
      element("span", "wl-source-num", `[${source.n}]`),
      element("strong", "wl-source-doc", source.document),
      element("span", "wl-source-page", t("components.sources.page", { page: source.page })),
    );
    item.append(head);

    if (source.text === null) {
      const gone = element("p", "wl-source-gone");
      gone.append(icon("warning"), element("span", "", t("components.sources.deleted")));
      item.append(gone, element("p", "help", t("components.sources.deleted_help", { document: source.document })));
    } else {
      const relevance = element("p", "wl-source-relevance");
      relevance.append(
        element("span", "wl-source-rel", capitalize(source.relevance_label)),
        element("span", "help", t("components.sources.rank", { rank: source.rank })),
        helpToggle(
          t("components.sources.raw_label"),
          t("components.sources.raw_help", { score: formatNumber(source.raw_score) }),
        ),
      );
      item.append(relevance);
      let quote = buildQuote(source, false);
      item.append(quote);
      const toggle = element("button", "btn wl-source-open", t("components.sources.open"));
      toggle.type = "button";
      toggle.setAttribute("aria-expanded", "false");
      toggle.setAttribute("aria-label", t("components.sources.open_for", { n: source.n, document: source.document }));
      toggle.setAttribute("aria-controls", `${uid}-quote-${source.n}`);
      quote.id = `${uid}-quote-${source.n}`;
      toggle.addEventListener("click", () => {
        const opened = toggle.getAttribute("aria-expanded") !== "true";
        toggle.setAttribute("aria-expanded", String(opened));
        toggle.firstChild.data = opened ? t("components.sources.close") : t("components.sources.open");
        toggle.setAttribute(
          "aria-label",
          t(opened ? "components.sources.close_for" : "components.sources.open_for", { n: source.n, document: source.document }),
        );
        const next = buildQuote(source, opened);
        next.id = quote.id;
        next.classList.toggle("is-open", opened);
        quote.replaceWith(next);
        quote = next;
      });
      item.append(toggle);
    }

    const link = (n) => () => panel.onLink?.(n);
    item.addEventListener("mouseenter", link(source.n));
    item.addEventListener("mouseleave", link(null));
    item.addEventListener("focusin", link(source.n));
    item.addEventListener("focusout", link(null));
    return item;
  }

  if (autoOpen) {
    const wide = matchMedia("(min-width: 1024px)");
    root.open = wide.matches;
    wide.addEventListener("change", (event) => {
      root.open = event.matches;
    });
  }
  panel.setSources([]);
  return panel;
}
