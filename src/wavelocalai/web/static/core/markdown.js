// Rendu Markdown sûr de la réponse d'un modèle (UX-DR10). Le texte du modèle n'est jamais du HTML :
// ce module ne lit ni n'écrit `innerHTML`, il construit des nœuds (`createElement`, `textContent`),
// si bien que `<script>`, `<img onerror>` ou une entité arrivent à l'écran comme du texte.
//
// Sous-ensemble : paragraphes (retour à la ligne conservé), titres (rendus en paragraphe gras :
// l'écran n'a qu'un `h1` et la structure des titres n'appartient pas au modèle), listes à puces et
// numérotées (imbriquées par indentation), citations, ligne horizontale, bloc de code (``` ou ~~~,
// non fermé = code jusqu'à la fin, comme pendant le flux), code en ligne, gras, italique, liens
// `http:`, `https:` et `mailto:` seulement (les autres restent du texte). Tableaux et images : texte.

const BLOCK_TAGS = new Set(["P", "UL", "OL", "LI", "BLOCKQUOTE"]);
const FENCE = /^ {0,3}(`{3,}|~{3,})\s*[\w+#.-]*\s*$/;
const HEADING = /^ {0,3}(#{1,6})\s+(.*?)(?:\s+#+)?\s*$/;
const RULE = /^ {0,3}([-*_])(?:\s*\1){2,}\s*$/;
const QUOTE = /^ {0,3}>\s?(.*)$/;
const ITEM = /^( *)([-*+]|\d{1,9}[.)])\s+(.*)$/;
const INLINE =
  /(?<ticks>`+)(?<code>[\s\S]*?[^`])\k<ticks>(?!`)|\[(?<label>[^\]\n]+)\]\((?<href>[^)\s]+)\)|\*\*(?<strong>[^*\n]+?)\*\*|(?<![\w])__(?<strong2>[^_\n]+?)__(?![\w])|\*(?<em>[^*\s](?:[^*\n]*[^*\s])?)\*|(?<![\w])_(?<em2>[^_\s](?:[^_\n]*[^_\s])?)_(?![\w])/g;

// L'adresse d'un lien, si on peut la suivre sans risque ; sinon null.
export function safeHref(href) {
  try {
    const url = new URL(href);
    return ["http:", "https:", "mailto:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function text(value) {
  return document.createTextNode(value);
}

function node(tag, className) {
  const created = document.createElement(tag);
  if (className) created.className = className;
  return created;
}

// Texte brut dont les retours à la ligne deviennent des `<br>`.
function appendLines(parent, value) {
  value.split("\n").forEach((line, index) => {
    if (index) parent.append(node("br"));
    if (line) parent.append(text(line));
  });
}

function appendInline(parent, source) {
  let last = 0;
  for (const match of source.matchAll(INLINE)) {
    appendLines(parent, source.slice(last, match.index));
    last = match.index + match[0].length;
    const found = match.groups;
    if (found.code !== undefined) {
      const code = node("code");
      code.textContent = found.code.replace(/\n/g, " ").trim() || found.code;
      parent.append(code);
    } else if (found.label !== undefined) {
      const href = safeHref(found.href);
      if (href === null) {
        appendLines(parent, match[0]); // adresse refusée : le texte tel quel
      } else {
        const link = node("a");
        link.href = href;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        appendInline(link, found.label);
        parent.append(link);
      }
    } else if (found.strong !== undefined || found.strong2 !== undefined) {
      const strong = node("strong");
      appendInline(strong, found.strong ?? found.strong2);
      parent.append(strong);
    } else {
      const em = node("em");
      appendInline(em, found.em ?? found.em2);
      parent.append(em);
    }
  }
  appendLines(parent, source.slice(last));
}

const startsBlock = (line) =>
  FENCE.test(line) || HEADING.test(line) || RULE.test(line) || QUOTE.test(line) || ITEM.test(line);

function renderBlocks(lines, parent) {
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    const fence = FENCE.exec(line);
    if (fence) {
      const mark = fence[1];
      const body = [];
      i++;
      while (i < lines.length && !new RegExp(`^ {0,3}${mark[0]}{${mark.length},}\\s*$`).test(lines[i])) {
        body.push(lines[i++]);
      }
      i++; // la clôture (absente pendant le flux : le code court jusqu'à la fin)
      const pre = node("pre", "md-code");
      const code = node("code");
      code.textContent = body.join("\n");
      pre.append(code);
      parent.append(pre);
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading) {
      const p = node("p", `md-heading md-heading-${heading[1].length}`);
      const strong = node("strong");
      appendInline(strong, heading[2]);
      p.append(strong);
      parent.append(p);
      i++;
      continue;
    }
    if (RULE.test(line)) {
      parent.append(node("hr"));
      i++;
      continue;
    }
    if (QUOTE.test(line)) {
      const quoted = [];
      while (i < lines.length && QUOTE.test(lines[i])) quoted.push(QUOTE.exec(lines[i++])[1]);
      const quote = node("blockquote");
      renderBlocks(quoted, quote);
      parent.append(quote);
      continue;
    }
    const item = ITEM.exec(line);
    if (item) {
      i = renderList(lines, i, parent);
      continue;
    }
    const paragraph = [];
    while (i < lines.length && lines[i].trim() && !(paragraph.length && startsBlock(lines[i]))) {
      paragraph.push(lines[i++].trim());
    }
    const p = node("p");
    appendInline(p, paragraph.join("\n"));
    parent.append(p);
  }
}

// Une liste : les éléments de même retrait et leurs lignes plus indentées (sous-listes, suite).
function renderList(lines, start, parent) {
  const first = ITEM.exec(lines[start]);
  const base = first[1].length;
  const ordered = /^\d/.test(first[2]);
  const list = node(ordered ? "ol" : "ul");
  let i = start;
  while (i < lines.length) {
    const match = ITEM.exec(lines[i]);
    if (!match || match[1].length !== base || /^\d/.test(match[2]) !== ordered) break;
    const content = [match[3]];
    i++;
    while (i < lines.length) {
      const next = lines[i];
      if (!next.trim()) {
        // Une ligne vide ferme l'élément ; la liste continue si l'élément suivant est de même retrait.
        let peek = i;
        while (peek < lines.length && !lines[peek].trim()) peek++;
        if (ITEM.exec(lines[peek] ?? "")?.[1].length === base) i = peek;
        break;
      }
      const indent = /^ */.exec(next)[0].length;
      if (indent <= base) break;
      content.push(next.slice(Math.min(indent, base + 2)));
      i++;
    }
    const li = node("li");
    const [head, ...rest] = content;
    appendInline(li, head);
    if (rest.length) renderBlocks(rest, li);
    list.append(li);
  }
  parent.append(list);
  return i;
}

// Le texte en Markdown -> un fragment de nœuds sûrs.
export function renderMarkdown(source) {
  const fragment = document.createDocumentFragment();
  renderBlocks(String(source ?? "").replace(/\r\n?/g, "\n").split("\n"), fragment);
  return fragment;
}

// Où poser le texte qui arrive entre deux rendus : au bout du dernier bloc de texte, pour qu'il
// prolonge la phrase en cours au lieu de s'afficher sur une ligne à part.
export function tailHost(root) {
  let host = root;
  while (host.lastElementChild && BLOCK_TAGS.has(host.lastElementChild.tagName)) {
    host = host.lastElementChild;
  }
  const last = host.lastElementChild;
  if (last && last.tagName === "PRE") return last.firstElementChild ?? last;
  return host;
}
