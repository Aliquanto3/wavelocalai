// Commun aux trois écrans du module Documents (Discussion, Base documentaire, Évaluation de la
// qualité) : la base documentaire simulée (ce que le serveur garderait), le panneau de sources
// (UX-DR11, `wl-source-panel` n'existe pas encore dans les composants communs) et de petits
// utilitaires de scénario. Ce n'est pas un écran : aucune route ne le charge.
//
// La base vit dans le store sous `ragBase` : `{documents, settings, reranker}`. Les trois écrans la
// lisent et s'y abonnent, si bien qu'un import fait dans « Base documentaire » se voit tout de suite
// dans « Discussion » (compteur, documents interrogeables). Chaque scénario pose la base qu'il
// attend (`setBasePreset`) : `ctx.reset()` ne la remet pas à zéro.

import { loadCopy } from "../core/data.js";
import { element, icon } from "../core/dom.js";
import { formatDate, formatInteger, formatNumber, formatTime } from "../core/format.js";
import { loadScreenTexts, plural, t } from "../core/i18n.js";
import { store } from "../core/store.js";

// --- Préparation (feuille de style et textes communs, chargés une seule fois) ---------------------

let prepared = null;

export function prepare() {
  prepared ??= Promise.all([
    loadScreenTexts("documents-commun"),
    new Promise((resolve) => {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = new URL("../../css/screens/documents-commun.css", import.meta.url).href;
      link.onload = link.onerror = () => resolve();
      document.head.append(link);
    }),
  ]);
  return prepared;
}

// --- Utilitaires de scénario ----------------------------------------------------------------------

export const speedOf = () => store.get().maquette.speed || 1;

export function waitUntil(condition, timeoutMs = 20000) {
  return new Promise((resolve, reject) => {
    const started = performance.now();
    const check = () => {
      if (condition()) return resolve();
      if (performance.now() - started > timeoutMs) return reject(new Error("Scénario : état jamais atteint"));
      setTimeout(check, 30);
    };
    check();
  });
}

export const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms / speedOf()));

// --- Base documentaire simulée --------------------------------------------------------------------

export function getBase() {
  return store.get().ragBase ?? null;
}

export async function setBasePreset(name = "complet") {
  const data = await loadCopy("base-documentaire.json");
  const ids = data.presets[name] ?? data.presets.complet;
  const documents = ids.map((id) => {
    const doc = data.documents.find((candidate) => candidate.id === id);
    return { status: "ready", embedding: data.settings.embedding, ...doc };
  });
  store.set({ ragBase: { documents, settings: data.settings, reranker: data.reranker, embeddingModels: data.embedding_models } });
}

// Au premier montage d'un écran du module : la base complète, si aucun scénario n'en a posé une.
export async function ensureBase() {
  if (!getBase()) await setBasePreset("complet");
  return getBase();
}

// Modifie une copie de la base puis la publie (les trois écrans s'y abonnent).
export function updateBase(mutate) {
  const next = structuredClone(getBase());
  mutate(next);
  store.set({ ragBase: next });
}

export function subscribeBase(listener) {
  return store.select((state) => state.ragBase, (base) => base && listener(base));
}

// Seuls les documents `ready` s'interrogent et se comptent ; un document `indexing` n'est pas prêt.
export function baseCounts(base = getBase()) {
  const ready = base.documents.filter((doc) => doc.status === "ready");
  return {
    documents: ready.length,
    chunks: ready.reduce((sum, doc) => sum + doc.chunks, 0),
    indexing: base.documents.filter((doc) => doc.status === "indexing").length,
  };
}

export const documentsLabel = (count) => plural("docs.documents", count, { count: formatInteger(count) });
export const chunksLabel = (count) => plural("docs.chunks", count, { count: formatInteger(count) });

export function formatDateTime(iso) {
  return `${formatDate(iso)} ${formatTime(iso)}`;
}

export function embeddingName(base, tag) {
  return base.embeddingModels.find((model) => model.tag === tag)?.name ?? tag;
}

