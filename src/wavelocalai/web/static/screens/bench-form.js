// Formulaire du Banc d'essai (story 7.4, UX-DR29, D-6, D-17, D-18) : scénario prédéfini, « Consigne »
// repliée (la consigne système du scénario, D-18), « Format attendu » lu du schéma que le serveur
// donne (D-17 : absent pour un scénario sans format), « Entrée » préremplie et modifiable, modèle,
// interrupteurs « Format imposé » et « Réponse concise » avec leur aide, puis « Lancer le test »
// désactivé avec sa raison visible reliée au bouton.
//
//   const form = formView(uid, scenarios);   form.el  form.config()  form.apply(config)
//
// Le front ne décide rien du format : il pose le schéma du serveur en tableau. « Format imposé » est
// désactivé, avec sa raison en texte, quand le scénario n'a pas de format ou que le modèle choisi ne
// sait pas imposer un schéma (`structured_output: false` de `GET /api/models`, décision n° 10).

import { element } from "../core/dom.js";
import { t } from "../core/i18n.js";

const typeNames = (type) =>
  (Array.isArray(type) ? type : [type]).map((name) => t(`bench.types.${name}`)).join(` ${t("bench.format.or")} `);

// Les champs d'un schéma d'objet, pour le tableau « Format attendu ».
export function schemaRows(schema) {
  const required = new Set(schema?.required ?? []);
  return Object.entries(schema?.properties ?? {}).map(([name, spec]) => {
    const among = Array.isArray(spec.enum) ? ` ${t("bench.format.among", { values: spec.enum.join(", ") })}` : "";
    return { name, type: `${typeNames(spec.type)}${among}`, required: required.has(name) };
  });
}

function formatTable(schema) {
  const table = element("table", "bc-format");
  const caption = element("caption", "sr-only", t("bench.format.caption"));
  const head = element("tr");
  for (const key of ["field", "type", "required"]) {
    const cell = element("th", "", t(`bench.format.${key}`));
    cell.scope = "col";
    head.append(cell);
  }
  const body = element("tbody");
  for (const row of schemaRows(schema)) {
    const line = element("tr");
    const name = element("th", "", row.name);
    name.scope = "row";
    line.append(name, element("td", "", row.type), element("td", "", t(row.required ? "bench.format.yes" : "bench.format.no")));
    body.append(line);
  }
  table.append(caption, element("thead"), body);
  table.tHead.append(head);
  return table;
}

function makeSwitch(uid, key) {
  const row = element("div", "bc-switch");
  const label = element("label", "switch bc-switch-label");
  const box = element("span", "switch-box");
  const input = element("input");
  input.type = "checkbox";
  input.setAttribute("role", "switch");
  input.id = `${uid}-${key}`;
  const check = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  check.setAttribute("class", "icon switch-check");
  check.setAttribute("aria-hidden", "true");
  check.setAttribute("focusable", "false");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", "/static/icons.svg#i-check");
  check.append(use);
  box.append(input, check);
  label.append(box, element("span", "", t(`bench.${key}.label`)));
  const help = element("p", "help bc-switch-help", t(`bench.${key}.help`));
  help.id = `${uid}-${key}-help`;
  const reason = element("p", "bc-switch-reason");
  reason.id = `${uid}-${key}-reason`;
  reason.hidden = true;
  input.setAttribute("aria-describedby", help.id);
  row.append(label, help, reason);
  return { row, input, help, reason };
}

