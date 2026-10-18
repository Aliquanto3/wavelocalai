// Agent seul, `#/agents/seul` (UX-DR28, stories 6.1 à 6.4) : écran à l'état livré.
//
// - Réglages : `wl-model-picker` sur le défaut `agent` (avec sa raison), neuf outils à cocher (« Envoi
//   d'email » décoché ; un outil indisponible n'est pas cochable et garde sa raison en aide).
// - Fil : accueil « Bonjour ! L'agent est prêt. » et actions rapides, puis `wl-chat-thread` pour la
//   réponse finale, qui arrive en flux avec son pied (CO₂, débit, durées) complété de « N étapes » et de
//   « Télécharger ».
// - Panneau « Étapes » : chronomètre, ligne d'état (« Réflexion… », « Appel de l'outil … »,
//   « En attente de votre validation »), puis la trace (liste ordonnée d'étapes dépliables).
// - Validation d'email (D2) : `approval_required` ouvre `ctx.states.confirmEmail` ; la décision est
//   publiée par `approval_resolved`, puis le run reprend (rien ne part sans « Envoyer l'email »).
// - Masqué (on change d'écran), l'écran détache son flux ; au retour il reprend après le dernier `seq`.
//
// Ce module exporte aussi les pièces que partage l'écran Équipe d'agents : trace d'étapes, ligne d'état,
// lecteur d'événements (`driveRun`), icônes (voir « Pièces communes »). Elles vivent ici parce que la
// maquette ne permet pas d'ajouter de composant commun (voir notes/agent-seul.md).

import { element, icon } from "../core/dom.js";
import { errorEnvelope } from "../core/errors.js";
import { formatDuration } from "../core/format.js";
import { loadScreenTexts, plural, t } from "../core/i18n.js";
import { setMaquette, store } from "../core/store.js";
import { findModel, modelDefaults } from "../sim/modeles.js";
import { sim } from "../sim/sim.js";
import { setOllamaDown } from "../sim/systeme.js";

// =============================================================================================
// Pièces communes (réutilisées par equipe-agents.js)
// =============================================================================================

const SVG_NS = "http://www.w3.org/2000/svg";
const speedOf = () => store.get().maquette.speed || 1;

// Le sprite partagé n'a pas d'icône pour les types d'étapes : tracés simples, décoratifs (le libellé
// porte toujours le sens).
const STEP_ICONS = {
  think: "M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2zM9 19h6v2H9z",
  tool: "M3 4h18v16H3zm2 2v12h14V6zm2.2 2.4 3.6 3.6-3.6 3.6-1.4-1.4 2.2-2.2-2.2-2.2zM12 15h5v2h-5z",
  answer: "M4 3h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H8l-5 4V4a1 1 0 0 1 1-1z",
  wait: "M6 2h12v5.5L14 12l4 4.5V22H6v-5.5L10 12 6 7.5z",
  error: "M12 2 1 21h22zm-1 7h2v6h-2zm0 8h2v2h-2z",
  stop: "M6 6h12v12H6z",
  done: "M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z",
};

export function stepIcon(name) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "icon step-icon");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("fill", "currentColor");
  path.setAttribute("fill-rule", "evenodd");
  path.setAttribute("d", STEP_ICONS[name] ?? STEP_ICONS.think);
  svg.append(path);
  return svg;
}

let textsPromise = null;
// Les textes de la trace sont dans i18n/screens/agent-seul.fr.json, aussi pour l'écran Équipe.
export function loadAgentTexts() {
  textsPromise ??= loadScreenTexts("agent-seul");
  return textsPromise;
}

export function waitUntil(condition, timeoutMs = 20000) {
  return new Promise((resolve, reject) => {
    const started = performance.now();
    const check = () => {
      if (condition()) return resolve();
      if (performance.now() - started > timeoutMs) return reject(new Error("Scénario : état jamais atteint"));
      setTimeout(check, 30);
    };
    check();
  });
}

export const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms / speedOf()));

// --- Lecteur d'événements -----------------------------------------------------------------------
// Le simulateur rejoue des scripts de `donnees/flux/` ; il ne sait ni attendre une décision ni jouer
// des événements construits à l'exécution. Ce lecteur publie des événements dans un run du
// simulateur (`run.emit`) : mêmes enveloppes AD-6, mêmes coupures de connexion, mêmes arrêts.

function substitute(value, vars) {
  if (typeof value === "string") {
    const whole = /^\{\{(\w+)\}\}$/.exec(value);
    if (whole && whole[1] in vars) return vars[whole[1]];
    return value.replace(/\{\{(\w+)\}\}/g, (match, name) => (name in vars ? String(vars[name]) : match));
  }
  if (Array.isArray(value)) return value.map((item) => substitute(item, vars));
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, substitute(item, vars)]));
  }
  return value;
}

// Développe `tokens` en événements `token` de 50 ms (même règle que le simulateur).
function expandTokens(events) {
  const out = [];
  for (const event of events) {
    if (!event.tokens) {
      out.push(event);
      continue;
    }
    const { lane, channel = "answer", text, tps = 40 } = event.tokens;
    const perSlice = Math.max(1, Math.round((tps * 50 * 4) / 1000));
    for (let i = 0, first = true; i < text.length; i += perSlice, first = false) {
      out.push({ wait: first ? (event.wait ?? 0) : 50, type: "token", data: { lane, text: text.slice(i, i + perSlice), channel } });
    }
  }
  return out;
}

// Événements d'un script (`{{nom}}` remplacé, `when` faux omis, `tokens` développé).
export function prepareEvents(events, vars = {}) {
  const filtered = substitute(events, vars).filter((event) => !("when" in event) || event.when);
  return expandTokens(filtered);
}

