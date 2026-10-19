// Détail d'une note (story 7.3, UX-DR11, UX-DR29) : la région « Détail », sous le tableau, que le bouton
// d'un score ouvre (`aria-expanded`, focus sur son titre ; « Fermer » rend le focus au bouton).
//
// - Fidélité : « 7 affirmations : 6 appuyées, 1 non appuyée », puis un verdict par affirmation (le mot,
//   puis l'icône) avec l'extrait d'appui cité (`support` = numéro `n` de l'événement `sources`).
// - Pertinence : la raison et les questions que le juge a retrouvées depuis la réponse.
// - Précision du contexte : la raison et les extraits que le juge a jugés utiles.
// - Un jeu de questions : une section par question ; la réponse évaluée est repliée.
// Tout texte venu d'un document, d'une question ou d'une réponse est posé par `textContent`. Le
// compte d'affirmations est un dénombrement des verdicts du serveur, jamais une note.

import { element, icon } from "../core/dom.js";
import { plural } from "../core/format.js";
import { t } from "../core/i18n.js";
import { bareReason, STOPPED_REASON } from "./eval-model.js";

const VERDICT_ICON = { "appuyée": "check", "non appuyée": "help", "contredite": "error" };
const NBSP = " ";

function sourceOf(sources, n) {
  return sources.find((source) => source.n === n) ?? null;
}

function sourceLine(sources, n) {
  const box = element("p", "eval-support");
  if (typeof n !== "number") {
    box.textContent = t("evaluation.detail.support_none");
    return box;
  }
  const source = sourceOf(sources, n);
  if (!source) {
    box.textContent = t("evaluation.detail.support_gone", { n });
    return box;
  }
  const where = [source.document, source.page ? `p.${NBSP}${source.page}` : null].filter(Boolean).join(", ");
  box.append(element("strong", "", t("evaluation.detail.support", { n })), where ? ` (${where})` : "");
  if (source.text) box.append(element("span", "eval-support-text", source.text));
  return box;
}

function claimsSummary(verdicts) {
  const tally = (word) => verdicts.filter((item) => item.verdict === word).length;
  const parts = [
    plural("evaluation.detail.supported", tally("appuyée")),
    plural("evaluation.detail.unsupported", tally("non appuyée")),
    plural("evaluation.detail.contradicted", tally("contredite")),
  ];
  return `${plural("evaluation.detail.claims", verdicts.length)}${NBSP}: ${parts.join(", ")}`;
}

function faithfulness(note, sources) {
  const parts = [];
  const verdicts = Array.isArray(note.verdicts) ? note.verdicts : [];
  if (!verdicts.length) return [element("p", "help", t("evaluation.detail.no_verdicts"))];
  parts.push(element("p", "eval-claims-summary", claimsSummary(verdicts)));
  const list = element("ul", "eval-claims");
  for (const item of verdicts) {
    const word = Object.hasOwn(VERDICT_ICON, item.verdict) ? item.verdict : "non appuyée";
    const li = element("li", "eval-claim");
    li.dataset.verdict = word;
    const head = element("p", "eval-claim-head");
    head.append(icon(VERDICT_ICON[word]), element("strong", "eval-verdict", t(`evaluation.detail.verdict.${word}`)), " ");
    head.append(element("span", "eval-claim-text", item.claim ?? ""));
    li.append(head, sourceLine(sources, item.support));
    if (item.reason) li.append(element("p", "help", t("evaluation.detail.reason", { reason: item.reason })));
    list.append(li);
  }
  parts.push(list);
  return parts;
}

function relevance(note) {
  const parts = [];
  if (note.reason) parts.push(element("p", "help", t("evaluation.detail.reason", { reason: note.reason })));
  if (Array.isArray(note.questions) && note.questions.length) {
    parts.push(element("h4", "eval-detail-sub", t("evaluation.detail.retrieved")));
    const list = element("ul", "eval-retrieved");
    list.append(...note.questions.map((text) => element("li", "", text)));
    parts.push(list);
  }
  return parts;
}