export function formView(uid, scenarios) {
  let scenario = scenarios[0];
  let isBusy = () => false;

  const select = element("select", "bc-select");
  select.id = `${uid}-scenario`;
  for (const item of scenarios) {
    const option = element("option", "", item.name);
    option.value = item.id;
    select.append(option);
  }
  const selectLabel = element("label", "bc-label", t("bench.scenario.label"));
  selectLabel.htmlFor = select.id;

  const instructionBody = element("p", "bc-instruction-body");
  const instruction = element("details", "bc-details bc-instruction");
  instruction.append(element("summary", "", t("bench.instruction.title")), instructionBody);
  const formatBody = element("div", "bc-format-body");
  const format = element("details", "bc-details bc-format-box");
  format.append(element("summary", "", t("bench.format.title")), formatBody);

  const input = element("textarea", "bc-input");
  input.id = `${uid}-input`;
  input.rows = 3;
  const inputLabel = element("label", "bc-label", t("bench.input.label"));
  inputLabel.htmlFor = input.id;
  const replaceNote = element("p", "help", t("bench.input.kept"));
  const replaceButton = element("button", "btn", t("bench.input.replace"));
  replaceButton.type = "button";
  const replaceRow = element("div", "bc-replace");
  replaceRow.hidden = true;
  replaceRow.append(replaceNote, replaceButton);

  const picker = document.createElement("wl-model-picker");
  picker.setAttribute("purpose", "chat");
  picker.setAttribute("label", t("bench.model"));

  const force = makeSwitch(uid, "force");
  const concise = makeSwitch(uid, "concise");
  const switches = element("div", "bc-switches");
  switches.append(force.row, concise.row);
  const settings = element("div", "bc-settings");
  settings.append(picker, switches);

  const launch = element("button", "btn btn-primary bc-launch", t("bench.launch"));
  launch.type = "submit";
  const legend = element("p", "help bc-legend");
  legend.id = `${uid}-legend`;
  launch.setAttribute("aria-describedby", legend.id);
  const launchRow = element("div", "bc-launch-row");
  launchRow.append(launch, legend);

  const el = element("form", "bc-form");
  el.noValidate = true;
  el.append(
    element("h2", "", t("bench.scenario.title")),
    selectLabel,
    select,
    instruction,
    format,
    inputLabel,
    input,
    replaceRow,
    element("h2", "", t("bench.settings.title")),
    settings,
    launchRow,
  );

  const modified = () => input.value !== scenario.input;

  function renderScenario() {
    instructionBody.textContent = scenario.instruction;
    formatBody.replaceChildren(
      scenario.schema ? formatTable(scenario.schema) : element("p", "help", t("bench.format.none")),
    );
  }

  function updateForce() {
    const fiche = picker.selected;
    let reason = null;
    if (!scenario.schema) reason = t("bench.force.no_schema");
    else if (fiche && fiche.structured_output === false) reason = t("bench.force.unsupported", { name: fiche.name });
    force.input.disabled = reason !== null;
    if (reason) force.input.checked = false;
    force.reason.hidden = reason === null;
    force.reason.textContent = reason ?? "";
    force.input.setAttribute("aria-describedby", reason ? `${force.help.id} ${force.reason.id}` : force.help.id);
  }

  // La première raison qui empêche de lancer (vide : on peut lancer).
  function reason() {
    if (isBusy()) return t("bench.legend.running");
    if (!picker.value) return t("bench.legend.model");
    if (!input.value.trim()) return t("bench.legend.input");
    return "";
  }

  function refresh() {
    updateForce();
    const why = reason();
    launch.disabled = why !== "";
    legend.textContent =
      why || t("bench.legend.ready", { name: picker.selected?.name ?? picker.value, scenario: scenario.name });
  }

  select.addEventListener("change", () => {
    const next = scenarios.find((item) => item.id === select.value) ?? scenario;
    const edited = modified();
    scenario = next;
    if (edited) replaceRow.hidden = false;
    else {
      input.value = next.input;
      replaceRow.hidden = true;
    }
    renderScenario();
    refresh();
  });
  replaceButton.addEventListener("click", () => {
    input.value = scenario.input;
    replaceRow.hidden = true;
    refresh();
    input.focus();
  });
  input.addEventListener("input", refresh);
  picker.addEventListener("wl-model-change", refresh);
  picker.addEventListener("wl-models-loaded", refresh);
  for (const item of [force, concise]) item.input.addEventListener("change", refresh);

  input.value = scenario.input;
  renderScenario();

  return {
    el,
    picker,
    launch,
    input,
    refresh,
    reason,
    scenario: () => scenario,
    setBusy(fn) {
      isBusy = fn;
    },
    config() {
      return {
        scenario: scenario.id,
        model: picker.value,
        input: input.value,
        force_format: force.input.checked && !force.input.disabled,
        concise: concise.input.checked,
      };
    },
    // Reprend une configuration (« Modifier le test », un essai rouvert ou rejoint).
    apply(config) {
      scenario = scenarios.find((item) => item.id === config.scenario) ?? scenario;
      select.value = scenario.id;
      input.value = config.input ?? scenario.input;
      replaceRow.hidden = true;
      if (config.model) picker.value = config.model;
      renderScenario();
      updateForce();
      force.input.checked = Boolean(config.force_format) && !force.input.disabled;
      concise.input.checked = Boolean(config.concise);
      refresh();
    },
  };
}
