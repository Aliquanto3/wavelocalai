// Textes de l'interface (AD-20) : un fichier par domaine dans static/i18n/fr/, fusionnés ici sous
// les mêmes clés qu'un catalogue unique (`t("home.lead")` ne dépend pas du fichier qui la porte).
// Le HTML garde son texte français (la page se lit même si ce module échoue) ; `data-i18n`,
// `data-i18n-aria-label` et `data-i18n-title` nomment la clé qui le remplace, et un test compare
// les deux.
//
// Mode d'emploi : une story qui livre un écran écrit ses textes dans son propre fichier
// (`i18n/fr/<écran>.json`, clé de premier niveau `<écran>`) et ajoute son nom à `TEXT_FILES`
// ci-dessous, la seule liste. Deux fichiers qui portent la même clé de premier niveau font échouer
// `tests/v2/unit/test_static_split.py` (jamais d'écrasement silencieux) ; le chargement échoue aussi.

const ATTRIBUTES = [
  ["i18nAriaLabel", "aria-label"],
  ["i18nTitle", "title"],
];

// Les fichiers de `static/i18n/fr/` (sans `.json`), chargés en parallèle.
export const TEXT_FILES = [
  "shell",
  "home",
  "components",
  "chat",
  "discussion",
  "docs",
  "arena",
  "models",
  "sobriety",
  "evaluation",
];

let texts = {};
const warned = new Set();

export async function loadTexts(base = "/static/i18n/fr") {
  const files = await Promise.all(
    TEXT_FILES.map(async (name) => {
      const response = await fetch(`${base}/${name}.json`);
      if (!response.ok) throw new Error(`Catalogue de textes indisponible (${name}, ${response.status}).`);
      return [name, await response.json()];
    }),
  );
  const merged = {};
  for (const [name, part] of files) {
    for (const key of Object.keys(part)) {
      if (key in merged) throw new Error(`Clé de textes déclarée deux fois : ${key} (${name}.json).`);
      merged[key] = part[key];
    }
  }
  texts = merged;
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
