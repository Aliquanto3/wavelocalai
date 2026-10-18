// Trace d'étapes d'un agent (UX-DR28), commune à Agent seul et à Équipe d'agents.
//
//   const trace = createStepTrace({label, showAgent, agentName(id), toolLabel(id), openFile(name)});
//   host.append(trace.root); trace.apply(dataDeStep); trace.waitOnLast(); trace.finish(statut);
//   trace.expand(id, ouvert); trace.entries(); trace.row(id); trace.count; trace.clear()
//
// `stepIcon(type)` : icône du sprite d'un type d'étape (think, tool, answer, wait, error, stop, done).

import { element, icon } from "../core/dom.js";
import { formatDuration } from "../core/format.js";
import { t } from "../core/i18n.js";

// Icône d'un type d'étape, décorative : le libellé porte toujours le sens.
const STEP_ICONS = { think: "lightbulb", tool: "terminal", answer: "chat", wait: "hourglass", error: "warning", stop: "stop", done: "check" };

export function stepIcon(name) {
  const svg = icon(STEP_ICONS[name] ?? STEP_ICONS.think);
  svg.classList.add("step-icon");
  return svg;
}

// Liste ordonnée, une ligne dépliable par étape (motif « disclosure » APG : un bouton `aria-expanded`). Une étape = un `step_id` : un événement de début (sans durée), puis un
// événement de fin (avec `duration_s`). Les lignes se mettent à jour sur place : le focus et l'état
// déplié ne bougent pas quand les étapes suivantes arrivent. La liste n'est pas `aria-live`.

let traceCounter = 0;