// Joue `events` dans `run`. `{pause: true}` suspend le lecteur (attente d'une décision) jusqu'à
// `resume(événements)`. `errorCode` : erreur injectée après `errorAfter` événements.
export function driveRun(run, events, { errorCode = null, errorAfter = 3, errorDetail = undefined } = {}) {
  const queue = [...events];
  let timer = null;
  let paused = false;
  let stopped = false;
  let emitted = 0;
  const step = () => {
    if (stopped || run.ended || paused || !queue.length) return;
    const next = queue[0];
    if (next.pause) {
      queue.shift();
      paused = true;
      return;
    }
    const slow = store.get().maquette.slowLoad && next.slow_wait !== undefined;
    const wait = (slow ? next.slow_wait : (next.wait ?? 0)) / speedOf();
    timer = setTimeout(() => {
      if (stopped || run.ended) return;
      queue.shift();
      if (errorCode && emitted >= errorAfter) {
        run.fail(errorCode, errorDetail);
        return;
      }
      run.emit(next.type, next.data ?? {});
      emitted += 1;
      step();
    }, wait);
  };
  step();
  run.done.then(() => clearTimeout(timer));
  return {
    stop() {
      stopped = true;
      clearTimeout(timer);
    },
    resume(extra = []) {
      paused = false;
      queue.unshift(...extra);
      step();
    },
    get paused() {
      return paused;
    },
  };
}

// --- Dialogue de validation ------------------------------------------------------------------------
// `wl-confirm-dialog` n'a pas de méthode pour se fermer de l'extérieur : l'événement `cancel` natif
// du `<dialog>` suffit (même chemin qu'Échap).
export function dialogElement() {
  return document.querySelector("#main > wl-confirm-dialog dialog[open]");
}

export function closeApprovalDialog() {
  dialogElement()?.dispatchEvent(new Event("cancel", { cancelable: true }));
}

// Clique « Envoyer l'email » (true) ou « Annuler » (false) dans le dialogue ouvert (scénarios).
export function decideInDialog(approve) {
  const dialog = dialogElement();
  if (!dialog) return false;
  const buttons = dialog.querySelectorAll(".wl-dialog-actions .btn");
  (approve ? buttons[1] : buttons[0])?.click();
  return true;
}

// --- Fichiers produits par les outils ------------------------------------------------------------------
// Le vrai front lit `GET /api/outputs/{name}` ; la maquette fabrique un petit fichier fictif.
export function openOutput(name) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 120"><title>${name}</title><rect x="20" y="60" width="24" height="40" fill="#451DC7"/><rect x="60" y="45" width="24" height="55" fill="#451DC7"/><rect x="100" y="35" width="24" height="65" fill="#451DC7"/><rect x="140" y="20" width="24" height="80" fill="#451DC7"/></svg>`;
  const blob = new Blob([name.endsWith(".svg") ? svg : "Fichier fictif de la maquette.\n"], {
    type: name.endsWith(".svg") ? "image/svg+xml" : "text/plain",
  });
  const link = element("a");
  link.href = URL.createObjectURL(blob);
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

// --- Ligne d'état d'un run d'agent --------------------------------------------------------------------
// Même rendu que `wl-run-status` (classes `wl-run-*`), avec les étapes propres aux agents que le
// composant commun ne connaît pas : « Réflexion… », « Appel de l'outil … », « En attente de votre
// validation ». Chronomètre local (seul chiffre calculé ici, AD-20).

const STAGE_KEYS = {
  starting: "components.run_status.starting",
  loading: "components.run_status.loading",
  generating: "components.run_status.generating",
  stopping: "components.run_status.stopping",
  ok: "components.run_status.ok",
  cancelled: "components.run_status.cancelled",
  error: "components.run_status.error",
  interrupted: "components.run_status.interrupted",
  thinking: "agent.status.thinking",
  tool: "agent.status.tool",
  waiting: "agent.status.waiting",
};
const FINAL = new Set(["ok", "cancelled", "error", "interrupted"]);

export function createAgentStatus({ stoppable = false, onStop = () => {} } = {}) {
  const stage = element("p", "wl-run-stage");
  stage.setAttribute("role", "status");
  stage.tabIndex = -1;
  const timer = element("span", "wl-run-timer");
  timer.setAttribute("role", "timer");
  timer.setAttribute("aria-label", t("components.run_status.elapsed"));
  const line = element("div", "wl-run-line");
  line.append(stage, timer);
  let stop = null;
  let hint = null;
  if (stoppable) {
    stop = element("button", "btn wl-run-stop", t("components.run_status.stop"));
    stop.type = "button";
    stop.setAttribute("aria-keyshortcuts", "Escape");
    stop.addEventListener("click", () => onStop());
    hint = element("span", "help wl-run-hint", t("components.run_status.stop_hint"));
    line.append(stop, hint);
  }
  const root = element("div", "wl-run-status agent-status");
  root.append(line);
  root.hidden = true;

  const state = { stage: "starting", vars: {}, startMs: null, endMs: null, interval: null, running: false, stopping: false };

  const elapsed = () => (state.startMs === null ? 0 : Math.max(0, Math.floor(((state.endMs ?? Date.now()) - state.startMs) / 1000)));
  const renderTimer = () => {
    timer.textContent = formatDuration(elapsed());
  };
  function render() {
    let text = t(STAGE_KEYS[state.stage] ?? STAGE_KEYS.starting, state.vars);
    if (state.vars.agent && !FINAL.has(state.stage)) text = t("agent.status.with_agent", { agent: state.vars.agent, text });
    stage.textContent = text;
    root.dataset.stage = state.stage;
    renderTimer();
    if (stop) {
      stop.hidden = !state.running;
      stop.disabled = state.stopping;
      hint.hidden = !state.running;
    }
  }
  return {
    root,
    get running() {
      return state.running;
    },
    get stage() {
      return state.stage;
    },
    start(ts) {
      clearInterval(state.interval);
      const started = Date.parse(ts);
      state.startMs = Number.isNaN(started) ? Date.now() : Math.min(started, Date.now());
      state.endMs = null;
      state.running = true;
      state.stopping = false;
      state.stage = "starting";
      state.vars = {};
      state.interval = setInterval(renderTimer, 250);
      root.hidden = false;
      render();
    },
    set(next, vars = {}) {
      if (!state.running || state.stopping) return;
      state.stage = next;
      state.vars = vars;
      render();
    },
    stopping() {
      if (!state.running || state.stopping) return;
      if (stop && document.activeElement === stop) stage.focus();
      state.stopping = true;
      state.stage = "stopping";
      state.vars = {};
      render();
    },
    end(finalStatus) {
      const hadFocus = stop && document.activeElement === stop;
      clearInterval(state.interval);
      state.interval = null;
      state.endMs = Date.now();
      state.running = false;
      state.stopping = false;
      state.stage = FINAL.has(finalStatus) ? finalStatus : "error";
      state.vars = {};
      root.hidden = false;
      render();
      if (hadFocus) stage.focus();
    },
    reset() {
      clearInterval(state.interval);
      state.interval = null;
      state.running = false;
      state.startMs = null;
      state.endMs = null;
      root.hidden = true;
    },
    dispose() {
      clearInterval(state.interval);
    },
  };
}

