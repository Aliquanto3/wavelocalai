// Agent seul, `#/agents/seul` (UX-DR28, AD-6, AD-9, AD-20, story 6.4) : une tâche confiée à un agent
// qui appelle des outils, chaque étape visible dans le panneau « Étapes », l'email validé par la
// personne dans un dialogue, la réponse finale dans le fil.
//
// - Un seul lecteur du flux d'un run : cet écran (`connectRun`). Il passe chaque enveloppe à
//   `wl-run-status` (mode piloté, `first-stage="thinking"`), à la trace et au fil.
// - La réponse finale arrive **en un bloc** à la fin du dernier tour (variante conservatrice de la
//   6.1) : une ligne d'aide le dit, et `wl-run-status` dit « Réflexion… » pendant l'attente.
// - Le pied de la réponse est réduit (D-31) : CO2, étapes et durée de la tâche entière viennent de
//   `GET /api/runs/{id}` (`totals`, additionnés par le serveur, AD-20), lu à `run_ended`.
// - L'écran reste en mémoire quand on va ailleurs (le routeur le masque) : masqué, il ferme son flux
//   en gardant le dernier `seq` et reprend par `?after=<seq>` au retour ; la validation d'un email
//   en attente est refermée puis rouverte (`agents-approval.js`).
// - `409 run_busy` : la tâche déjà active est rejointe (rejouée depuis le début), sans erreur.
// - Garde-fou mémoire (`ram_guard`, 4.8) : la tâche revient dans le champ, comme au Chat libre.

import { createApproval } from "./agents-approval.js";
import { createTools } from "./agents-tools.js";
import { api, ApiError } from "../core/api.js";
import { element } from "../core/dom.js";
import { loadDraft, saveDraft } from "../core/drafts.js";
import { t } from "../core/i18n.js";
import { isRamGuard, onSmallerModel } from "../core/ram-guard.js";
import { screenTabs } from "../core/screen-tabs.js";
import { connectRun } from "../core/sse.js";
import { store } from "../core/store.js";

const DRAFT = "agents-solo";
let counter = 0;

function envelopeOf(error) {
  if (error instanceof ApiError && error.envelope) return error.envelope;
  return { code: "internal", message: t("agents.start_failed") };
}

// « Télécharger » : la route d'export du serveur (Markdown), un lien et non un `blob:`.
function exportLink(conversationId) {
  const link = element("a", "btn agents-download", t("agents.download"));
  link.href = api.conversationExportUrl(conversationId, "md");
  link.download = "";
  return link;
}

// L'accueil de l'agent : « Bonjour ! », une phrase, les actions rapides de la v1 (elles remplissent
// la saisie sans l'envoyer).
function welcomeCard(onPick) {
  const card = element("div", "agents-welcome card");
  card.append(
    element("h2", "agents-welcome-title", t("agents.welcome.title")),
    element("p", "agents-welcome-text", t("agents.welcome.text")),
  );
  const row = element("div", "agents-quick");
  const quick = (name) => {
    const box = element("div", "agents-quick-card");
    const button = element("button", "btn", t(`agents.welcome.${name}_button`));
    button.type = "button";
    button.addEventListener("click", () => onPick(t(`agents.welcome.${name}_prompt`)));
    box.append(element("p", "agents-quick-title", t(`agents.welcome.${name}_title`)), button);
    return box;
  };
  const sobriety = element("div", "agents-quick-card");
  sobriety.append(
    element("p", "agents-quick-title", t("agents.welcome.sobriety_title")),
    element("p", "help", t("agents.welcome.sobriety_text")),
  );
  row.append(quick("audit"), quick("data"), sobriety);
  card.append(row);
  return card;
}