// --- Aide en bouton (même motif que `wl-metric`, pour un texte hors d'une métrique) ----------------

let helpCounter = 0;

export function helpToggle(label, text) {
  const id = `docs-help-${++helpCounter}`;
  const root = element("span", "docs-help");
  const button = element("button", "docs-help-button");
  button.type = "button";
  button.setAttribute("aria-label", t("docs.help_for", { label }));
  button.setAttribute("aria-expanded", "false");
  button.setAttribute("aria-controls", id);
  button.append(icon("info"));
  const body = element("span", "docs-help-text help", text);
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
  root.append(button, body);
  return root;
}

// --- Panneau de sources (UX-DR11) -----------------------------------------------------------------
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

let panelCounter = 0;

function capitalize(text) {
  return text ? text[0].toLocaleUpperCase("fr-FR") + text.slice(1) : text;
}

function buildQuote(source, opened) {
  const quote = element("blockquote", "docs-source-quote");
  const text = source.text ?? "";
  const passage = source.passage && text.includes(source.passage) ? source.passage : null;
  if (!opened || !passage) {
    quote.append(document.createTextNode(text));
    return quote;
  }
  const at = text.indexOf(passage);
  const mark = element("mark", "docs-source-mark", passage);
  quote.append(document.createTextNode(text.slice(0, at)), mark, document.createTextNode(text.slice(at + passage.length)));
  return quote;
}

export function createSourcePanel({ prefix = "docs.sources", autoOpen = true } = {}) {
  const uid = `docs-sources-${++panelCounter}`;
  const root = element("details", "docs-sources");
  const summary = element("summary", "docs-sources-summary");
  const title = element("span", "docs-sources-title");
  summary.append(title);
  const empty = element("p", "help docs-sources-empty", t(`${prefix}.empty`));
  const list = element("ol", "docs-sources-list");
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
      const toggle = item.querySelector(".docs-source-open");
      if (toggle && toggle.getAttribute("aria-expanded") !== "true") toggle.click();
    },
    clear() {
      panel.setSources([]);
    },
  };

  function renderSource(source) {
    const item = element("li", "docs-source");
    item.dataset.n = String(source.n);
    const head = element("p", "docs-source-head");
    head.append(
      element("span", "docs-source-num", `[${source.n}]`),
      element("strong", "docs-source-doc", source.document),
      element("span", "docs-source-page", t("docs.sources.page", { page: source.page })),
    );
    item.append(head);

    if (source.text === null) {
      const gone = element("p", "docs-source-gone");
      gone.append(icon("warning"), element("span", "", t("docs.sources.deleted")));
      item.append(gone, element("p", "help", t("docs.sources.deleted_help", { document: source.document })));
    } else {
      const relevance = element("p", "docs-source-relevance");
      relevance.append(
        element("span", "docs-rel", capitalize(source.relevance_label)),
        element("span", "help", t("docs.sources.rank", { rank: source.rank })),
        helpToggle(
          t("docs.sources.raw_label"),
          t("docs.sources.raw_help", { score: formatNumber(source.raw_score) }),
        ),
      );
      item.append(relevance);
      let quote = buildQuote(source, false);
      item.append(quote);
      const toggle = element("button", "btn docs-source-open", t("docs.sources.open"));
      toggle.type = "button";
      toggle.setAttribute("aria-expanded", "false");
      toggle.setAttribute("aria-label", t("docs.sources.open_for", { n: source.n, document: source.document }));
      toggle.setAttribute("aria-controls", `${uid}-quote-${source.n}`);
      quote.id = `${uid}-quote-${source.n}`;
      toggle.addEventListener("click", () => {
        const opened = toggle.getAttribute("aria-expanded") !== "true";
        toggle.setAttribute("aria-expanded", String(opened));
        toggle.firstChild.data = opened ? t("docs.sources.close") : t("docs.sources.open");
        toggle.setAttribute(
          "aria-label",
          t(opened ? "docs.sources.close_for" : "docs.sources.open_for", { n: source.n, document: source.document }),
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