function precision(note, sources) {
  const parts = [];
  if (note.reason) parts.push(element("p", "help", t("evaluation.detail.reason", { reason: note.reason })));
  parts.push(element("h4", "eval-detail-sub", t("evaluation.detail.useful")));
  const useful = Array.isArray(note.useful) ? note.useful : [];
  if (!useful.length) {
    parts.push(element("p", "help", t("evaluation.detail.useful_none")));
    return parts;
  }
  const list = element("ul", "eval-useful");
  for (const n of useful) {
    const li = element("li", "");
    li.append(sourceLine(sources, n));
    list.append(li);
  }
  parts.push(list);
  return parts;
}

const BY_METRIC = { faithfulness, relevance, context_precision: precision };

function entryBody(metric, entry, scoreText) {
  const body = element("div", "eval-detail-entry");
  const { note } = entry;
  if (!note) {
    body.append(element("p", "help", t("evaluation.detail.not_evaluated", { reason: entry.missing ?? STOPPED_REASON })));
  } else if (note.score === null) {
    body.append(
      element("p", "help", t("evaluation.detail.not_evaluated", { reason: bareReason(note.reason) || t("evaluation.results.reason_unknown") })),
    );
  } else {
    body.append(element("p", "eval-detail-score", t("evaluation.detail.score", { score: scoreText(note.score) })));
    body.append(...BY_METRIC[metric](note, entry.sources));
  }
  const answer = element("details", "eval-answer");
  answer.append(element("summary", "", t("evaluation.detail.answer")));
  const text = entry.answer?.text;
  answer.append(element("p", "eval-answer-text", text ?? t("evaluation.detail.answer_none")));
  body.append(answer);
  return body;
}

export function detailView(uid, { scoreText }) {
  const title = element("h3", "eval-detail-title");
  title.id = `${uid}-detail-title`;
  title.tabIndex = -1;
  const close = element("button", "btn eval-detail-close", t("evaluation.detail.close"));
  close.type = "button";
  const head = element("div", "eval-detail-head");
  head.append(title, close);
  const body = element("div", "eval-detail-body");
  const el = element("section", "eval-detail");
  el.setAttribute("aria-labelledby", title.id);
  el.hidden = true;
  el.append(head, body);

  let current = null; // { lane, metric, trigger }
  let heading = () => "";

  function paint(model) {
    title.textContent = heading(current);
    const { entries } = model.detail(current.lane, current.metric);
    if (entries.length === 1) {
      body.replaceChildren(entryBody(current.metric, entries[0], scoreText));
      return;
    }
    body.replaceChildren(
      ...entries.map((entry) => {
        const section = element("details", "eval-detail-question");
        section.open = false;
        section.append(element("summary", "", `${t("evaluation.detail.question", { n: entry.index + 1 })} · ${entry.question}`));
        section.append(entryBody(current.metric, entry, scoreText));
        return section;
      }),
    );
  }

  return {
    el,
    get open() {
      return current !== null;
    },
    get target() {
      return current;
    },
    // `describe({ lane, metric })` : le titre « Qwen 3.5 2B · Fidélité ».
    show(target, model, describe) {
      heading = describe;
      current = target;
      el.hidden = false;
      paint(model);
      title.focus();
    },
    // Les notes arrivent encore : le détail ouvert se met à jour, sans reprendre le focus. Les sections
    // d'un jeu de questions gardent leur état ouvert ou fermé.
    refresh(model) {
      if (!current) return;
      const opened = [...body.querySelectorAll(".eval-detail-question")].map((node) => node.open);
      const answers = [...body.querySelectorAll(".eval-answer")].map((node) => node.open);
      paint(model);
      body.querySelectorAll(".eval-detail-question").forEach((node, index) => (node.open = opened[index] ?? false));
      body.querySelectorAll(".eval-answer").forEach((node, index) => (node.open = answers[index] ?? false));
    },
    hide({ restoreFocus = true } = {}) {
      const trigger = current?.trigger;
      current = null;
      el.hidden = true;
      body.replaceChildren();
      if (restoreFocus) trigger?.();
    },
    onClose(handler) {
      close.addEventListener("click", handler);
    },
  };
}