export function mount(host) {
  const uid = `agents-${++counter}`;

  // --- Structure -------------------------------------------------------------------------
  const picker = document.createElement("wl-model-picker");
  picker.setAttribute("purpose", "agent");
  const modelHint = element("p", "help agents-model-hint", t("agents.settings.model_required"));
  modelHint.hidden = true;
  const unverified = element("p", "agents-warning");
  unverified.setAttribute("role", "status");
  const model = element("div", "agents-model");
  model.append(picker, modelHint, unverified);
  const tools = createTools(uid);
  const settings = element("div", "agents-settings");
  settings.append(model, tools.root);

  const input = element("textarea", "chat-input");
  input.id = `${uid}-task`;
  input.rows = 3;
  input.value = loadDraft(DRAFT);
  input.setAttribute("aria-describedby", `${uid}-keys`);
  const inputLabel = element("label", "chat-input-label", t("agents.task"));
  inputLabel.htmlFor = input.id;
  const keys = element("p", "help", t("agents.keys"));
  keys.id = `${uid}-keys`;
  const send = element("button", "btn chat-send", t("agents.send"));
  send.type = "submit";
  const clear = element("button", "btn", t("agents.clear"));
  clear.type = "button";
  const actions = element("div", "chat-actions");
  actions.append(send, clear);
  const composer = element("form", "chat-composer");
  composer.append(inputLabel, input, keys, actions);

  const thread = document.createElement("wl-chat-thread");
  const welcome = welcomeCard((prompt) => {
    input.value = prompt;
    saveDraft(DRAFT, prompt);
    input.focus();
  });
  const blockNotice = element("p", "help agents-block-notice", t("agents.block_notice"));
  const status = document.createElement("wl-run-status");
  status.setAttribute("driven", "");
  status.setAttribute("first-stage", "thinking");
  status.toolLabel = tools.labelOf;
  const notice = element("p", "chat-notice");
  notice.setAttribute("role", "status");
  notice.hidden = true;
  const error = document.createElement("wl-error");
  error.setAttribute("alert", "");
  const dialog = document.createElement("wl-confirm-dialog");

  const main = element("div", "agents-main");
  main.append(welcome, thread, blockNotice, status, notice, error, composer);

  const trace = document.createElement("wl-step-trace");
  trace.labelOf = tools.labelOf;
  const stepsTitle = element("h2", "agents-steps-title", t("agents.steps.title"));
  stepsTitle.id = `${uid}-steps`;
  const stepsEmpty = element("p", "help", t("agents.steps.empty"));
  const steps = element("aside", "agents-steps");
  steps.setAttribute("aria-labelledby", stepsTitle.id);
  steps.append(stepsTitle, stepsEmpty, trace);

  const work = element("div", "agents-work");
  work.append(main, steps);
  host.replaceChildren(
    element("h1", "", t("screens.agents-solo")),
    screenTabs("agents", "agents-solo"),
    element("p", "lead", t("agents.lead")),
    settings,
    work,
    dialog,
  );

  // --- État ------------------------------------------------------------------------------
  let conversationId = null;
  let runId = null; // la tâche suivie, tant qu'elle n'est pas terminée
  let stream = null;
  let answer = null;
  let wasHidden = host.hidden;
  let pending = false; // commande envoyée, réponse du serveur attendue
  let lastTask = ""; // la dernière tâche envoyée : rendue au champ si le garde-fou refuse

  const running = () => runId !== null;
  const say = (text) => {
    notice.textContent = text;
    notice.hidden = false;
  };
  const approvals = createApproval({
    dialog,
    trace,
    runId: () => runId,
    say,
    fail: (envelope) => {
      error.error = envelope;
    },
  });

  function render() {
    const chosen = picker.selected;
    clear.disabled = running() || pending;
    send.disabled = running() || pending || !picker.value;
    welcome.hidden = !thread.empty || running();
    stepsEmpty.hidden = trace.count > 0;
    modelHint.hidden = !picker.loaded || Boolean(picker.value);
    // Un modèle sans outils vérifiés reste permis (D-32) : l'avertissement le dit.
    unverified.textContent =
      chosen && !chosen.tools_verified ? t("agents.settings.tools_unverified") : "";
    unverified.hidden = !unverified.textContent;
  }

  function ensureAnswer(tag) {
    if (!answer) {
      const chosen = picker.selected;
      answer = thread.beginAnswer({
        name: chosen?.name ?? tag ?? "",
        origin: chosen?.origin ?? "unknown",
        reduced: true,
      });
    }
    return answer;
  }

  // La tâche est finie : sa réponse est close, son pied dit la tâche entière (totaux du serveur) et
  // « Télécharger » suit comme une action (route d'export du serveur, sans `blob:`).
  async function finish(status_) {
    const ended = runId;
    const reply = answer || status_ !== "ok" ? ensureAnswer(null) : null;
    reply?.end({ status: status_ });
    runId = null;
    stream = null;
    answer = null;
    trace.setCurrent(null);
    approvals.reset();
    render();
    if (!reply) return;
    if (conversationId) reply.actions.append(exportLink(conversationId));
    try {
      reply.summarize((await api.run(ended)).totals);
    } catch {
      // Sans totaux le pied reste vide : rien d'inventé.
    }
  }

  // --- Flux ------------------------------------------------------------------------------
  const forward = (_data, envelope) => status.feed(envelope);
  const handlers = {
    run_started: (data, envelope) => {
      trace.maxTurns = data?.params?.max_turns ?? null;
      forward(data, envelope);
    },
    model_loading: forward,
    model_loaded: forward,
    step: (data, envelope) => {
      trace.add(data);
      render();
      forward(data, envelope);
      if (data?.kind === "tool_result") approvals.toolResult(data);
    },
    approval_required: (data, envelope) => {
      trace.setCurrent("approval");
      forward(data, envelope);
      approvals.required(data);
    },
    approval_resolved: (data, envelope) => {
      trace.setCurrent("running");
      forward(data, envelope);
      approvals.resolved(data);
    },
    token: (data, envelope) => {
      ensureAnswer(data?.lane).token(data?.text, data?.channel);
      forward(data, envelope);
    },
    run_ended: (data, envelope) => {
      forward(data, envelope);
      finish(data?.status ?? "error");
      keepTask(data);
    },
  };

  // Garde-fou mémoire : la tâche reste dans l'historique du fil et revient dans le champ, sauf si la
  // personne a déjà tapé autre chose.
  function keepTask(data) {
    if (data?.status !== "error" || !isRamGuard(data.error)) return;
    if (lastTask && !input.value.trim()) {
      input.value = lastTask;
      saveDraft(DRAFT, lastTask);
    }
  }

  function openStream(id) {
    stream?.close({ keepSeq: true });
    stream = connectRun(id, handlers, ({ status: state }) => {
      // Run inconnu ou serveur muet après plusieurs essais, sans `run_ended` : on le dit.
      if (state === "failed" && running()) {
        status.abandon();
        finish("interrupted");
      }
    });
  }

  function follow(id) {
    runId = id;
    status.runId = id;
    trace.setCurrent("running");
    if (!host.hidden) openStream(id); // masqué : le flux s'ouvrira au retour (AD-6)
    render();
  }

  // --- Actions ---------------------------------------------------------------------------
  function startOver() {
    trace.clear();
    approvals.reset();
    answer = null;
    notice.hidden = true;
  }

  async function submit() {
    if (running() || pending) return;
    const task = input.value;
    if (!task.trim()) {
      input.focus();
      return;
    }
    const chosen = picker.value;
    notice.hidden = true;
    error.error = null;
    if (!chosen) {
      error.error = {
        code: "no_model",
        message: t("agents.no_model"),
        action: t("agents.no_model_action"),
      };
      return;
    }
    pending = true; // pas de second envoi ni d'effacement pendant la requête
    lastTask = task;
    render();
    try {
      const started = await api.startAgent({
        mode: "solo",
        model: chosen,
        prompt: task,
        tools: tools.selected(),
        conversation_id: conversationId,
        allow_cloud: store.get().allowCloud,
      });
      conversationId = started.conversation_id ?? conversationId;
      startOver();
      thread.addUserMessage(task);
      if (input.value === task) {
        input.value = "";
        saveDraft(DRAFT, "");
      }
      follow(started.run_id);
    } catch (failure) {
      const busy = failure instanceof ApiError ? failure.envelope : null;
      if (failure.status === 409 && busy?.code === "run_busy" && busy.detail?.run_id) {
        // Une tâche tourne déjà : on la rejoint, sans erreur. Le texte reste dans le champ.
        startOver();
        say(t("agents.joined"));
        join(busy.detail.run_id);
      } else {
        error.error = envelopeOf(failure);
      }
    } finally {
      pending = false;
      render();
    }
  }

  // La conversation de la tâche rejointe, pour « Télécharger » (lue une fois, sans bloquer le flux).
  function join(id) {
    follow(id);
    api
      .run(id)
      .then((snapshot) => {
        conversationId ??= snapshot.conversation_id ?? null;
      })
      .catch(() => {});
  }

  async function clearConversation() {
    if (running() || pending) return;
    error.error = null;
    if (conversationId !== null) {
      pending = true;
      render();
      try {
        await api.deleteConversation(conversationId);
      } catch (failure) {
        // Déjà effacée ailleurs (404) : même résultat. Sinon le message du serveur s'affiche.
        if (!(failure instanceof ApiError && failure.status === 404)) {
          error.error = envelopeOf(failure);
          pending = false;
          render();
          return;
        }
      }
      pending = false;
    }
    thread.clear();
    startOver();
    status.runId = null;
    conversationId = null;
    say(t("agents.cleared"));
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
  input.addEventListener("input", () => saveDraft(DRAFT, input.value));
  clear.addEventListener("click", clearConversation);
  // Garde-fou mémoire : le modèle proposé par le serveur est choisi, sans relancer.
  onSmallerModel(host, (tag) => {
    picker.value = tag;
    render(); // l'affectation n'émet pas `wl-model-change`
    say(t("agents.model_changed", { model: picker.modelFor(tag)?.name ?? tag }));
    input.focus();
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
  tools.load();
  return () => {
    visibility.disconnect();
    stream?.close();
    stream = null;
    approvals.reset();
  };
}
