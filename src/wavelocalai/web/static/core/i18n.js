// Textes de l'interface (AD-20) : static/i18n/fr.json, un seul catalogue. Le HTML garde son texte
// français (la page se lit même si ce module échoue) ; `data-i18n`, `data-i18n-aria-label` et
// `data-i18n-title` nomment la clé qui le remplace, et un test compare les deux.

const ATTRIBUTES = [
  ["i18nAriaLabel", "aria-label"],
  ["i18nTitle", "title"],
];

let texts = {};
const warned = new Set();

export async function loadTexts(url = "/static/i18n/fr.json") {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Catalogue de textes indisponible (${response.status}).`);
  texts = await response.json();
}

function lookup(key) {
  let value = texts;
  for (const part of key.split(".")) {
    if (value === null || typeof value !== "object") return undefined;
    value = value[part];
  }
  return typeof value === "string" ? value : undefined;
}

// Le texte de `key`, `{nom}` remplacé par `vars.nom`. Une clé absente rend la clé, dite en console.
export function t(key, vars = {}) {
  const value = lookup(key);
  if (value === undefined) {
    if (!warned.has(key)) {
      warned.add(key);
      console.warn(`i18n : clé absente du catalogue : ${key}`);
    }
    return key;
  }
  return value.replace(/\{(\w+)\}/g, (match, name) => (name in vars ? String(vars[name]) : match));
}

// Applique le catalogue aux éléments `data-i18n*` sous `root`.
export function applyTexts(root = document) {
  for (const el of root.querySelectorAll("[data-i18n]")) {
    el.textContent = t(el.dataset.i18n);
  }
  for (const [dataName, attribute] of ATTRIBUTES) {
    const selector = `[data-${dataName.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)}]`;
    for (const el of root.querySelectorAll(selector)) {
      el.setAttribute(attribute, t(el.dataset[dataName]));
    }
  }
}