export function createStepTrace({ label, showAgent = false, agentName = (id) => id, toolLabel = (id) => id, openFile = null } = {}) {
  const root = element("ol", "step-trace");
  root.setAttribute("aria-label", label);
  root.hidden = true;
  const rows = new Map();
  const uid = `trace-${++traceCounter}`;

  const labelOf = (row) => {
    if (row.limit) return row.summary;
    if (row.kind === "think") return t("components.step_trace.think");
    if (row.kind === "answer") return t("components.step_trace.answer");
    return toolLabel(row.tool);
  };
  const stateText = (row) => {
    switch (row.state) {
      case "running":
        return t("components.step_trace.running");
      case "waiting":
        return t("components.step_trace.waiting");
      case "error":
        return `${t("components.step_trace.error_result")} · ${formatDuration(row.duration)}`;
      case "cancelled":
        return t("components.run_status.cancelled");
      case "interrupted":
        return t("components.run_status.interrupted");
      case "failed":
        return t("components.run_status.error");
      default:
        return formatDuration(row.duration);
    }
  };
  const stateIcon = (row) => {
    if (row.state === "waiting") return "wait";
    if (row.state === "error" || row.state === "failed") return "error";
    if (row.state === "cancelled" || row.state === "interrupted") return "stop";
    return row.kind === "think" ? "think" : row.kind === "answer" ? "answer" : "tool";
  };

  function buildBody(row) {
    const parts = [];
    if (row.args && Object.keys(row.args).length) {
      parts.push(element("p", "step-field", t("components.step_trace.arguments")));
      parts.push(element("pre", "step-code", JSON.stringify(row.args, null, 2)));
    }
    const text = row.kind === "tool" ? row.result : row.summary;
    if (text) {
      parts.push(element("p", "step-field", row.kind === "tool" ? t("components.step_trace.result") : t("components.step_trace.summary")));
      parts.push(element("p", "step-text", text));
    }
    if (row.file && openFile) {
      const name = row.file.split("/").pop();
      const open = element("button", "btn step-file", t("components.step_trace.open_file"));
      open.type = "button";
      open.setAttribute("aria-label", t("components.step_trace.open_file_named", { name }));
      open.addEventListener("click", () => openFile(name));
      parts.push(open);
    }
    if (!parts.length) parts.push(element("p", "help", t("components.step_trace.nothing_yet")));
    return parts;
  }

  function paint(row) {
    const { node } = row;
    node.li.dataset.kind = row.kind;
    node.li.dataset.state = row.state;
    node.number.textContent = String(row.n);
    node.label.textContent = labelOf(row);
    node.agent.textContent = showAgent && row.agent ? agentName(row.agent) : "";
    node.agent.hidden = !(showAgent && row.agent);
    node.state.textContent = stateText(row);
    node.outcome.textContent = row.outcome ?? "";
    node.outcome.hidden = !row.outcome;
    const wanted = stateIcon(row);
    if (node.iconName !== wanted) {
      const next = stepIcon(wanted);
      node.icon.replaceWith(next);
      node.icon = next;
      node.iconName = wanted;
    }
    const signature = JSON.stringify([row.args, row.result, row.summary, row.file]);
    if (signature !== node.signature) {
      node.signature = signature;
      node.body.replaceChildren(...buildBody(row));
    }
  }

  function create(id, data) {
    const li = element("li", "step");
    const button = element("button", "step-head");
    button.type = "button";
    button.setAttribute("aria-expanded", "false");
    const body = element("div", "step-body");
    body.id = `${uid}-${id}`;
    body.hidden = true;
    button.setAttribute("aria-controls", body.id);
    const number = element("span", "step-n");
    const ic = stepIcon("think");
    const main = element("span", "step-main");
    const labelNode = element("span", "step-label");
    const agent = element("span", "step-agent");
    const outcome = element("span", "step-outcome");
    main.append(labelNode, agent, outcome);
    const stateNode = element("span", "step-state");
    button.append(number, ic, main, stateNode, icon("expand-more"));
    button.addEventListener("click", () => {
      const open = button.getAttribute("aria-expanded") !== "true";
      button.setAttribute("aria-expanded", String(open));
      body.hidden = !open;
    });
    li.append(button, body);
    const row = {
      id,
      n: rows.size + 1,
      kind: "think",
      agent: data.agent ?? null,
      state: "running",
      node: { li, button, body, number, icon: ic, iconName: "think", label: labelNode, agent, outcome, state: stateNode, signature: "" },
    };
    rows.set(id, row);
    root.append(li);
    root.hidden = false;
    return row;
  }

  return {
    root,
    get count() {
      return rows.size;
    },
    row: (id) => rows.get(id) ?? null,
    // Un événement `step`.
    apply(data) {
      const row = rows.get(data.step_id) ?? create(data.step_id, data);
      row.kind = data.kind === "tool_call" || data.kind === "tool_result" ? "tool" : data.kind;
      if (data.tool) row.tool = data.tool;
      if (data.arguments) row.args = data.arguments;
      if (data.agent) row.agent = data.agent;
      if (data.kind === "tool_result") {
        row.result = data.summary;
        if (data.artifact_url) row.file = data.artifact_url;
      } else if (data.summary) row.summary = data.summary;
      if (data.outcome) row.outcome = data.outcome;
      if (data.limit_reached) row.limit = true;
      if (typeof data.duration_s === "number") {
        row.duration = data.duration_s;
        row.state = data.is_error ? "error" : "done";
      } else if (row.state !== "waiting") row.state = "running";
      paint(row);
      return row;
    },
    // La dernière étape en cours attend une décision (validation d'email).
    waitOnLast() {
      const running = [...rows.values()].filter((row) => row.state === "running");
      const row = running[running.length - 1];
      if (row) {
        row.state = "waiting";
        paint(row);
      }
      return row ?? null;
    },
    // Fin du run : les étapes encore en cours prennent le statut du run.
    finish(finalStatus) {
      const map = { cancelled: "cancelled", interrupted: "interrupted", error: "failed" };
      if (!map[finalStatus]) return;
      for (const row of rows.values()) {
        if (row.state === "running" || row.state === "waiting") {
          row.state = map[finalStatus];
          row.duration ??= 0;
          paint(row);
        }
      }
    },
    expand(id, open = true) {
      const row = rows.get(id);
      if (!row) return;
      row.node.button.setAttribute("aria-expanded", String(open));
      row.node.body.hidden = !open;
    },
    entries: () => [...rows.values()],
    clear() {
      rows.clear();
      root.replaceChildren();
      root.hidden = true;
    },
  };
}

