// Filtre et lignes de la liste de <wl-model-picker> : nom, badge d'origine, taille, mémoire, débit, pastilles.
// Le front ne calcule rien : `fits`, `required_gb` et le débit viennent de l'API (AD-20).

import { element, icon } from "../core/dom.js";
import { formatGb, formatNumber, formatRate } from "../core/format.js";
import { t } from "../core/i18n.js";
import "./wl-badge.js";

// Mots de la saisie : tous doivent figurer dans le nom, le tag, le fournisseur ou l'éditeur.
export function matchesQuery(model, query) {
  const words = query.toLocaleLowerCase("fr-FR").split(/\s+/).filter(Boolean);
  if (!words.length) return true;
  const haystack = [model.name, model.tag, model.provider, model.editor]
    .filter(Boolean)
    .join(" ")
    .toLocaleLowerCase("fr-FR");
  return words.every((word) => haystack.includes(word));
}

function badgeKind(model) {
  return ["local", "cloud"].includes(model.origin) ? model.origin : "unknown";
}

export function unavailableReason(model) {
  if (model.available) return null;
  return t(
    model.origin === "cloud"
      ? "components.picker.unavailable_cloud"
      : "components.picker.unavailable_local",
  );
}

export function buildOption(model, { id, multi, active, selected, isDefault }) {
  const disabledReason = unavailableReason(model);
  const row = element("div", "wl-picker-option");
  row.id = id;
  row.dataset.tag = model.tag;
  row.setAttribute("role", "option");
  row.setAttribute("aria-selected", String(selected));
  if (disabledReason) row.setAttribute("aria-disabled", "true");
  if (active) row.classList.add("is-active");

  const head = element("span", "wl-picker-option-head");
  if (multi) {
    const box = element("span", "wl-picker-check");
    box.setAttribute("aria-hidden", "true");
    if (selected) box.append(icon("check"));
    head.append(box);
  }
  const badge = document.createElement("wl-badge");
  badge.setAttribute("kind", badgeKind(model));
  head.append(element("span", "wl-picker-option-name", model.name), badge);
  if (isDefault) head.append(element("span", "wl-picker-pill", t("components.picker.default")));

  const meta = element("span", "wl-picker-option-meta");
  if (model.size_gb != null) meta.append(element("span", "", formatGb(model.size_gb)));
  const memory = memoryFact(model);
  if (memory) meta.append(memory);
  if (model.throughput_tps != null) {
    meta.append(
      element("span", "", t("components.picker.throughput", { rate: formatRate(model.throughput_tps) })),
    );
  }
  if (disabledReason) meta.append(element("span", "wl-picker-warning", disabledReason));

  const pills = element("span", "wl-picker-option-pills");
  if (model.tools_verified) pills.append(element("span", "wl-picker-pill", t("components.picker.tools")));
  if (model.reasoning) pills.append(element("span", "wl-picker-pill", t("components.picker.reasoning")));
  if (model.params_active_b != null && model.params_total_b != null && model.params_active_b < model.params_total_b) {
    pills.append(
      element("span", "wl-picker-pill", t("components.picker.moe", { active: formatNumber(model.params_active_b) })),
    );
  }
  row.append(head, meta);
  if (pills.children.length) row.append(pills);
  return row;
}

// « Tient en mémoire », un avertissement, ou « à vérifier » : jamais un chiffre calculé ici.
function memoryFact(model) {
  if (model.origin === "cloud") return null;
  if (model.fits === true) return element("span", "wl-picker-fits", t("components.picker.fits"));
  if (model.fits === false) {
    const text =
      model.required_gb != null // le même chiffre que les « nécessaires » d'un refus ram_guard
        ? t("components.picker.no_fit_need", { needed: formatGb(model.required_gb) })
        : t("components.picker.no_fit");
    const warning = element("span", "wl-picker-warning");
    warning.append(icon("warning"), element("span", "", text));
    return warning;
  }
  return element("span", "", t("components.picker.memory_unknown"));
}
