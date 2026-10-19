// Formats d'affichage `fr-FR` par `Intl` (UX-DR15, EXPERIENCE.md « Chiffres »). Le front ne calcule
// aucune mesure (AD-20) : il met en forme ce que l'API a mesuré. Un inconnu n'est jamais un 0 :
// `null`, `undefined` et `NaN` donnent « inconnu » (ou « non évalué » pour un score).
//
// Virgule décimale, espace fine insécable entre les milliers, au plus trois chiffres significatifs ;
// une espace insécable sépare le nombre de son unité.

import { t } from "./i18n.js";

const LOCALE = "fr-FR";
const NBSP = " ";

const formatters = new Map();

// Un `Intl.NumberFormat` ou `Intl.DateTimeFormat` par jeu d'options, construit une fois.
function intl(key, options, Formatter = Intl.NumberFormat) {
  let formatter = formatters.get(key);
  if (!formatter) {
    formatter = new Formatter(LOCALE, options);
    formatters.set(key, formatter);
  }
  return formatter;
}

function isMeasure(value) {
  return typeof value === "number" && Number.isFinite(value);
}

export function formatUnknown() {
  return t("format.unknown");
}

// Nombre à trois chiffres significatifs au plus : 0,66 ; 13,8 ; 128.
export function formatNumber(value) {
  if (!isMeasure(value)) return formatUnknown();
  return intl("sig3", { maximumSignificantDigits: 3 }).format(value);
}

// Entier exact avec milliers (nombre de tokens, d'extraits, de réponses).
export function formatInteger(value) {
  if (!isMeasure(value)) return formatUnknown();
  return intl("int", { maximumFractionDigits: 0 }).format(value);
}

function withUnit(text, unit) {
  return `${text}${NBSP}${unit}`;
}

const CO2_STEPS = [
  { unit: "mg", per_mg: 1 },
  { unit: "g", per_mg: 1000 },
  { unit: "kg", per_mg: 1_000_000 },
];

// L'unité qui convient à `mg` : mg sous 1 g, g au-delà, kg au-delà de 1 000 g. L'arrondi à trois
// chiffres est fait avant le choix : 999,6 mg devient « 1 g », jamais « 1 000 mg ».
export function co2Unit(mg) {
  const rounded = Number(Math.abs(mg).toPrecision(3));
  if (rounded >= 1_000_000) return "kg";
  if (rounded >= 1000) return "g";
  return "mg";
}

// CO2 en milligrammes -> « 1,8 mg ». `unit` impose l'unité (comparaison : une seule unité).
export function formatCo2(mg, { unit } = {}) {
  if (!isMeasure(mg)) return formatUnknown();
  const chosen = unit ?? co2Unit(mg);
  const step = CO2_STEPS.find((candidate) => candidate.unit === chosen) ?? CO2_STEPS[0];
  return withUnit(formatNumber(mg / step.per_mg), step.unit);
}

// Plusieurs CO2 à comparer : une seule unité, celle du plus grand. -> { unit, format(mg) }
export function co2Group(values) {
  const known = values.filter(isMeasure);
  const unit = known.length ? co2Unit(Math.max(...known.map(Math.abs))) : "mg";
  return { unit, format: (mg) => formatCo2(mg, { unit }) };
}

export function formatGb(gb) {
  return isMeasure(gb) ? withUnit(formatNumber(gb), "Go") : formatUnknown();
}

// Pourcentage entier (charge du processeur) : « 12 % ». Un inconnu n'est jamais 0 %.
export function formatPercent(percent) {
  return isMeasure(percent) ? withUnit(formatInteger(Math.round(percent)), "%") : formatUnknown();
}

export function formatRate(tokensPerSecond) {
  return isMeasure(tokensPerSecond)
    ? withUnit(formatNumber(tokensPerSecond), "tokens/s")
    : formatUnknown();
}

// Durées : « 0,66 s », « 12,3 s », « 1 min 12 s », « 1 h 05 min ».
export function formatDuration(seconds) {
  if (!isMeasure(seconds) || seconds < 0) return formatUnknown();
  if (seconds < 60) {
    const rounded = Number(seconds.toPrecision(3));
    return rounded < 60 ? withUnit(formatNumber(seconds), "s") : "1" + NBSP + "min";
  }
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = total % 60;
  if (hours > 0) return `${hours}${NBSP}h ${String(minutes).padStart(2, "0")}${NBSP}min`;
  return rest === 0 ? `${minutes}${NBSP}min` : `${minutes}${NBSP}min ${rest}${NBSP}s`;
}

// Chronomètre d'un bandeau : « 0:42 », « 12:05 », « 1:02:03 » (secondes entières).
export function formatClock(seconds) {
  if (!isMeasure(seconds) || seconds < 0) return formatUnknown();
  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = String(total % 60).padStart(2, "0");
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, "0")}:${rest}` : `${minutes}:${rest}`;
}

// Texte au pluriel du catalogue : `<base>_one` (0 et 1) ou `<base>_other`, `{n}` mis en forme.
export const plural = (base, n, vars = {}) =>
  t(`${base}_${n < 2 ? "one" : "other"}`, { n: formatInteger(n), ...vars });

// Date ISO -> « 18 oct. 2026 ».
export function formatDate(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return formatUnknown();
  return intl("date", { day: "numeric", month: "short", year: "numeric" }, Intl.DateTimeFormat).format(date);
}

// Score sur 100 ; sans score, « non évalué » (jamais 0/100).
export function formatScore(score) {
  if (!isMeasure(score)) return t("format.not_evaluated");
  return `${formatNumber(score)}/100`;
}

const MONEY_FLOOR = 0.0001;

// Montant dans la devise de la table de prix du serveur : « 0,03 € », « 6,60 € ». Jusqu'à quatre
// décimales pour un petit coût ; un coût réel sous 0,0001 se dit « moins de 0,0001 € », jamais 0.
export function formatMoney(amount, currency) {
  if (!isMeasure(amount)) return formatUnknown();
  const money = (value) =>
    intl(`money-${currency}`, { style: "currency", currency, minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(value);
  return amount > 0 && amount < MONEY_FLOOR ? t("format.money_below", { value: money(MONEY_FLOOR) }) : money(amount);
}
