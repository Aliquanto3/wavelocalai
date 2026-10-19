// Sobriété, section « Empreinte carbone de cette session » (story 5.1) : le total, la part par
// module, Local et Cloud « (estimé) », les réponses non mesurables à part. Tout vient du store,
// rempli par `GET /api/carbon/session` puis `carbon_updated` (AD-10) : l'écran ne calcule rien et
// suit les réponses sans clic.
//
// - Une seule unité pour toute la section (UX-DR15, `co2Group`) ; aucune couleur selon un seuil de
//   CO2, aucun jugement (« bon », « élevé »).
// - Session sans réponse : « Aucune réponse mesurée dans cette session », jamais « 0 mg ». Session
//   sans réponse mesurée mais avec des non-mesurables : elles sont dites à part.
// - « non mesurables » est un lien qui déplie « Comment ces chiffres sont calculés » (`onMethod`).
// - « Remettre le compteur à zéro » et l'historique relèvent de la story 5.2.

import { element, icon } from "../core/dom.js";
import { co2Group, formatInteger, plural } from "../core/format.js";
import { t } from "../core/i18n.js";
import { setAttr, setText } from "./sobriety-health.js";

// Ordre des modules à l'écran ; un genre inconnu garde son identifiant, après les autres.
const MODULE_ORDER = ["chat", "arena", "rag", "agent", "ingest"];

function moduleLabel(id) {
  return MODULE_ORDER.includes(id) ? t(`sobriety.carbon.modules.${id}`) : id;
}

function sortedModules(byModule) {
  const rank = (id) => (MODULE_ORDER.includes(id) ? MODULE_ORDER.indexOf(id) : MODULE_ORDER.length);
  return Object.entries(byModule ?? {})
    .filter(([, value]) => value.mg > 0) // un module à 0 est omis
    .sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b));
}

export function buildCarbon({ onMethod, methodId }) {
  const title = element("h2", "", t("sobriety.carbon.title"));
  title.id = "sob-carbon-title";

  const bar = element("span", "sob-skeleton");
  bar.append(element("span", "sr-only", t("sobriety.loading")));

  const empty = element("div", "sob-empty");
  empty.append(
    element("h3", "", t("sobriety.carbon.empty_title")),
    element("p", "", t("sobriety.carbon.empty_text")),
  );
  const onlyUnmeasurable = element("p", "wl-notice wl-notice-info");
  onlyUnmeasurable.append(icon("info"), element("span", "", t("sobriety.carbon.only_unmeasurable")));

  const total = document.createElement("wl-metric");
  total.setAttribute("label", t("sobriety.carbon.total_label"));
  total.setAttribute("help", t("sobriety.carbon.total_help"));
  const byModule = element("p", "sob-line");
  byModule.dataset.line = "modules";
  const origin = element("p", "sob-line");
  origin.dataset.line = "origin";
  const originText = element("span");
  const separator = document.createTextNode("");
  const methodLink = element("button", "link-button");
  methodLink.type = "button";
  methodLink.setAttribute("aria-controls", methodId);
  methodLink.addEventListener("click", onMethod);
  const unmeasurableNone = element("span");
  origin.append(originText, separator, methodLink, unmeasurableNone);
  const content = element("div", "sob-carbon-content");
  content.append(total, byModule, origin);

  const box = element("div", "sob-carbon");
  box.append(bar, empty, onlyUnmeasurable, content);
  const section = element("section", "sob-section");
  section.setAttribute("aria-labelledby", title.id);
  section.append(title, box);

  function render(state) {
    const carbon = state.carbon;
    const waiting = !carbon;
    bar.hidden = !waiting;
    setAttr(box, "aria-busy", String(waiting));
    if (waiting) {
      empty.hidden = true;
      onlyUnmeasurable.hidden = true;
      content.hidden = true;
      return;
    }
    const measured = (carbon.measured_runs ?? 0) > 0;
    const unmeasurable = carbon.unmeasurable_runs ?? 0;
    empty.hidden = measured || unmeasurable > 0;
    onlyUnmeasurable.hidden = measured || unmeasurable === 0;
    content.hidden = !measured && unmeasurable === 0;

    const modules = sortedModules(carbon.by_module);
    const local = carbon.by_origin?.local;
    const cloud = carbon.by_origin?.cloud;
    const group = co2Group([carbon.total_mg, local?.mg, cloud?.mg, ...modules.map(([, v]) => v.mg)]);

    total.hidden = !measured;
    if (measured) setAttr(total, "value", group.format(carbon.total_mg));
    byModule.hidden = !measured || modules.length === 0;
    setText(
      byModule,
      t("sobriety.carbon.by_module_line", {
        modules: modules.map(([id, value]) => `${moduleLabel(id)} ${group.format(value.mg)}`).join(" · "),
      }),
    );

    const parts = [];
    if (measured) {
      parts.push(
        local?.runs
          ? t("sobriety.carbon.local", { value: group.format(local.mg) })
          : t("sobriety.carbon.local_none"),
        cloud?.runs
          ? t("sobriety.carbon.cloud", { value: group.format(cloud.mg) })
          : t("sobriety.carbon.cloud_none"),
      );
    }
    setText(originText, parts.join(" · "));
    // Le séparateur ne précède le compte des non-mesurables que s'il y a quelque chose avant.
    separator.textContent = parts.length > 0 ? " · " : "";
    if (unmeasurable > 0) {
      methodLink.hidden = false;
      unmeasurableNone.hidden = true;
      const count = formatInteger(unmeasurable);
      setText(
        methodLink,
        `${plural("sobriety.carbon.unmeasurable", unmeasurable, { count })} ${plural("sobriety.carbon.unmeasurable_suffix", unmeasurable)}`,
      );
    } else {
      methodLink.hidden = true;
      unmeasurableNone.hidden = false;
      setText(unmeasurableNone, t("sobriety.carbon.unmeasurable_none"));
    }
  }

  return { section, render };
}