// --- Trace d'étapes ------------------------------------------------------------------------------------
// `wl-step-trace` (UX-DR28) : liste ordonnée, une ligne dépliable par étape (motif « disclosure »
// APG : un bouton `aria-expanded`). Une étape = un `step_id` : un événement de début (sans durée), puis un
// événement de fin (avec `duration_s`). Les lignes se mettent à jour sur place : le focus et l'état
// déplié ne bougent pas quand les étapes suivantes arrivent. La liste n'est pas `aria-live`.

let traceCounter = 0;

export function createStepTrace({ label, showAgent = false, agentName = (id) => id, toolLabel = (id) => id } = {}) {
  const root = element("ol", "step-trace");
  root.setAttribute("aria-label", label);
  root.hidden = true;
  const rows = new Map();
  const uid = `trace-${++traceCounter}`;

  const labelOf = (row) => {
    if (row.limit) return row.summary;
    if (row.kind === "think") return t("agent.step.think");
    if (row.kind === "answer") return t("agent.step.answer");
    return toolLabel(row.tool);
  };
  const stateText = (row) => {
    switch (row.state) {
      case "running":
        return t("agent.step.running");
      case "waiting":
        return t("agent.step.waiting");
      case "error":
        return `${t("agent.step.error_result")} · ${formatDuration(row.duration)}`;
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
      parts.push(element("p", "step-field", t("agent.step.arguments")));
      parts.push(element("pre", "step-code", JSON.stringify(row.args, null, 2)));
    }
    const text = row.kind === "tool" ? row.result : row.summary;
    if (text) {
      parts.push(element("p", "step-field", row.kind === "tool" ? t("agent.step.result") : t("agent.step.summary")));
      parts.push(element("p", "step-text", text));
    }
    if (row.file) {
      const name = row.file.split("/").pop();
      const open = element("button", "btn step-file", t("agent.step.open_file"));
      open.type = "button";
      open.setAttribute("aria-label", t("agent.step.open_file_named", { name }));
      open.addEventListener("click", () => openOutput(name));
      parts.push(open);
    }
    if (!parts.length) parts.push(element("p", "help", t("agent.step.nothing_yet")));
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

// =============================================================================================
// Écran Agent seul
// =============================================================================================

let counter = 0;
let view = null; // l'instance montée, pour les scénarios

export async function mount(host, ctx) {
  const uid = `agent-${++counter}`;
  const data = await ctx.data("agent-seul.json");
  let disposed = false;

  // --- État des outils -------------------------------------------------------------------------------
  const toolsState = structuredClone(data.tools).map((tool) => ({ ...tool, checked: tool.default_checked }));
  const toolLabel = (id) => toolsState.find((tool) => tool.id === id)?.label ?? id;

  // --- Structure -------------------------------------------------------------------------------------
  const guard = ctx.states.ollamaGuard();
  const picker = document.createElement("wl-model-picker");
  picker.setAttribute("purpose", "agent");
  const modelWarning = element("p", "help agent-model-warning");
  modelWarning.hidden = true;
  const settings = element("div", "agent-settings");
  settings.append(picker, modelWarning);

  const toolsGroup = element("fieldset", "agent-tools");
  toolsGroup.append(element("legend", "", t("agent.tools.legend")), element("p", "help", t("agent.tools.intro")));
  const toolList = element("ul", "agent-tool-list");
  toolsGroup.append(toolList);

  const hello = ctx.states.emptyState({ title: t("agent.hello.title"), text: t("agent.hello.text"), level: 2 });
  hello.classList.add("agent-hello");
  const quickTitle = element("h3", "agent-quick-title", t("agent.hello.quick"));
  const quickList = element("ul", "agent-quick");
  for (const action of data.quick_actions) {
    const item = element("li");
    const button = element("button", "btn agent-quick-button");
    button.type = "button";
    button.dataset.action = action.id;
    button.append(element("span", "agent-quick-label", action.label), element("span", "help", action.description));
    button.addEventListener("click", () => {
      input.value = action.prompt;
      input.focus();
      if (action.needs_tool && !toolsState.find((tool) => tool.id === action.needs_tool)?.checked) {
        say(t("agent.hello.tool_off", { tool: toolLabel(action.needs_tool) }));
      }
    });
    item.append(button);
    quickList.append(item);
  }
  hello.append(quickTitle, quickList);

  const thread = document.createElement("wl-chat-thread");
  const firstLoad = element("p", "help agent-first-load", t("agent.first_load"));
  firstLoad.hidden = true;
  const notices = element("div", "agent-notices");
  const error = document.createElement("wl-error");
  error.setAttribute("alert", "");
  const conversation = element("div", "agent-conversation");
  conversation.append(hello, thread, firstLoad, notices, error);

  const stepsTitle = element("h2", "agent-steps-title", t("agent.steps.title"));
  const status = createAgentStatus();
  const trace = createStepTrace({ label: t("agent.steps.label"), toolLabel });
  const stepsEmpty = element("p", "help agent-steps-empty", t("agent.steps.empty"));
  const approvalNote = element("p", "help agent-approval-note", t("agent.approval.expiry", { minutes: data.approval_expiry_min }));
  approvalNote.hidden = true;
  const steps = element("section", "agent-steps");
  steps.setAttribute("aria-labelledby", `${uid}-steps-title`);
  stepsTitle.id = `${uid}-steps-title`;
  steps.append(stepsTitle, status.root, approvalNote, stepsEmpty, trace.root);

  const input = element("textarea", "agent-input");
  input.id = `${uid}-task`;
  input.rows = 3;
  input.setAttribute("aria-describedby", `${uid}-keys`);
  const inputLabel = element("label", "agent-input-label", t("agent.task"));
  inputLabel.htmlFor = input.id;
  const keys = element("p", "help", t("agent.keys"));
  keys.id = `${uid}-keys`;
  const send = element("button", "btn btn-primary", t("agent.send"));
  send.type = "submit";
  const stopButton = element("button", "btn", t("agent.stop"));
  stopButton.type = "button";
  stopButton.setAttribute("aria-keyshortcuts", "Escape");
  const clear = element("button", "btn", t("agent.clear"));
  clear.type = "button";
  const actions = element("div", "agent-actions");
  actions.append(send, stopButton, clear);
  const reason = element("p", "help agent-reason");
  reason.id = `${uid}-reason`;
  send.setAttribute("aria-describedby", reason.id);
  const composer = element("form", "agent-composer");
  composer.append(inputLabel, input, keys, actions, reason);

  const layout = element("div", "agent-layout");
  conversation.classList.add("agent-area-thread");
  steps.classList.add("agent-area-steps");
  composer.classList.add("agent-area-composer");
  layout.append(conversation, steps, composer);

  host.replaceChildren(
    element("h1", "", ctx.route.title),
    ctx.tabs(),
    element("p", "lead", t("agent.lead")),
    guard,
    settings,
    toolsGroup,
    layout,
  );

  // --- Outils --------------------------------------------------------------------------------------
  function renderTools() {
    toolList.replaceChildren(
      ...toolsState.map((tool) => {
        const id = `${uid}-tool-${tool.id}`;
        const item = element("li", "agent-tool");
        item.dataset.available = String(tool.available);
        const box = element("input");
        box.type = "checkbox";
        box.id = id;
        box.checked = tool.checked && tool.available;
        box.setAttribute("aria-describedby", `${id}-help`);
        if (!tool.available) box.setAttribute("aria-disabled", "true");
        box.addEventListener("click", (event) => {
          if (!tool.available) event.preventDefault(); // non cochable, mais focalisable
        });
        box.addEventListener("change", () => {
          tool.checked = box.checked;
        });
        const label = element("label", "agent-tool-name", tool.label);
        label.htmlFor = id;
        const head = element("div", "agent-tool-head");
        head.append(box, label);
        const help = element("p", "help agent-tool-help");
        help.id = `${id}-help`;
        help.append(document.createTextNode(tool.description));
        if (tool.sensitive) help.append(document.createTextNode(` ${t("agent.tools.sensitive")}`));
        item.append(head, help);
        if (!tool.available) {
          const why = element("p", "agent-tool-reason", tool.reason);
          why.id = `${id}-reason`;
          box.setAttribute("aria-describedby", `${id}-help ${why.id}`);
          item.append(why);
        }
        return item;
      }),
    );
  }
  renderTools();

  const selectedTools = () => toolsState.filter((tool) => tool.checked && tool.available).map((tool) => tool.id);
  const emailOn = () => selectedTools().includes("envoi_email");

  // --- État du run -----------------------------------------------------------------------------------
  let run = null;
  let attachment = null;
  let lastSeq = 0;
  let answer = null;
  let current = null; // { tag, name, origin, text, vars, metrics }
  let lastMessage = "";
  let tail = null;
  let approvalOpen = false;
  let expiring = false;
  let stopping = false;
  const transcript = [];
  const loaded = new Set();
  let wasHidden = host.hidden;
  const running = () => run !== null;

  function say(text, tone = "info") {
    notices.replaceChildren(ctx.states.notice(text, { tone }));
  }

  function render() {
    const busy = running();
    const noModel = !picker.selected;
    send.disabled = busy || noModel;
    stopButton.hidden = !busy;
    stopButton.disabled = stopping;
    clear.hidden = thread.empty;
    clear.disabled = busy;
    hello.hidden = !thread.empty;
    reason.textContent = busy ? t("agent.busy_reason") : noModel ? t("agent.no_model") : "";
    reason.hidden = !reason.textContent;
    stepsEmpty.hidden = trace.count > 0 || status.running;
    const model = picker.selected;
    const warn = Boolean(model && model.tools_verified === false);
    modelWarning.hidden = !warn;
    if (warn) modelWarning.textContent = t("agent.model_warning");
  }

  function ensureAnswer() {
    if (!answer) answer = thread.beginAnswer({ name: current.name, origin: current.origin });
    return answer;
  }

  function resultText(decision) {
    return data.results[decision] ?? "";
  }

  // --- Étapes et validation --------------------------------------------------------------------------
  function onStep(step) {
    trace.apply(step);
    const open = step.duration_s === null || step.duration_s === undefined;
    if (open) {
      if (step.kind === "think") status.set("thinking");
      else if (step.kind === "tool_call") status.set("tool", { tool: toolLabel(step.tool) });
      else if (step.kind === "answer") status.set("generating");
    }
    render();
  }

  async function onApproval(approval) {
    const thisRun = run;
    if (!thisRun) return;
    trace.waitOnLast();
    status.set("waiting");
    approvalNote.hidden = false;
    ctx.announce(t("agent.status.waiting"));
    approvalOpen = true;
    let approved = false;
    try {
      approved = await ctx.states.confirmEmail({ to: approval.to, subject: approval.subject, body: approval.body });
    } finally {
      approvalOpen = false;
      approvalNote.hidden = true;
    }
    if (disposed || thisRun !== run || thisRun.ended) return; // le run s'est terminé pendant l'attente : rien n'est envoyé
    const decision = expiring ? "expired" : approved ? "approved" : "rejected";
    expiring = false;
    const script = await ctx.data("flux/agent-seul-email-suite.json");
    if (disposed || thisRun !== run || thisRun.ended) return;
    const answers = { approved: "email_envoye", rejected: "email_refuse", expired: "email_expire" };
    const vars = {
      ...current.vars,
      decision,
      result_text: resultText(decision),
      approval_s: { approved: 6.4, rejected: 4.8, expired: 600 }[decision],
      reflection:
        decision === "approved"
          ? "L'email est parti. Je le confirme à l'utilisateur."
          : "Rien n'est parti. Je l'annonce à l'utilisateur.",
      answer: data.answers[answers[decision]],
    };
    tail = driveRun(thisRun, prepareEvents(script.events, vars));
  }

  function finish(finalStatus, payload = {}) {
    closeApprovalDialog();
    tail?.stop();
    tail = null;
    approvalNote.hidden = true;
    const bubble = ensureAnswer();
    bubble.end({ status: finalStatus });
    if (finalStatus === "ok") addFootExtras(bubble);
    trace.finish(finalStatus);
    status.end(finalStatus);
    firstLoad.hidden = true;
    if (payload.error) error.error = payload.error;
    transcript.push({ role: "assistant", name: current.name, origin: current.origin, text: current.text, status: finalStatus });
    attachment?.close();
    run = null;
    attachment = null;
    answer = null;
    stopping = false;
    render();
  }

  function markdownOf() {
    const lines = transcript.map((message) =>
      message.role === "user" ? `**Vous** : ${message.text}` : `**${message.name}** (${message.origin}) : ${message.text}`,
    );
    const stepLines = trace.entries().map((row) => `${row.n}. ${row.node.label.textContent} : ${row.node.state.textContent}`);
    return `# Tâche confiée à l'agent\n\n${lines.join("\n\n")}\n\n## Étapes\n\n${stepLines.join("\n")}\n`;
  }

  function addFootExtras(bubble) {
    const metric = document.createElement("wl-metric");
    metric.setAttribute("label", t("agent.foot.steps"));
    metric.setAttribute("value", plural("agent.steps_count", trace.count));
    const download = element("button", "btn agent-download", t("agent.download"));
    download.type = "button";
    download.addEventListener("click", () => {
      const blob = new Blob([markdownOf()], { type: "text/markdown" });
      const link = element("a");
      link.href = URL.createObjectURL(blob);
      link.download = "tache-agent.md";
      link.click();
      setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    });
    bubble.foot.append(metric, download);
  }

  // --- Flux ------------------------------------------------------------------------------------------
  const handlers = {
    "*": (_data, envelope) => {
      lastSeq = envelope.seq;
    },
    run_started: (_data, envelope) => {
      status.start(envelope.ts);
      render();
    },
    model_loading: () => {
      firstLoad.hidden = false;
      status.set("loading");
    },
    model_loaded: (payload) => {
      firstLoad.hidden = true;
      loaded.add(payload.tag);
      status.set("thinking");
    },
    step: (payload) => onStep(payload),
    token: (payload) => {
      const bubble = ensureAnswer();
      bubble.token(payload?.text, payload?.channel);
      if (payload?.channel !== "thought") current.text += payload.text;
      status.set("generating");
    },
    approval_required: (payload) => {
      onApproval(payload).catch((failure) => console.error(failure));
    },
    approval_resolved: (payload) => {
      ctx.announce(resultText(payload.decision));
      if (run && !run.ended) status.set("thinking");
    },
    retry: (payload) => {
      ensureAnswer().retry(payload?.reason);
      current.text = "";
    },
    metrics: (payload) => {
      ensureAnswer().metrics(payload);
      current.metrics = payload;
    },
    run_ended: (payload) => finish(payload?.status ?? "error", payload ?? {}),
  };

  function follow(simRun, { after = 0 } = {}) {
    run = simRun;
    lastSeq = after;
    attachment = simRun.attach(handlers, { after });
    render();
  }

  // --- Actions ---------------------------------------------------------------------------------------
  function pickScript(message) {
    if (/e-?mail|courriel/i.test(message)) {
      return emailOn() ? { script: "agent-seul-email", answer: "analyse" } : { script: "agent-seul-analyse", answer: "sans_email" };
    }
    if (/poste|processeur|m[ée]moire/i.test(message)) return { script: "agent-seul-poste", answer: "poste" };
    if (/marge|devis|calcul/i.test(message)) return { script: "agent-seul-devis", answer: "devis" };
    return { script: "agent-seul-analyse", answer: "analyse" };
  }

  function varsFor(model, message, answerKey) {
    const metrics = { lane: model.tag, ...(data.metrics[model.tag] ?? data.metrics.default_local) };
    return {
      tag: model.tag,
      tools: selectedTools(),
      loading: model.origin === "local" && !loaded.has(model.tag),
      load_s: metrics.load_s,
      tps: metrics.tps,
      metrics,
      answer: data.answers[answerKey] ?? "",
      prompt: message,
      email_to: data.email.to,
      email_subject: data.email.subject,
      email_body: data.email.body,
    };
  }

  // `options` : { script, answer, errorCode, errorAfter, errorDetail } choisis par un scénario.
  async function submit(options = {}) {
    if (running()) return null;
    const message = input.value;
    if (!message.trim()) {
      input.focus();
      return null;
    }
    error.error = null;
    notices.replaceChildren();
    const model = picker.selected;
    if (!model) {
      error.error = errorEnvelope("no_model", { detail: { purpose: "agent" } });
      return null;
    }
    // Ce que `POST /api/agents/runs` refuserait avant de créer le run.
    let refused = sim.precheck({ origin: model.origin, kind: "agent", model });
    if (refused?.code === "run_busy") {
      const other = sim.get(refused.detail.run_id);
      if (other.options.vars?.mode === "crew") {
        const link = element("a", "btn", t("agent.busy_crew_link"));
        link.href = "#/agents/equipe";
        notices.replaceChildren(ctx.states.notice(t("agent.busy_crew"), { tone: "warning" }), link);
        return null;
      }
      const joined = (await findModel(other.options.vars?.tag)) ?? model;
      current = { tag: joined.tag, name: joined.name, origin: joined.origin, text: "", vars: other.options.vars ?? {} };
      trace.clear();
      thread.addUserMessage(other.options.vars?.prompt ?? "");
      say(t("agent.joined"));
      follow(other);
      return run;
    }
    if (refused?.code === "ram_guard") {
      refused = errorEnvelope("ram_guard", {
        detail: {
          technical: "hardware.fits : besoin estimé 5,2 Go (poids 4,7 Go + contexte 0,5 Go), libre 2,8 Go",
          needed_gb: 5.2,
          free_gb: 2.8,
          suggested_model: "qwen3.5:2b",
        },
      });
    }
    if (refused) {
      error.error = refused; // la tâche reste dans le champ
      return null;
    }
    lastMessage = message;
    thread.addUserMessage(message);
    transcript.push({ role: "user", text: message });
    input.value = "";
    const picked = options.script ? { script: options.script, answer: options.answer ?? "analyse" } : pickScript(message);
    const vars = varsFor(model, message, picked.answer);
    current = { tag: model.tag, name: model.name, origin: model.origin, text: "", vars };
    trace.clear();
    const simRun = sim.play(picked.script, null, {
      vars: { ...vars, mode: "solo" },
      kind: "agent",
      origin: model.origin,
      module: "agent",
      error: options.errorCode ?? undefined,
      errorAfter: options.errorAfter,
      errorDetail: model.provider_name ? { provider: model.provider, provider_name: model.provider_name } : undefined,
    });
    follow(simRun);
    return simRun;
  }

  function requestStop() {
    if (!running() || stopping) return;
    stopping = true;
    status.stopping();
    render();
    sim.cancel(run.id);
  }

  function clearConversation() {
    if (running()) return;
    thread.clear();
    transcript.length = 0;
    trace.clear();
    status.reset();
    error.error = null;
    say(t("agent.cleared"), "success");
    render();
    input.focus();
  }

  composer.addEventListener("submit", (event) => {
    event.preventDefault();
    submit();
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      submit();
    }
  });
  stopButton.addEventListener("click", requestStop);
  clear.addEventListener("click", clearConversation);
  picker.addEventListener("wl-model-change", render);
  const onKeydown = (event) => {
    if (event.key === "Escape" && !event.defaultPrevented && running() && !host.hidden) {
      event.preventDefault();
      requestStop();
    }
  };
  document.addEventListener("keydown", onKeydown);

  // Boutons d'action des erreurs (AD-18 : tirés du code et de `detail`).
  error.addEventListener("wl-error-action", async (event) => {
    const id = event.detail.id;
    if (id === "retry") {
      error.error = null;
      if (!input.value) input.value = lastMessage;
      submit();
    } else if (id === "allow_cloud") {
      store.set({ allowCloud: true });
      error.error = null;
    } else if (id === "use_local" || id === "choose_other") {
      const defaults = await modelDefaults("agent", false).catch(() => ({ tags: [] }));
      if (defaults.tags[0]) picker.value = defaults.tags[0];
      error.error = null;
    } else if (id === "smaller") {
      const suggested = error.error?.detail?.suggested_model;
      const model = suggested ? await findModel(suggested) : null;
      if (model) picker.value = model.tag;
      setMaquette({ ramGuard: false });
      error.error = null;
      say(t("agent.smaller", { name: model?.name ?? suggested ?? "" }), "success");
    } else if (id === "unload") {
      setMaquette({ ramGuard: false });
      error.error = null;
      say(t("agent.unloaded"), "success");
    }
    render();
  });

  // --- Écran masqué puis revu (reprise par `?after=<seq>`) -------------------------------------------
  const visibility = new MutationObserver(() => {
    if (host.hidden === wasHidden) return;
    wasHidden = host.hidden;
    if (wasHidden) {
      thread.suspend();
      attachment?.close();
      attachment = null;
    } else {
      thread.resume();
      if (running()) attachment = run.attach(handlers, { after: lastSeq });
    }
  });
  visibility.observe(host, { attributes: true, attributeFilter: ["hidden"] });

  view = {
    host,
    picker,
    input,
    thread,
    trace,
    status,
    submit,
    get run() {
      return run;
    },
    get answerText() {
      return current?.text ?? "";
    },
    get approvalOpen() {
      return approvalOpen;
    },
    get steps() {
      return trace.count;
    },
    whenPickerReady: () => waitUntil(() => picker.selected !== null || picker.querySelector("wl-error:not([hidden])"), 5000),
    stop: requestStop,
    refresh: render,
    setTool(id, checked) {
      const tool = toolsState.find((candidate) => candidate.id === id);
      if (tool && tool.available) tool.checked = checked;
      renderTools();
    },
    // SMTP absent : « Envoi d'email » indisponible, décoché, avec sa raison.
    setSmtp(present) {
      const tool = toolsState.find((candidate) => candidate.id === "envoi_email");
      tool.available = present;
      tool.reason = present ? null : data.smtp_reason;
      if (!present) tool.checked = false;
      renderTools();
    },
    // Aucune réponse en 10 min : le dialogue se ferme et l'envoi est refusé (`expired`).
    expireApproval() {
      expiring = true;
      closeApprovalDialog();
    },
  };

  render();
  return () => {
    disposed = true;
    view = null;
    visibility.disconnect();
    document.removeEventListener("keydown", onKeydown);
    guard.dispose?.();
    closeApprovalDialog();
    tail?.stop();
    attachment?.close();
    status.dispose();
  };
}

// =============================================================================================
// Scénarios
// =============================================================================================

// Repart de l'état d'ouverture, attend le sélecteur, puis applique `setup` (états globaux).
async function fresh(ctx, setup = () => {}) {
  await ctx.reset();
  setup();
  await waitUntil(() => view !== null);
  await view.whenPickerReady();
}

async function choose(tag) {
  await waitUntil(() => view.picker.knows(tag), 5000);
  view.picker.value = tag;
  view.refresh(); // une valeur posée par le code n'émet pas wl-model-change
}

async function ask(ctx, { model, prompt, ...options } = {}) {
  if (model) await choose(model);
  const data = await ctx.data("agent-seul.json");
  view.input.value = prompt ?? data.quick_actions[0].prompt;
  return view.submit(options);
}

const untilDone = (simRun) => simRun?.done ?? Promise.resolve();
const untilSteps = (count) => waitUntil(() => view.steps >= count);

async function emailRun(ctx, options = {}) {
  const data = await ctx.data("agent-seul.json");
  view.setTool("envoi_email", true);
  return ask(ctx, { prompt: data.prompts.email, ...options });
}

export const scenarios = [
  {
    id: "vide",
    label: "Accueil de l'agent : « Bonjour ! », actions rapides, outils",
    run: (ctx) => fresh(ctx),
  },
  {
    id: "outil-indisponible",
    label: "Envoi d'email indisponible (SMTP absent) : pastille non cochable avec sa raison",
    async run(ctx) {
      await fresh(ctx);
      view.setSmtp(false);
    },
  },
  {
    id: "aucun-modele",
    label: "Aucun modèle avec défaut : « Choisissez un modèle avec outils vérifiés », lancement désactivé",
    run: (ctx) => fresh(ctx, () => setMaquette({ noLocalModel: true })),
  },
  {
    id: "modele-sans-outils",
    label: "Modèle sans outils vérifiés : avertissement",
    async run(ctx) {
      await fresh(ctx);
      await choose("gemma4:1b");
      await waitUntil(() => !view.host.querySelector(".agent-model-warning").hidden);
    },
  },
  {
    id: "etapes-en-cours",
    label: "Le panneau « Étapes » se remplit pendant la tâche",
    async run(ctx) {
      await fresh(ctx);
      await ask(ctx);
      await untilSteps(3);
    },
  },
  {
    id: "tache-terminee",
    label: "Tâche terminée : quatre étapes, réponse, CO₂ mesuré, Télécharger",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await ask(ctx));
    },
  },
  {
    id: "etape-depliee",
    label: "Une étape dépliée : arguments, résultat, « Ouvrir le fichier »",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await ask(ctx));
      view.trace.expand("s3");
    },
  },
  {
    id: "erreur-outil",
    label: "Un outil échoue : « Résultat : erreur », l'agent poursuit",
    async run(ctx) {
      await fresh(ctx);
      const data = await ctx.data("agent-seul.json");
      await untilDone(await ask(ctx, { prompt: data.prompts.erreur_outil, script: "agent-seul-erreur-outil", answer: "erreur_outil" }));
      view.trace.expand("s2");
    },
  },
  {
    id: "bornes-atteintes",
    label: "Borne de tours : « Arrêt : nombre d'étapes maximal atteint (12) »",
    async run(ctx) {
      await fresh(ctx);
      const data = await ctx.data("agent-seul.json");
      await untilDone(await ask(ctx, { prompt: data.prompts.bornes, script: "agent-seul-bornes", answer: "bornes" }));
    },
  },
  {
    id: "validation-email",
    label: "« Rien ne part sans moi » : dialogue de validation de l'email",
    async run(ctx) {
      await fresh(ctx);
      await emailRun(ctx);
      await waitUntil(() => view.approvalOpen);
    },
  },
  {
    id: "email-envoye",
    label: "Email approuvé : « Email envoyé. » dans la trace, l'agent conclut",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await emailRun(ctx);
      await waitUntil(() => view.approvalOpen);
      decideInDialog(true);
      await untilDone(simRun);
      view.trace.expand("s4");
    },
  },
  {
    id: "email-annule",
    label: "Email refusé : « Envoi annulé : l'agent en est informé. »",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await emailRun(ctx);
      await waitUntil(() => view.approvalOpen);
      decideInDialog(false);
      await untilDone(simRun);
      view.trace.expand("s4");
    },
  },
  {
    id: "validation-expiree",
    label: "Sans réponse en 10 min : « Validation expirée : email non envoyé. »",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await emailRun(ctx);
      await waitUntil(() => view.approvalOpen);
      view.expireApproval();
      await untilDone(simRun);
    },
  },
  {
    id: "email-non-coche",
    label: "Demande d'email avec l'outil décoché : l'agent le dit et ne prépare rien",
    async run(ctx) {
      await fresh(ctx);
      const data = await ctx.data("agent-seul.json");
      await untilDone(await ask(ctx, { prompt: data.prompts.email }));
    },
  },
  {
    id: "arret",
    label: "Arrêter pendant la tâche : étapes et partiel gardés, « Arrêté »",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await ask(ctx);
      await untilSteps(3);
      view.stop();
      await untilDone(simRun);
    },
  },
  {
    id: "premier-chargement-lent",
    label: "Premier chargement lent du modèle (8 à 26 s)",
    async run(ctx) {
      await fresh(ctx, () => setMaquette({ slowLoad: true }));
      await ask(ctx);
      await waitUntil(() => view.status.stage === "loading");
    },
  },
  {
    id: "reponse-cloud-estimee",
    label: "Modèle cloud : CO₂ « estimé »",
    async run(ctx) {
      await fresh(ctx, () => ctx.store.set({ allowCloud: true }));
      await untilDone(await ask(ctx, { model: "gpt-5-mini" }));
    },
  },
  {
    id: "reponse-cloud-non-mesurable",
    label: "Modèle cloud : CO₂ « non mesurable » avec sa raison",
    async run(ctx) {
      await fresh(ctx, () => ctx.store.set({ allowCloud: true }));
      await untilDone(await ask(ctx, { model: "claude-haiku-4-5" }));
    },
  },
  {
    id: "rejoint-409",
    label: "Une tâche tourne déjà (autre onglet) : 409 rejoint, étapes rejouées",
    async run(ctx) {
      await fresh(ctx);
      const data = await ctx.data("agent-seul.json");
      const model = await findModel("qwen3.6:7b");
      const metrics = { lane: model.tag, ...data.metrics[model.tag] };
      sim.play("agent-seul-poste", null, {
        kind: "agent",
        module: "agent",
        vars: { tag: model.tag, tools: [], loading: false, load_s: null, tps: 18, metrics, answer: data.answers.poste, prompt: "Donne-moi l'état du poste.", mode: "solo" },
      });
      await pause(400);
      await ask(ctx);
      await untilSteps(2);
    },
  },
  {
    id: "reprise-au-retour",
    label: "Aller sur l'Accueil pendant la tâche, puis revenir : reprise sans perte",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await ask(ctx);
      await untilSteps(2);
      await ctx.navigate("/");
      await pause(1500);
      await ctx.navigate("/agents/seul");
      await untilDone(simRun);
    },
  },
  {
    id: "connexion-perdue",
    label: "Connexion perdue pendant la tâche, puis reprise sans doublon",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await ask(ctx);
      await untilSteps(2);
      simRun.cut(4000);
      await pause(1500);
      await untilDone(simRun);
      await waitUntil(() => ctx.store.get().connection.status === "open");
    },
  },
  {
    id: "serveur-redemarre",
    label: "Le serveur redémarre pendant la tâche : « Interrompu »",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await ask(ctx);
      await untilSteps(2);
      sim.restartServer();
      await untilDone(simRun);
    },
  },
  {
    id: "serveur-redemarre-en-attente",
    label: "Le serveur redémarre pendant la validation : « Interrompu », l'email n'est jamais envoyé",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await emailRun(ctx);
      await waitUntil(() => view.approvalOpen);
      sim.restartServer();
      await untilDone(simRun);
    },
  },
  {
    id: "erreur-interrompue",
    label: "Erreur « interrupted » : Ollama arrête la génération, la trace est gardée",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await ask(ctx, { errorCode: "interrupted", errorAfter: 6 }));
    },
  },
  {
    id: "erreur-delai",
    label: "Erreur « timeout » : délai dépassé",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await ask(ctx, { errorCode: "timeout", errorAfter: 5 }));
    },
  },
  {
    id: "erreur-ollama-arrete",
    label: "Ollama arrêté : bandeau et erreur à l'envoi",
    async run(ctx) {
      await fresh(ctx, () => setOllamaDown(true));
      await ask(ctx, { model: "qwen3.6:7b" });
    },
  },
  {
    id: "erreur-cloud-injoignable",
    label: "Fournisseur cloud injoignable",
    async run(ctx) {
      await fresh(ctx, () => ctx.store.set({ allowCloud: true }));
      await untilDone(await ask(ctx, { model: "claude-haiku-4-5", errorCode: "cloud_unreachable", errorAfter: 3 }));
    },
  },
  {
    id: "erreur-cle-absente",
    label: "Clé d'API absente (Mistral)",
    async run(ctx) {
      await fresh(ctx, () => ctx.store.set({ allowCloud: true }));
      await ask(ctx, { model: "mistral-small-latest" });
    },
  },
  {
    id: "cloud-non-autorise",
    label: "Modèle cloud choisi, cloud désactivé : « Autoriser le cloud »",
    async run(ctx) {
      await fresh(ctx);
      ctx.store.set({ allowCloud: true });
      await choose("gpt-5-mini");
      const data = await ctx.data("agent-seul.json");
      view.input.value = data.quick_actions[0].prompt;
      ctx.store.set({ allowCloud: false });
      await view.submit();
    },
  },
  {
    id: "cloud-retire",
    label: "Cloud désactivé pendant qu'un modèle cloud est choisi",
    async run(ctx) {
      await fresh(ctx, () => ctx.store.set({ allowCloud: true }));
      await choose("gpt-5-mini");
      ctx.store.set({ allowCloud: false });
      await waitUntil(() => !view.picker.querySelector(".wl-picker-notice").hidden);
    },
  },
  {
    id: "garde-fou-memoire",
    label: "Garde-fou mémoire : tâche gardée, deux issues",
    async run(ctx) {
      await fresh(ctx, () => setMaquette({ ramGuard: true }));
      await ask(ctx, { model: "qwen3.6:7b" });
    },
  },
];
