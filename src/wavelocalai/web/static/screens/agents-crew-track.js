// Suivi d'une mission d'équipe (UX-DR28, AD-6, AD-20, story 6.6) : une ligne dépliable par agent, dans
// l'ordre de l'équipe, avec son statut et sa trace, puis le « Journal brut » replié.
//
//   const track = createTrack({ labelOf, onChange });   track.root
//   track.setAgents(["Chercheur", …])   track.reset()   track.feed(type, data, envelope)
//   track.states()        // { <rôle>: "pending" | "current" | "done" | "stopped" | "notrun" } (le schéma)
//   track.noteTrace       // la trace de l'agent en cours, où `agents-approval.js` inscrit ses issues
//
// Statuts (D-34) : « En attente » ; « En cours · <étape> » ; « Terminé · 3 outils · 41 s » (outils et
// durée lus dans `agent_totals` de l'étape `answer` qui clôt l'agent, jamais calculés ici) ;
// « Arrêté » (l'agent en cours quand la mission s'arrête ou échoue) ; « Non lancé » (un agent que la
// mission n'a pas atteint). Une ligne dépliée montre la `wl-step-trace` de l'agent (le champ `agent`
// des étapes aiguille chaque étape), l'étape en cours marquée ; le journal brut est en lignes
// horaires lisibles (« 09:15:02 Chercheur · Appel de l'outil … »), jamais du JSON (D-33).
// Le front ne déduit les statuts que de l'ordre des événements du serveur.

import { element } from "../core/dom.js";
import { formatDuration, formatTime, plural } from "../core/format.js";
import { t } from "../core/i18n.js";

let counter = 0;

function stepText(step, labelOf) {
  const tool = step.tool ? labelOf(step.tool) : "";
  if (step.kind === "think") return t("components.step_trace.think");
  if (step.kind === "tool_call") return t("components.step_trace.tool_call", { tool });
  if (step.kind === "tool_result") {
    return t(step.failed ? "components.step_trace.tool_failed" : "components.step_trace.tool_result", { tool });
  }
  return t("components.step_trace.answer");
}

