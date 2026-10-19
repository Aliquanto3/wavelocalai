// Volet « Configurer l'équipe » (UX-DR28, D-35, D-36, story 6.6) : modifier les agents d'une équipe et
// enregistrer la modification (`PUT /api/agents/crews/{id}`, clé `agents.crews` de `preferences`, Q3).
//
//   const config = createConfig({ tools, models, maxAgents, allowCloud, say, onSaved, onClose });
//   config.root   config.open(crew)   config.close()   config.isOpen
//
// - **Non modal** : ni `dialog`, ni piège de focus ; le schéma reste visible et lisible (colonne de
//   droite dès 1 024 px, sous le schéma en deçà : c'est la grille de l'écran qui le place). À
//   l'ouverture le focus va sur son `h2`.
// - Un `fieldset` par agent : Rôle, Objectif, Outils en interrupteurs (ceux de l'Agent seul), Modèle
//   (liste native : « Modèle de la mission » = aucun modèle propre). Le contexte (`backstory`) de
//   l'équipe d'origine est conservé tel quel, sans champ.
// - À `maxAgents` (5, D-36), « Ajouter un agent » est désactivé avec sa raison visible, reliée au
//   bouton par `aria-describedby`.
// - « Enregistrer » passe par la validation du serveur (`POST /api/agents/crews/validate`) : chaque
//   erreur s'affiche sous son champ (`aria-describedby`, `aria-invalid`) et le focus va à la première.
//   « Annuler » abandonne les changements non enregistrés. Le front ne valide rien lui-même.

import { switchFor } from "./agents-tools.js";
import { api, ApiError } from "../core/api.js";
import { element } from "../core/dom.js";
import { t } from "../core/i18n.js";

let counter = 0;
const ROLE_MAX = 60;
const GOAL_MAX = 300;

function blank() {
  return { role: "", goal: "", backstory: "", tools: [], model: null };
}

