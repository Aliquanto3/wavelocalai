// Citations vérifiées de la Discussion (UX-DR11, story 4.6) : seuls les marqueurs `[n]` que
// l'événement `citations` confirme deviennent des boutons dans le texte de la réponse. Le serveur a
// vérifié que `n` désigne une source de la réponse ; le front ne fabrique aucun marqueur. Sans
// `citations`, ou pour un marqueur que le serveur n'a pas confirmé (`[9]` pour trois sources), le
// texte du modèle reste tel quel, sans bouton. Survoler ou focaliser `[n]` met la source en
// évidence dans le panneau, et inversement ; un clic ouvre l'extrait.

import { element } from "../core/dom.js";
import { t } from "../core/i18n.js";

const MARKER = /(\[\d{1,3}\])/;
const SKIPPED = new Set(["BUTTON", "A", "CODE", "PRE"]); // un lien ou du code n'est pas une citation

// Les textes de `body` dont un marqueur `[n]` est confirmé par `record.citations` deviennent des
// boutons `docs-cite` (classe `is-linked` quand la source correspondante est en évidence).
// `hooks` : `{ enter(record, n), leave(record), click(record, n) }`.
export function decorateCitations(body, record, hooks) {
  const confirmed = new Map((record.citations ?? []).map((item) => [item.marker, item.n]));
  if (!confirmed.size) return;
  const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT, {
    acceptNode: (node) =>
      SKIPPED.has(node.parentElement?.tagName) || !MARKER.test(node.data)
        ? NodeFilter.FILTER_REJECT
        : NodeFilter.FILTER_ACCEPT,
  });
  const texts = [];
  while (walker.nextNode()) texts.push(walker.currentNode);
  for (const node of texts) {
    const fragment = document.createDocumentFragment();
    let changed = false;
    for (const part of node.data.split(MARKER)) {
      const found = /^\[(\d{1,3})\]$/.exec(part);
      const n = found ? confirmed.get(Number(found[1])) : undefined;
      const source = n === undefined ? null : record.sources.find((candidate) => candidate.n === n);
      if (!source) {
        if (part) fragment.append(part);
        continue;
      }
      changed = true;
      fragment.append(marker(part, n, source, record, hooks));
    }
    if (changed) node.replaceWith(fragment);
  }
}

function marker(text, n, source, record, hooks) {
  // Nom accessible : le texte visible « [1] » d'abord, puis la source (WCAG 2.5.3).
  const where = Number.isInteger(source.page)
    ? t("discussion.cite_label_page", { n, document: source.document, page: source.page })
    : t("discussion.cite_label", { n, document: source.document });
  const button = element("button", "docs-cite", text);
  button.type = "button";
  button.dataset.n = String(n);
  button.append(element("span", "sr-only", ` ${where}`));
  const enter = () => hooks.enter(record, n);
  const leave = () => hooks.leave(record);
  button.addEventListener("mouseenter", enter);
  button.addEventListener("mouseleave", leave);
  button.addEventListener("focus", enter);
  button.addEventListener("blur", leave);
  button.addEventListener("click", () => hooks.click(record, n));
  return button;
}

// Met en évidence les marqueurs de la source `n` dans le texte de la réponse (`null` : aucun).
export function linkMarkers(body, n) {
  for (const button of body?.querySelectorAll(".docs-cite") ?? []) {
    button.classList.toggle("is-linked", n !== null && Number(button.dataset.n) === n);
  }
}
