// Les outils de l'agent (EXPERIENCE.md « Agent seul », D-6, story 6.4) : un interrupteur en bascule
// (`<input type="checkbox" role="switch">`) par outil de `GET /api/agents/tools`, avec sa description
// en aide. Tous activés, sauf l'outil `sensitive` (« Envoi d'email », qui ne part qu'après validation).
// Un outil indisponible n'est pas activable : `aria-disabled` (focalisable, jamais `disabled`) et son
// clic est refusé, sa raison reste en légende visible reliée à l'interrupteur.

import { api, ApiError } from "../core/api.js";
import { element, icon } from "../core/dom.js";
import { t } from "../core/i18n.js";

function switchFor(tool, uid) {
  const input = element("input");
  input.type = "checkbox";
  input.setAttribute("role", "switch");
  input.id = `${uid}-${tool.id}`;
  input.dataset.tool = tool.id;
  const described = [`${input.id}-help`];
  const help = element("p", "help agents-tool-help", tool.description);
  help.id = `${input.id}-help`;
  const parts = [help];
  if (tool.available) {
    input.checked = !tool.sensitive;
  } else {
    input.checked = false;
    input.setAttribute("aria-disabled", "true");
    input.addEventListener("click", (event) => event.preventDefault()); // clic et Espace
    const reason = element("p", "help agents-tool-reason", tool.reason ?? "");
    reason.id = `${input.id}-reason`;
    described.push(reason.id);
    parts.push(reason);
  }
  input.setAttribute("aria-describedby", described.join(" "));
  const box = element("span", "switch-box");
  box.append(input, icon("check"));
  box.lastChild.classList.add("switch-check");
  const label = element("label", "switch");
  label.append(box, element("span", "", tool.label));
  const item = element("li", "agents-tool");
  item.dataset.available = String(tool.available);
  item.append(label, ...parts);
  return item;
}

export function createTools(uid) {
  const root = element("fieldset", "agents-tools");
  root.append(element("legend", "agents-tools-legend", t("agents.settings.tools_legend")));
  const error = document.createElement("wl-error");
  error.setAttribute("alert", "");
  error.hidden = true;
  const loading = element("p", "help", t("agents.settings.tools_loading"));
  const list = element("ul", "agents-tool-list");
  root.append(error, loading, list);
  let tools = [];

  async function load() {
    try {
      tools = (await api.agentTools()).tools;
      error.hidden = true;
    } catch (failure) {
      tools = [];
      const envelope = failure instanceof ApiError && failure.envelope ? failure.envelope : null;
      error.error = envelope ?? {
        code: "internal",
        message: t("agents.settings.tools_failed"),
        action: t("agents.settings.tools_failed_action"),
      };
      error.hidden = false;
    }
    loading.hidden = true;
    list.replaceChildren(...tools.map((tool) => switchFor(tool, uid)));
  }

  return {
    root,
    load,
    // Les outils activés, dans l'ordre du serveur.
    selected: () =>
      [...list.querySelectorAll("input[role=switch]")]
        .filter((input) => input.checked && input.getAttribute("aria-disabled") !== "true")
        .map((input) => input.dataset.tool),
    labelOf: (id) => tools.find((tool) => tool.id === id)?.label ?? id,
  };
}