export function createConfig({ tools, models, maxAgents, allowCloud, say, onSaved, onClose }) {
  const uid = `crew-config-${++counter}`;
  const title = element("h2", "crew-config-title", t("crew.config.title"));
  title.id = `${uid}-title`;
  title.tabIndex = -1;
  const lead = element("p", "help", t("crew.config.lead"));
  const failure = document.createElement("wl-error");
  failure.setAttribute("alert", "");
  const agentsError = element("p", "crew-field-error");
  agentsError.id = `${uid}-agents-error`;
  agentsError.hidden = true;
  const none = element("p", "help", t("crew.config.none"));
  const list = element("div", "crew-config-agents");
  const add = element("button", "btn", t("crew.config.add"));
  add.type = "button";
  const addReason = element("p", "help crew-config-reason", "");
  addReason.id = `${uid}-add-reason`;
  const save = element("button", "btn chat-send", t("crew.config.save"));
  save.type = "submit";
  const cancel = element("button", "btn", t("crew.config.cancel"));
  cancel.type = "button";
  const actions = element("div", "crew-config-actions");
  actions.append(save, cancel);
  const form = element("form", "crew-config-form");
  form.noValidate = true;
  form.append(agentsError, none, list, add, addReason, actions);
  const root = element("section", "crew-config");
  root.setAttribute("aria-labelledby", title.id);
  root.hidden = true;
  root.append(title, lead, failure, form);

  let crewId = null;
  let draft = [];
  let saving = false;

  // --- Lecture et écriture du brouillon ------------------------------------------------------
  function collect() {
    draft = [...list.querySelectorAll(".crew-config-agent")].map((box, index) => ({
      role: box.querySelector("[data-field=role]").value.trim(),
      goal: box.querySelector("[data-field=goal]").value.trim(),
      backstory: draft[index]?.backstory ?? "",
      tools: [...box.querySelectorAll("input[role=switch]")]
        .filter((input) => input.checked && input.getAttribute("aria-disabled") !== "true")
        .map((input) => input.dataset.tool),
      model: box.querySelector("[data-field=model]").value || null,
    }));
  }

  function fieldBox(label, control, field, index, hint) {
    const id = `${uid}-${index}-${field}`;
    control.id = id;
    control.dataset.field = field;
    const error = element("p", "crew-field-error");
    error.id = `${id}-error`;
    error.hidden = true;
    error.dataset.errorFor = `agents[${index}].${field}`;
    control.setAttribute("aria-describedby", error.id);
    const box = element("div", "crew-field");
    const tag = element("label", "crew-field-label", label);
    tag.htmlFor = id;
    box.append(tag, control, error);
    if (hint) box.append(hint);
    return box;
  }

  function modelSelect(agent) {
    const select = element("select", "crew-model-select");
    select.append(new Option(t("crew.config.model_mission"), ""));
    const known = new Set();
    for (const model of models()) {
      known.add(model.tag);
      select.append(new Option(model.name ?? model.tag, model.tag));
    }
    if (agent.model && !known.has(agent.model)) select.append(new Option(agent.model, agent.model));
    select.value = agent.model ?? "";
    return select;
  }

  function agentBox(agent, index) {
    const box = element("fieldset", "crew-config-agent");
    const legend = element("legend", "crew-config-legend", t("crew.config.agent", { n: index + 1 }));
    const role = element("input");
    role.type = "text";
    role.maxLength = ROLE_MAX + 20; // la limite est celle du serveur : il dit l'erreur
    role.value = agent.role;
    const goal = element("textarea");
    goal.rows = 2;
    goal.maxLength = GOAL_MAX + 100;
    goal.value = agent.goal;
    const toolsBox = element("fieldset", "crew-config-tools");
    toolsBox.append(element("legend", "crew-field-label", t("crew.config.tools")));
    const toolList = element("ul", "agents-tool-list");
    for (const tool of tools()) {
      const item = switchFor(tool, `${uid}-${index}`);
      const input = item.querySelector("input");
      if (tool.available) input.checked = agent.tools.includes(tool.id);
      toolList.append(item);
    }
    const toolsError = element("p", "crew-field-error");
    toolsError.id = `${uid}-${index}-tools-error`;
    toolsError.hidden = true;
    toolsError.dataset.errorFor = `agents[${index}].tools`;
    toolsBox.dataset.field = "tools";
    toolsBox.setAttribute("aria-describedby", toolsError.id);
    toolsBox.append(toolList, toolsError);
    const remove = element("button", "btn", t("crew.config.remove"));
    remove.type = "button";
    remove.addEventListener("click", () => {
      collect();
      draft.splice(index, 1);
      render();
      say(t("crew.config.removed"));
      add.focus();
    });
    box.append(
      legend,
      fieldBox(t("crew.config.role"), role, "role", index),
      fieldBox(t("crew.config.goal"), goal, "goal", index),
      toolsBox,
      fieldBox(t("crew.config.model"), modelSelect(agent), "model", index),
      remove,
    );
    return box;
  }

  function render() {
    list.replaceChildren(...draft.map(agentBox));
    none.hidden = draft.length > 0;
    const full = draft.length >= maxAgents();
    add.disabled = full;
    addReason.textContent = full ? t("crew.config.add_reason", { max: maxAgents() }) : "";
    addReason.hidden = !full;
    if (full) add.setAttribute("aria-describedby", addReason.id);
    else add.removeAttribute("aria-describedby");
  }

  // --- Erreurs du serveur : une par champ, sous le champ -------------------------------------
  function clearErrors() {
    failure.error = null;
    agentsError.hidden = true;
    for (const node of root.querySelectorAll("[data-error-for]")) node.hidden = true;
    for (const node of root.querySelectorAll("[aria-invalid]")) node.removeAttribute("aria-invalid");
  }

  function showErrors(errors) {
    let first = null;
    for (const { field, message } of errors) {
      if (field === "agents") {
        agentsError.textContent = message;
        agentsError.hidden = false;
        first ??= add;
        continue;
      }
      const slot = root.querySelector(`[data-error-for="${CSS.escape(field)}"]`);
      if (!slot) continue;
      slot.textContent = message;
      slot.hidden = false;
      const control = slot.parentElement.querySelector("[data-field]") ?? slot.parentElement;
      control.setAttribute("aria-invalid", "true");
      first ??= control.matches("input,textarea,select") ? control : control.querySelector("input,select");
    }
    first?.focus();
  }

  function busy(value) {
    saving = value;
    save.disabled = value;
    save.textContent = t(value ? "crew.config.saving" : "crew.config.save");
  }

  async function submit() {
    if (saving) return;
    collect();
    clearErrors();
    busy(true);
    try {
      const checked = await api.validateCrew(draft, allowCloud());
      if (!checked.valid) {
        failure.error = { code: "invalid_request", message: t("crew.config.invalid") };
        showErrors(checked.errors ?? []);
        return;
      }
      const saved = await api.saveCrew(crewId, draft, allowCloud());
      close();
      say(t("crew.config.saved"));
      onSaved(saved);
    } catch (problem) {
      const envelope = problem instanceof ApiError ? problem.envelope : null;
      failure.error = envelope ?? { code: "internal", message: t("crew.config.save_failed") };
    } finally {
      busy(false);
    }
  }

  function close({ restoreFocus = true } = {}) {
    if (root.hidden) return;
    root.hidden = true;
    crewId = null;
    draft = [];
    clearErrors();
    onClose({ restoreFocus });
  }

  add.addEventListener("click", () => {
    if (draft.length >= maxAgents()) return;
    collect();
    draft.push(blank());
    render();
    say(t("crew.config.added"));
    list.lastElementChild?.querySelector("[data-field=role]")?.focus();
  });
  cancel.addEventListener("click", () => close());
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submit();
  });

  return {
    root,
    get isOpen() {
      return !root.hidden;
    },
    open(crew) {
      crewId = crew.id;
      draft = crew.agents.map((agent) => ({ ...blank(), ...agent, tools: [...(agent.tools ?? [])] }));
      clearErrors();
      render();
      root.hidden = false;
      title.focus({ preventScroll: false });
    },
    close,
    // Les listes (outils, modèles) arrivent après l'ouverture : on redessine sans perdre la saisie.
    refresh() {
      if (root.hidden) return;
      collect();
      render();
    },
  };
}
