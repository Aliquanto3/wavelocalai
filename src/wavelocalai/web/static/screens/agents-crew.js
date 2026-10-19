// Équipe d'agents, `#/agents/equipe[/<run_id>]` (UX-DR28, AD-3, AD-6, AD-9, AD-20, D-8, D-33 à D-36,
// story 6.6) : une équipe de la bibliothèque, son schéma, la mission suivie agent par agent, puis le
// rapport à télécharger.
//
// - Un seul lecteur du flux d'un run : cet écran (`connectRun`). Il passe chaque enveloppe à
//   `wl-run-status` (mode piloté, `first-stage="thinking"`), au suivi (`agents-crew-track.js`, qui aiguille
//   les étapes par leur champ `agent`) et à la validation d'email (`agents-approval.js`, le même
//   dialogue que l'Agent seul : un agent d'équipe peut demander l'envoi d'un email).
// - Le schéma (`wl-team-graph`) suit les statuts du suivi ; « Configurer » ouvre un volet non modal
//   (`agents-crew-config.js`) qui enregistre la modification de l'équipe (décision Q3).
// - Aucun calcul de métrique (AD-20) : les totaux d'un agent viennent de `agent_totals`, ceux de la
//   mission de `GET /api/runs/{id}` (`totals` et `mission`, pic de mémoire compris), lus à `run_ended`.
// - À la fin d'un run lancé ici, l'adresse est réécrite en `#/agents/equipe/<run_id>`
//   (`history.replaceState`, décision n° 7 du 2026-10-19) : la mission se rouvre par cette adresse, le
//   flux la rejoue depuis la base ; un identifiant inconnu dit « Mission introuvable ».
// - `409 run_busy` : la mission déjà active est rejointe (rejouée depuis le début), sans erreur.
// - Écran masqué : le flux se ferme en gardant le dernier `seq`, la validation en attente est refermée
//   puis rouverte au retour (comme à l'Agent seul).

import { createApproval } from "./agents-approval.js";
import { createConfig } from "./agents-crew-config.js";
import { createTrack } from "./agents-crew-track.js";
import { api, ApiError } from "../core/api.js";
import { element } from "../core/dom.js";
import { loadDraft, saveDraft } from "../core/drafts.js";
import { t } from "../core/i18n.js";
import { screenTabs } from "../core/screen-tabs.js";
import { connectRun } from "../core/sse.js";
import { store } from "../core/store.js";

const DRAFT = "agents-crew";
const BASE = "#/agents/equipe";
let counter = 0;

const envelopeOf = (failure, fallback) =>
  failure instanceof ApiError && failure.envelope ? failure.envelope : { code: "internal", message: t(fallback) };

// « Télécharger en Markdown » : la route d'export du serveur, un lien et non un `blob:`.
function exportLink(conversationId) {
  const link = element("a", "btn agents-download", t("crew.report.download"));
  link.href = api.conversationExportUrl(conversationId, "md");
  link.download = "";
  return link;
}

function missingView() {
  const title = element("h2", "", t("crew.missing.title"));
  title.id = `crew-missing-title-${++counter}`;
  const link = element("a", "btn", t("crew.missing.new"));
  link.href = BASE;
  const view = element("section", "crew-missing");
  view.setAttribute("role", "alert");
  view.setAttribute("aria-labelledby", title.id);
  view.hidden = true;
  view.append(title, element("p", "", t("crew.missing.unknown")), link);
  return view;
}