export function createTrack({ labelOf, onChange = () => {} }) {
  const uid = `crew-track-${++counter}`;
  const title = element("h2", "crew-track-title", t("crew.track.title"));
  title.id = `${uid}-title`;
  const empty = element("p", "help", t("crew.track.empty"));
  const list = element("ol", "crew-agents");
  list.hidden = true;
  const journalList = element("ol", "crew-journal-list");
  const journalEmpty = element("p", "help", t("crew.journal.empty"));
  const journal = element("details", "crew-journal");
  journal.append(element("summary", "", t("crew.journal.title")), journalEmpty, journalList);
  journal.hidden = true;
  const root = element("section", "crew-track");
  root.setAttribute("aria-labelledby", title.id);
  root.append(title, empty, list, journal);

  let rows = []; // { role, item, status, trace, state, totals, tool, approval }
  let current = null;
  let maxTurns = null;

  const byRole = (role) => rows.find((row) => row.role === role) ?? null;

  function statusText(row) {
    if (row.state === "pending") return t("crew.track.pending");
    if (row.state === "notrun") return t("crew.track.notrun");
    if (row.state === "stopped") return t("crew.track.stopped");
    if (row.state === "done") {
      if (!row.totals) return t("crew.track.done");
      return t("crew.track.done_totals", {
        tools: plural("crew.track.tools", row.totals.tools ?? 0),
        duration: formatDuration(row.totals.duration_s),
      });
    }
    if (row.approval) return t("crew.track.approval");
    return row.tool
      ? t("crew.track.running_tool", { tool: labelOf(row.tool) })
      : t("crew.track.running");
  }

  function paint(row) {
    row.status.textContent = statusText(row);
    row.item.dataset.state = row.state;
  }

  function setState(row, state) {
    row.state = state;
    paint(row);
    onChange();
  }

  function buildRow(role, index) {
    const item = element("li", "crew-agent");
    const trace = document.createElement("wl-step-trace");
    trace.labelOf = labelOf;
    trace.maxTurns = maxTurns;
    const panelId = `${uid}-panel-${index}`;
    const toggle = element("button", "crew-agent-toggle");
    toggle.type = "button";
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-controls", panelId);
    const status = element("span", "crew-agent-status");
    toggle.append(element("span", "crew-agent-role", role), status);
    const panel = element("div", "crew-agent-panel");
    panel.id = panelId;
    panel.hidden = true;
    const none = element("p", "help", t("crew.track.no_steps"));
    panel.append(none, trace);
    toggle.addEventListener("click", () => {
      const open = panel.hidden;
      panel.hidden = !open;
      toggle.setAttribute("aria-expanded", String(open));
    });
    item.append(toggle, panel);
    return { role, item, status, trace, none, state: "pending", totals: null, tool: null, approval: false };
  }

  function setAgents(roles) {
    rows = roles.map(buildRow);
    current = null;
    list.replaceChildren(...rows.map((row) => row.item));
    rows.forEach(paint);
    list.hidden = !rows.length;
    empty.hidden = rows.length > 0;
    journal.hidden = !rows.length;
    onChange();
  }

  function reset() {
    rows = [];
    current = null;
    maxTurns = null;
    list.replaceChildren();
    list.hidden = true;
    empty.hidden = false;
    journal.hidden = true;
    journalList.replaceChildren();
    journalEmpty.hidden = false;
    onChange();
  }

  function log(envelope, agent, text) {
    const line = element("li", "crew-journal-line");
    const time = element("time", "crew-journal-time", formatTime(envelope?.ts));
    if (envelope?.ts) time.dateTime = envelope.ts;
    line.append(time, " ", agent ? `${agent} · ${text}` : text);
    journalList.append(line);
    journalEmpty.hidden = true;
  }

  function activate(row) {
    if (!row || row.state === "done") return;
    current = row;
    if (row.state !== "current") {
      row.state = "current";
      row.trace.setCurrent("running");
    }
    paint(row);
    onChange();
  }

  function finishAgent(row, step) {
    row.totals = step.agent_totals ?? null;
    row.tool = null;
    row.approval = false;
    row.trace.setCurrent(null);
    setState(row, "done");
    const next = rows[rows.indexOf(row) + 1];
    if (next) activate(next);
    else current = null;
  }

  const handlers = {
    run_started(data, envelope) {
      maxTurns = data?.params?.max_turns ?? maxTurns;
      const roles = (data?.params?.agents ?? []).map((agent) => agent.role);
      if (roles.length && roles.join("\n") !== rows.map((row) => row.role).join("\n")) setAgents(roles);
      for (const row of rows) row.trace.maxTurns = maxTurns;
      log(envelope, null, t("crew.journal.started"));
      activate(rows[0]);
    },

    step(data, envelope) {
      log(envelope, data.agent, stepText(data, labelOf));
      const row = byRole(data.agent);
      if (!row) return;
      activate(row);
      row.none.hidden = true;
      row.trace.add(data);
      if (data.kind === "answer") return finishAgent(row, data);
      row.tool = data.kind === "tool_call" ? data.tool : null;
      paint(row);
    },

    approval_required(_data, envelope) {
      if (!current) return;
      current.approval = true;
      current.trace.setCurrent("approval");
      paint(current);
      log(envelope, current.role, t("components.step_trace.state_approval"));
    },

    approval_resolved(data, envelope) {
      if (!current) return;
      current.approval = false;
      current.trace.setCurrent("running");
      paint(current);
      log(envelope, current.role, t(`crew.journal.${data.decision}`));
    },

    run_ended(data, envelope) {
      const status = data?.status ?? "error";
      log(envelope, null, t(`crew.journal.ended_${status}`));
      for (const row of rows) {
        if (row.state === "current") {
          row.trace.setCurrent(null);
          row.approval = false;
          setState(row, status === "ok" ? "done" : "stopped");
        } else if (row.state === "pending") {
          setState(row, "notrun");
        }
      }
      current = null;
    },
  };

  return {
    root,
    setAgents,
    reset,
    feed(type, data, envelope) {
      handlers[type]?.(data, envelope);
    },
    states: () => Object.fromEntries(rows.map((row) => [row.role, row.state])),
    roles: () => rows.map((row) => row.role),
    // Une issue (validation refusée, email envoyé…) s'inscrit dans la trace de l'agent en cours.
    noteTrace: {
      note(note) {
        const row = current ?? rows.at(-1);
        if (!row) return;
        row.none.hidden = true;
        row.trace.note(note);
      },
    },
    get count() {
      return rows.length;
    },
  };
}
