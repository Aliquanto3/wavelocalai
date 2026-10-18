// Affichage du champ `co2` d'AD-10 (`{mg, method, estimated, range_mg, allocation, reason}`), sans
// rien calculer : « 1,8 mg » mesuré, « 0,9 mg (estimé) » pour une estimation, « non mesurable »
// avec sa raison en aide ; jamais « — » seul ni 0 (03 §3.7, story 2.5).

import { co2Group, formatCo2 } from "./format.js";
import { t } from "./i18n.js";

export function co2Display(co2) {
  if (!co2) return { kind: "unknown", value: t("format.unknown"), help: null };
  if (co2.mg === null || co2.mg === undefined || co2.method === "unmeasurable") {
    return { kind: "unmeasurable", value: t("co2.unmeasurable"), help: co2.reason ?? t("co2.unmeasurable_help") };
  }
  if (co2.estimated) {
    const range = co2.range_mg;
    let help = t("co2.estimated_help");
    if (range && typeof range.low === "number" && typeof range.high === "number") {
      const group = co2Group([range.low, range.high]);
      help = t("co2.estimated_range", { low: group.format(range.low), high: group.format(range.high) });
    }
    return { kind: "estimated", value: t("co2.estimated_value", { value: formatCo2(co2.mg) }), help };
  }
  return { kind: "measured", value: formatCo2(co2.mg), help: t("co2.measured_help") };
}
