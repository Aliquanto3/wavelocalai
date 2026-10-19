// Mises en forme communes aux tableaux de l'écran Modèles : le front ne calcule rien (AD-20).

import { element } from "../core/dom.js";
import { formatNumber, formatUnknown } from "../core/format.js";
import { t } from "../core/i18n.js";

// « 8 B · 1 B actifs » (MoE), « 2,3 B » (dense, ou actifs inconnus : jamais le total pris pour eux),
// « inconnu » sans taille.
export function paramsText(total, active) {
  if (total === null || total === undefined) return formatUnknown();
  const totalText = formatNumber(total);
  if (active === null || active === undefined || active === total) {
    return t("models.installed.params_total", { total: totalText });
  }
  return t("models.installed.params_active", { total: totalText, active: formatNumber(active) });
}

let currentTag = null;

// Le modèle dont la fiche est ouverte (`#/modeles/<tag>`) : son lien porte `aria-current`.
export function setCurrentCardTag(tag) {
  currentTag = tag;
}

// Nom du modèle, lien vers sa fiche (`#/modeles/<tag>`, story 5.6), puis son tag d'Ollama en petit :
// le tag est ce qu'on saisit pour l'installer.
export function nameCell(name, tag) {
  const cell = element("span", "models-name");
  const link = element("a", "models-name-text models-name-link", name);
  link.href = `#/modeles/${encodeURIComponent(tag)}`;
  link.dataset.tag = tag;
  link.setAttribute("aria-label", t("models.card.link_aria", { name }));
  if (currentTag === tag) link.setAttribute("aria-current", "true");
  cell.append(link);
  if (name !== tag) cell.append(element("code", "models-tag", tag));
  return cell;
}

const baseTag = (tag) => tag.replace(/:latest$/, "");

// Le run racine qui emploie ce modèle (`system.modelsInUse` : tag -> run_id du flux système), sinon
// null. `:latest` ne compte pas : `qwen3.5` et `qwen3.5:latest` sont le même modèle.
export function usedBy(modelsInUse, tag) {
  const wanted = baseTag(tag);
  const found = Object.keys(modelsInUse ?? {}).find((used) => baseTag(used) === wanted);
  return found === undefined ? null : modelsInUse[found];
}
