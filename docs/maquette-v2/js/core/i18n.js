// Textes de l'interface (repris de static/core/i18n.js). Le catalogue est la fusion de :
// - i18n/fr.json, recopié tel quel du front livré ;
// - i18n/maquette.fr.json, les textes communs que la maquette ajoute (coquille, états, panneau) ;
// - i18n/screens/<écran>.fr.json, chargé par le routeur à la première visite d'un écran.
// Une clé absente rend la clé elle-même, dite une fois en console (avertissement).

const ATTRIBUTES = [
  ["i18nAriaLabel", "aria-label"],
  ["i18nTitle", "title"],
];

const ROOT = new URL("../../i18n/", import.meta.url);
let texts = {};
const warned = new Set();

function merge(target, source) {
  for (const [key, value] of Object.entries(source)) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      target[key] = merge(target[key] && typeof target[key] === "object" ? target[key] : {}, value);
    } else {
      target[key] = value;
    }
  }
  return target;
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Catalogue de textes indisponible (${response.status}) : ${url}`);
  return response.json();
}

// Charge le catalogue commun (fr.json puis maquette.fr.json, qui peut le compléter).
export async function loadTexts() {
  const [base, extra] = await Promise.all([
    fetchJson(new URL("fr.json", ROOT)),
    fetchJson(new URL("maquette.fr.json", ROOT)),
  ]);
  texts = merge(merge({}, base), extra);
}

// Ajoute les textes d'un écran (`i18n/screens/<écran>.fr.json`).
export async function loadScreenTexts(screen) {
  addTexts(await fetchJson(new URL(`screens/${screen}.fr.json`, ROOT)));
}

export function addTexts(extra) {
  merge(texts, extra);
}

function lookup(key) {
  let value = texts;
  for (const part of key.split(".")) {
    if (value === null || typeof value !== "object") return undefined;
    value = value[part];
  }
  return typeof value === "string" ? value : undefined;
}

export function has(key) {
  return lookup(key) !== undefined;
}

// Le texte de `key`, `{nom}` remplacé par `vars.nom`.
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

// Accord simple : `<key>_one` pour 1, `<key>_many` sinon ; `{count}` est passé tel quel.
export function plural(key, count, vars = {}) {
  return t(`${key}_${count === 1 ? "one" : "many"}`, { count, ...vars });
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