export function mount(host, params = {}) {
  const uid = `crew-${++counter}`;

  // --- Structure -------------------------------------------------------------------------
  const teamSelect = element("select", "crew-select");
  teamSelect.id = `${uid}-team`;
  const teamLabel = element("label", "crew-label", t("crew.team.label"));
  teamLabel.htmlFor = teamSelect.id;
  const modified = element("span", "crew-modified", t("crew.team.modified"));
  const revert = element("button", "btn", t("crew.team.revert"));
  revert.type = "button";
  const configure = element("button", "btn", t("crew.team.configure"));
  configure.type = "button";
  configure.setAttribute("aria-expanded", "false");
  const teamRow = element("div", "crew-team-row");
  teamRow.append(teamLabel, teamSelect, modified, revert, configure);
  const description = element("p", "help crew-description");
  const teamError = document.createElement("wl-error");
  teamError.setAttribute("alert", "");
  const teamLoading = element("p", "help", t("crew.team.loading"));

  const picker = document.createElement("wl-model-picker");
  picker.setAttribute("purpose", "agent");
  picker.setAttribute("label", t("crew.model.label"));
  const modelHelp = element("p", "help crew-model-help", t("crew.model.help"));
  const unverified = element("p", "agents-warning");
  unverified.setAttribute("role", "status");
  const model = element("div", "agents-model");
  model.append(picker, modelHelp, unverified);

  const input = element("textarea", "chat-input");
  input.id = `${uid}-topic`;
  input.rows = 2;
  input.value = loadDraft(DRAFT);
  input.setAttribute("aria-describedby", `${uid}-keys`);
  const inputLabel = element("label", "chat-input-label", t("crew.topic.label"));
  inputLabel.htmlFor = input.id;
  const keys = element("p", "help", t("crew.topic.keys"));
  keys.id = `${uid}-keys`;
  const launch = element("button", "btn chat-send", t("crew.launch"));
  launch.type = "submit";
  const reason = element("p", "help crew-launch-reason");
  reason.id = `${uid}-reason`;
  const actions = element("div", "chat-actions");
  actions.append(launch, reason);
  const controls = element("form", "crew-controls");
  controls.append(teamRow, description, teamLoading, teamError, model, inputLabel, input, keys, actions);

  const status = document.createElement("wl-run-status");
  status.setAttribute("driven", "");
  status.setAttribute("first-stage", "thinking");
  const notice = element("p", "chat-notice");
  notice.setAttribute("role", "status");
  notice.hidden = true;
  const error = document.createElement("wl-error");
  error.setAttribute("alert", "");
  const dialog = document.createElement("wl-confirm-dialog");
  const missing = missingView();

  const graph = document.createElement("wl-team-graph");
  const graphTitle = element("h2", "crew-section-title", t("crew.team.schema"));
  graphTitle.id = `${uid}-graph`;
  const graphBox = element("section", "crew-graph");
  graphBox.setAttribute("aria-labelledby", graphTitle.id);
  graphBox.append(graphTitle, graph);

  const thread = document.createElement("wl-chat-thread");
  const reportTitle = element("h2", "crew-section-title", t("crew.report.title"));
  reportTitle.id = `${uid}-report`;
  const reportNote = element("p", "help crew-report-note");
  reportNote.hidden = true;
  const report = element("section", "crew-report");
  report.setAttribute("aria-labelledby", reportTitle.id);
  report.hidden = true;
  report.append(reportTitle, thread, reportNote);

  // --- État ------------------------------------------------------------------------------
  let crews = [];
  let maxAgents = 5;
  let toolList = [];
  let modelList = [];
  let selectedId = null;
  let shown = false; // une mission (en cours, finie ou rouverte) est à l'écran
  let conversationId = null;
  let runId = null; // la mission suivie, tant qu'elle n'est pas terminée
  let startedHere = false; // lancée depuis cet écran : l'adresse est réécrite à sa fin
  let stream = null;
  let answer = null;
  let wasHidden = host.hidden;
  let pending = false;

  const labelOf = (id) => toolList.find((tool) => tool.id === id)?.label ?? id;
  const running = () => runId !== null;
  const current = () => crews.find((crew) => crew.id === selectedId) ?? null;
  const say = (text) => {
    notice.textContent = text;
    notice.hidden = false;
  };

  const track = createTrack({ labelOf, onChange: refreshGraph });
  status.toolLabel = labelOf;
  const approvals = createApproval({
    dialog,
    trace: track.noteTrace,
    runId: () => runId,
    say,
    fail: (envelope) => {
      error.error = envelope;
    },
  });
  const config = createConfig({
    tools: () => toolList,
    models: () => modelList,
    maxAgents: () => maxAgents,
    allowCloud: () => store.get().allowCloud,
    say,
    onSaved: (saved) => replaceCrew(saved),
    onClose: ({ restoreFocus }) => {
      configure.setAttribute("aria-expanded", "false");
      if (restoreFocus) configure.focus();
      render();
    },
  });
  config.root.id = `${uid}-config`;
  configure.setAttribute("aria-controls", config.root.id);

  const work = element("div", "crew-work");
  work.append(graphBox, config.root, track.root, report);
  host.replaceChildren(
    element("h1", "", t("screens.agents-crew")),
    screenTabs("agents", "agents-crew"),
    element("p", "lead", t("crew.lead")),
    controls,
    status,
    notice,
    error,
    missing,
    work,
    dialog,
  );

  // --- Rendu -----------------------------------------------------------------------------
  function needsModel() {
    return (current()?.agents ?? []).some((agent) => !agent.model);
  }

  function launchReason() {
    if (running() || pending) return t("crew.reason.busy");
    if (!current()?.agents.length) return t("crew.reason.no_agent");
    if (!input.value.trim()) return t("crew.reason.no_topic");
    if (needsModel() && !picker.value) return t("crew.reason.no_model");
    return "";
  }

  function refreshGraph() {
    const roles = shown ? track.roles() : (current()?.agents ?? []).map((agent) => agent.role);
    graph.set(roles, shown ? track.states() : {});
  }

  function render() {
    const crew = current();
    const locked = running() || pending;
    teamSelect.disabled = locked || !crews.length;
    modified.hidden = !crew?.modified;
    revert.hidden = !crew?.modified;
    revert.disabled = locked;
    configure.disabled = locked || !crew;
    description.textContent = crew?.description ?? "";
    description.hidden = !crew?.description;
    const why = launchReason();
    launch.disabled = Boolean(why);
    reason.textContent = why;
    reason.hidden = !why;
    if (why) launch.setAttribute("aria-describedby", reason.id);
    else launch.removeAttribute("aria-describedby");
    const chosen = picker.selected;
    unverified.textContent = chosen && !chosen.tools_verified ? t("crew.model.unverified") : "";
    unverified.hidden = !unverified.textContent;
    refreshGraph();
  }

  function fillTeams() {
    teamSelect.replaceChildren(...crews.map((crew) => new Option(crew.label, crew.id)));
    teamSelect.value = selectedId ?? "";
    teamLoading.hidden = true;
  }

  // La saisie du sujet est proposée par l'équipe tant que la personne n'a rien écrit de plus.
  function proposeTopic(previous) {
    const proposed = current()?.topic ?? "";
    if (proposed && (!input.value.trim() || input.value === previous?.topic)) {
      input.value = proposed;
      saveDraft(DRAFT, proposed);
    }
  }

  function select(id) {
    const previous = current();
    selectedId = id;
    teamSelect.value = id ?? "";
    config.close({ restoreFocus: false });
    proposeTopic(previous);
    render();
  }

  function replaceCrew(saved) {
    crews = crews.map((crew) => (crew.id === saved.id ? saved : crew));
    render();
  }

  async function loadCrews() {
    try {
      const listing = await api.agentCrews();
      crews = listing.crews;
      maxAgents = listing.max_agents ?? maxAgents;
      selectedId = crews.some((c) => c.id === selectedId) ? selectedId : (crews[0]?.id ?? null);
      fillTeams();
      proposeTopic(null);
    } catch (failure) {
      teamLoading.hidden = true;
      teamError.error = {
        ...envelopeOf(failure, "crew.team.failed"),
        action: t("crew.team.failed_action"),
      };
    }
    render();
  }

  async function loadLists() {
    // Outils et modèles : les interrupteurs et la liste du volet « Configurer » (une lecture chacun).
    const [tools, models] = await Promise.allSettled([api.agentTools(), api.models(store.get().allowCloud)]);
    toolList = tools.status === "fulfilled" ? tools.value.tools : [];
    modelList =
      models.status === "fulfilled" ? models.value.models.filter((m) => m.kind === "chat") : [];
    config.refresh();
    track.root.querySelectorAll("wl-step-trace").forEach((trace) => (trace.labelOf = labelOf));
  }

  // --- Mission ---------------------------------------------------------------------------
  function ensureAnswer(tag) {
    if (!answer) {
      const known = picker.modelFor(tag);
      answer = thread.beginAnswer({
        name: known?.name ?? tag ?? t("crew.report.title"),
        origin: known?.origin ?? "unknown",
        reduced: true,
      });
    }
    return answer;
  }

  function startOver(roles, { rewrite }) {
    track.reset();
    track.setAgents(roles);
    approvals.reset();
    thread.clear();
    answer = null;
    shown = true;
    report.hidden = false;
    reportTitle.textContent = t("crew.report.title");
    reportNote.hidden = true;
    notice.hidden = true;
    missing.hidden = true;
    work.hidden = false;
    if (rewrite && location.hash.startsWith(`${BASE}/`)) history.replaceState(null, "", BASE);
    render();
  }

  function follow(id, { here }) {
    runId = id;
    startedHere = here;
    status.runId = id;
    if (!host.hidden) openStream(id); // masqué : le flux s'ouvrira au retour (AD-6)
    render();
  }

  // Le texte de la mission et, faute de `token` rejoués, le rapport gardé dans la conversation.
  async function restoreConversation({ topic, report: wantReport }) {
    try {
      const { messages = [] } = await api.conversation(conversationId);
      const first = messages.find((message) => message.role === "user");
      if (topic && first) thread.addUserMessage(first.content);
      const last = messages.filter((message) => message.role === "assistant").at(-1);
      if (wantReport && last?.content && !answer) {
        answer = ensureAnswer(null);
        answer.token(last.content, "answer");
        return answer;
      }
    } catch {
      // Sans la conversation, l'écran garde le suivi : rien n'est inventé.
    }
    return null;
  }

  async function finish(endStatus) {
    const ended = runId;
    runId = null;
    stream = null;
    approvals.reset();
    render();
    // Sans `token` rejoués (mission rouverte), le rapport est celui gardé dans la conversation.
    const reply = answer ?? (conversationId ? await restoreConversation({ topic: false, report: true }) : null);
    answer = null;
    reply?.end({ status: endStatus });
    if (reply && endStatus !== "ok") reportTitle.textContent = t("crew.report.title_partial");
    if (!reply && endStatus !== "ok") {
      reportNote.textContent = t(endStatus === "cancelled" ? "crew.report.none_cancelled" : "crew.report.none_error");
      reportNote.hidden = false;
    }
    if (startedHere && !host.hidden && location.hash === BASE) {
      history.replaceState(null, "", `${BASE}/${encodeURIComponent(ended)}`);
    }
    if (!reply) return;
    if (conversationId) reply.actions.append(exportLink(conversationId));
    try {
      const snapshot = await api.run(ended);
      // Totaux additionnés par le serveur ; le pic de mémoire est celui du poste (`mission`).
      reply.summarize({ ...snapshot.totals, peak_memory_gb: snapshot.mission?.peak_memory_gb ?? null });
    } catch {
      // Sans totaux le pied reste vide : rien d'inventé.
    }
  }

  // --- Flux ------------------------------------------------------------------------------
  const forward = (_data, envelope) => status.feed(envelope);
  const tracked = (type) => (data, envelope) => {
    track.feed(type, data, envelope);
    forward(data, envelope);
  };
  const handlers = {
    run_started: tracked("run_started"),
    model_loading: forward,
    model_loaded: forward,
    step: (data, envelope) => {
      tracked("step")(data, envelope);
      if (data?.kind === "tool_result") approvals.toolResult(data);
    },
    approval_required: (data, envelope) => {
      tracked("approval_required")(data, envelope);
      approvals.required(data);
    },
    approval_resolved: (data, envelope) => {
      tracked("approval_resolved")(data, envelope);
      approvals.resolved(data);
    },
    token: (data, envelope) => {
      ensureAnswer(data?.lane).token(data?.text, data?.channel);
      forward(data, envelope);
    },
    run_ended: (data, envelope) => {
      track.feed("run_ended", data, envelope);
      forward(data, envelope);
      finish(data?.status ?? "error");
    },
  };

  function openStream(id) {
    stream?.close({ keepSeq: true });
    stream = connectRun(id, handlers, ({ status: state }) => {
      // Run inconnu ou serveur muet après plusieurs essais, sans `run_ended` : on le dit.
      if (state === "failed" && running()) {
        status.abandon();
        track.feed("run_ended", { status: "interrupted" }, null);
        finish("interrupted");
      }
    });
  }

  // --- Lancer et rouvrir -----------------------------------------------------------------
  async function submit() {
    const crew = current();
    if (running() || pending || !crew) return;
    if (launchReason()) {
      (input.value.trim() ? picker : input).focus?.();
      return;
    }
    notice.hidden = true;
    error.error = null;
    const topic = input.value.trim();
    pending = true;
    render();
    try {
      const started = await api.startAgent({
        mode: "crew",
        crew: crew.id,
        topic,
        ...(picker.value ? { model: picker.value } : {}),
        allow_cloud: store.get().allowCloud,
      });
      conversationId = started.conversation_id ?? null;
      startOver(
        crew.agents.map((agent) => agent.role),
        { rewrite: true },
      );
      thread.addUserMessage(topic);
      follow(started.run_id, { here: true });
    } catch (failure) {
      const busy = failure instanceof ApiError ? failure.envelope : null;
      if (failure.status === 409 && busy?.code === "run_busy" && busy.detail?.run_id) {
        await join(await api.run(busy.detail.run_id), { busy: true });
      } else {
        error.error = envelopeOf(failure, "crew.start_failed");
      }
    } finally {
      pending = false;
      render();
    }
  }

  // Rejoindre ou rouvrir une mission : le flux la rejoue depuis la base ; la conversation redonne le
  // sujet (et le rapport si le flux ne le rejoue pas).
  async function join(snapshot, { busy = false } = {}) {
    conversationId = snapshot.conversation_id ?? null;
    const roles = (snapshot.params?.agents ?? []).map((agent) => agent.role);
    if (crews.some((crew) => crew.id === snapshot.params?.crew)) {
      selectedId = snapshot.params.crew;
      teamSelect.value = selectedId;
    }
    startOver(roles, { rewrite: false });
    if (conversationId) await restoreConversation({ topic: true, report: false });
    if (busy) say(t("crew.joined"));
    follow(snapshot.run_id, { here: false });
  }

  async function reopen(id) {
    try {
      const snapshot = await api.run(id);
      if (snapshot.kind !== "agent" || snapshot.params?.mode !== "crew") throw new Error("not a mission");
      await join(snapshot);
    } catch {
      work.hidden = true;
      missing.hidden = false;
    }
  }

  // --- Événements ------------------------------------------------------------------------
  teamSelect.addEventListener("change", () => select(teamSelect.value));
  configure.addEventListener("click", () => {
    if (config.isOpen) config.close();
    else if (current()) {
      configure.setAttribute("aria-expanded", "true");
      config.open(current());
    }
  });
  revert.addEventListener("click", async () => {
    const crew = current();
    if (!crew || running() || pending) return;
    try {
      replaceCrew(await api.resetCrew(crew.id));
      config.close({ restoreFocus: false });
      configure.focus(); // le bouton « Revenir » vient de disparaître
      say(t("crew.team.reverted"));
    } catch (failure) {
      error.error = envelopeOf(failure, "crew.team.revert_failed");
    }
  });
  controls.addEventListener("submit", (event) => {
    event.preventDefault();
    submit();
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      submit();
    }
  });
  input.addEventListener("input", () => {
    saveDraft(DRAFT, input.value);
    render();
  });
  picker.addEventListener("wl-model-change", render);
  picker.addEventListener("wl-models-loaded", render);

  // --- Écran masqué puis revu ------------------------------------------------------------
  const visibility = new MutationObserver(() => {
    if (host.hidden === wasHidden) return;
    wasHidden = host.hidden;
    if (wasHidden) {
      thread.suspend();
      approvals.suspend();
      stream?.close({ keepSeq: true });
      stream = null;
    } else {
      thread.resume();
      if (running()) openStream(runId);
      approvals.resume();
    }
  });
  visibility.observe(host, { attributes: true, attributeFilter: ["hidden"] });

  render();
  loadCrews().then(() => (params.run_id ? reopen(params.run_id) : null));
  loadLists();
  return () => {
    visibility.disconnect();
    stream?.close();
    stream = null;
    approvals.reset();
  };
}
