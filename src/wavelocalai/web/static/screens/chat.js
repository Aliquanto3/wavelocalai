// Chat libre, `#/arene/chat` (UX-DR21, AD-6, AD-9, AD-14, AD-20) : une conversation avec un modèle,
// la réponse affichée au fil de son flux.
//
// - Un seul lecteur du flux d'un run : cet écran (`connectRun`). Il passe chaque enveloppe à
//   `wl-run-status` (mode piloté : étape, chronomètre, Arrêter, Échap) et au fil `wl-chat-thread`.
// - L'écran reste en mémoire quand on va ailleurs (le routeur le masque). Masqué, il ferme son flux
//   en gardant le dernier `seq` ; de retour, il rouvre le flux par `?after=<seq>` : la génération
//   n'a pas été interrompue, rien n'est perdu ni répété.
// - `409 run_busy` : le run actif est rejoint (rejoué depuis le début), sans erreur affichée.
// - `allow_cloud` du store accompagne chaque commande ; le brouillon de saisie vit dans
//   `localStorage` seulement (`core/drafts.js`).
// - À l'ouverture, la dernière conversation de chat est relue au serveur (`GET /api/conversations`)
//   et remontée telle qu'affichée ; son modèle et sa créativité sont ceux de son dernier run (rien
//   n'est gardé dans le navigateur). Un run encore actif est suivi par son flux.
// - « Télécharger » ouvre les exports du serveur (JSON, Markdown) ; « Effacer la conversation »,
//   sans confirmation (UX-DR21), appelle `DELETE` : le texte disparaît de la base, pas le CO2.

import { api, ApiError } from "../core/api.js";
import { element } from "../core/dom.js";
import { loadDraft, saveDraft } from "../core/drafts.js";
import { formatNumber } from "../core/format.js";
import { t } from "../core/i18n.js";
import { isRamGuard, onSmallerModel } from "../core/ram-guard.js";
import { screenTabs } from "../core/screen-tabs.js";
import { connectRun } from "../core/sse.js";
import { store } from "../core/store.js";

const DRAFT = "chat";
const DEFAULT_TEMPERATURE = 0.2;
let counter = 0;

function envelopeOf(error) {
  if (error instanceof ApiError && error.envelope) return error.envelope;
  return { code: "internal", message: t("chat.start_failed") };
}

export function mount(host) {
  const uid = `chat-${++counter}`;

  // --- Structure -------------------------------------------------------------------------
  const picker = document.createElement("wl-model-picker");
  picker.setAttribute("purpose", "chat");

  const slider = element("input", "chat-slider");
  slider.type = "range";
  slider.id = `${uid}-creativity`;
  slider.min = "0";
  slider.max = "2";
  slider.step = "0.1";
  slider.value = String(DEFAULT_TEMPERATURE);
  slider.setAttribute("aria-describedby", `${uid}-creativity-help`);
  const sliderLabel = element("label", "chat-slider-label", t("chat.creativity"));
  sliderLabel.htmlFor = slider.id;
  const sliderValue = element("output", "chat-slider-value", formatNumber(DEFAULT_TEMPERATURE));
  sliderValue.htmlFor = slider.id;
  const sliderHelp = element("p", "help", t("chat.creativity_help"));
  sliderHelp.id = `${uid}-creativity-help`;
  const creativity = element("div", "chat-creativity");
  const sliderRow = element("div", "chat-slider-row");
  sliderRow.append(slider, sliderValue);
  creativity.append(sliderLabel, sliderRow, sliderHelp);

  const settings = element("div", "chat-settings");
  settings.append(picker, creativity);

  const empty = element("p", "help chat-empty", t("chat.empty"));
  const thread = document.createElement("wl-chat-thread");
  const status = document.createElement("wl-run-status");
  status.setAttribute("driven", "");
  const notice = element("p", "chat-notice");
  notice.setAttribute("role", "status");
  notice.hidden = true;
  const error = document.createElement("wl-error");
  error.setAttribute("alert", "");

  const input = element("textarea", "chat-input");
  input.id = `${uid}-message`;
  input.rows = 3;
  input.value = loadDraft(DRAFT);
  input.setAttribute("aria-describedby", `${uid}-keys`);
  const inputLabel = element("label", "chat-input-label", t("chat.message"));
  inputLabel.htmlFor = input.id;
  const keys = element("p", "help", t("chat.keys"));
  keys.id = `${uid}-keys`;
  const send = element("button", "btn chat-send", t("chat.send"));
  send.type = "submit";
  const downloadJson = element("button", "btn", t("chat.download_json"));
  downloadJson.type = "button";
  const downloadMarkdown = element("button", "btn", t("chat.download_markdown"));
  downloadMarkdown.type = "button";
  const clear = element("button", "btn", t("chat.clear"));
  clear.type = "button";
  const actions = element("div", "chat-actions");
  actions.append(send, downloadJson, downloadMarkdown, clear);
  const composer = element("form", "chat-composer");
  composer.append(inputLabel, input, keys, actions);

  host.replaceChildren(
    element("h1", "", t("screens.arena-chat")),
    screenTabs("arena", "arena-chat"),
    element("p", "lead", t("chat.lead")),
    settings,
    empty,
    thread,
    status,
    notice,
    error,
    composer,
  );

  // --- État ------------------------------------------------------------------------------
  let conversationId = null;
  let runId = null; // le run suivi, tant qu'il n'est pas terminé
  let stream = null;
  let answer = null;
  let wasHidden = host.hidden;
  let pending = false; // commande envoyée, réponse du serveur attendue
  let lastMessage = ""; // la dernière question envoyée : rendue au champ si le garde-fou refuse

  const running = () => runId !== null;

  function render() {
    clear.disabled = running() || pending;
    send.disabled = running() || pending;
    downloadJson.disabled = downloadMarkdown.disabled = conversationId === null || pending;
    empty.hidden = !thread.empty;
  }

  function ensureAnswer(tag) {
    if (!answer) answer = thread.beginAnswer({ name: tag ?? "", origin: "unknown" });
    empty.hidden = true;
    return answer;
  }

  function finish(status_, data = {}) {
    ensureAnswer(null).end({ status: status_, ...data });
    runId = null;
    stream = null;
    answer = null;
    render();
  }

  // --- Flux ------------------------------------------------------------------------------
  const forward = (_data, envelope) => status.feed(envelope);
  const handlers = {
    run_started: (data, envelope) => {
      ensureAnswer(Array.isArray(data?.models) ? data.models[0] : null);
      forward(data, envelope);
    },
    model_loading: forward,
    model_loaded: forward,
    token: (data, envelope) => {
      ensureAnswer(data?.lane).token(data?.text, data?.channel);
      forward(data, envelope);
    },
    retry: (data) => ensureAnswer(data?.lane).retry(data?.reason),
    metrics: (data) => ensureAnswer(data?.lane).metrics(data),
    run_ended: (data, envelope) => {
      forward(data, envelope);
      finish(data?.status ?? "error");
      keepQuestion(data);
    },
  };

  // Garde-fou mémoire (`ram_guard`, story 4.8) : la question reste dans l'historique du fil (le
  // serveur l'a gardée) et revient dans le champ, sauf si la personne a déjà tapé autre chose.
  function keepQuestion(data) {
    if (data?.status !== "error" || !isRamGuard(data.error)) return;
    if (lastMessage && !input.value.trim()) {
      input.value = lastMessage;
      saveDraft(DRAFT, lastMessage);
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
    if (!host.hidden) openStream(id); // masqué : le flux s'ouvrira au retour (AD-6)
    render();
  }

  // --- Actions ---------------------------------------------------------------------------
  // --- Conversation rouverte -------------------------------------------------------------
  // Mesures d'une réponse telles que le fil les montre (`metrics` du flux) : rien si le run n'en
  // a pas laissé (arrêté, en erreur).
  function resultOf(run) {
    const m = run?.metrics;
    if (!m || (m.tps === null && m.output_tokens === null)) return null;
    return {
      origin: m.origin,
      tps: m.tps,
      tps_source: m.tps_source,
      eval_tokens: m.output_tokens,
      load_s: m.load_s,
      total_s: m.total_s,
    };
  }

  function showReply(run, message) {
    thread.restoreAnswer({
      name: run?.model ?? "",
      origin: run?.metrics?.origin ?? "unknown",
      text: message?.content ?? "",
      thought: message?.reasoning ?? "",
      result: resultOf(run),
      status: run?.status ?? "ok",
    });
  }

  function showConversation(view) {
    const answered = new Set(
      view.messages.filter((m) => m.role === "assistant" && m.run).map((m) => m.run.run_id),
    );
    for (const message of view.messages) {
      if (message.role === "user") {
        thread.addUserMessage(message.content);
        const run = message.run;
        // Run fini sans réponse écrite (arrêté avant le premier jeton, en erreur) : la réponse
        // vide et son marqueur, comme à l'écran avant l'effacement du navigateur.
        if (run && run.status !== "running" && !answered.has(run.run_id)) showReply(run, null);
      } else if (message.role === "assistant") {
        showReply(message.run, message);
      }
    }
  }

  async function restore() {
    let view;
    try {
      const latest = (await api.conversations("chat", 1)).conversations[0];
      if (!latest) return;
      view = await api.conversation(latest.id);
    } catch {
      return; // pas d'historique lisible : l'écran reste vide, sans erreur
    }
    // Une personne qui a déjà écrit n'est pas dérangée par la conversation d'avant.
    if (conversationId !== null || running() || pending || !thread.empty) return;
    conversationId = view.id;
    showConversation(view);
    if (view.model) picker.value = view.model;
    if (typeof view.temperature === "number") {
      slider.value = String(view.temperature);
      sliderValue.textContent = formatNumber(view.temperature);
    }
    if (view.active_run_id) follow(view.active_run_id);
    render();
  }

  function download(extension) {
    if (conversationId === null) return;
    const link = element("a");
    link.href = api.conversationExportUrl(conversationId, extension);
    link.download = "";
    document.body.append(link);
    link.click();
    link.remove();
  }

  async function submit() {
    if (running() || pending) return;
    const message = input.value;
    if (!message.trim()) {
      input.focus();
      return;
    }
    const model = picker.value;
    notice.hidden = true;
    error.error = null;
    if (!model) {
      error.error = { code: "no_model", message: t("chat.no_model"), action: t("chat.no_model_action") };
      return;
    }
    pending = true; // pas de second envoi (bouton ni Entrée) ni d'effacement pendant la requête
    lastMessage = message;
    render();
    try {
      const started = await api.startChat({
        conversation_id: conversationId,
        model,
        message,
        temperature: Number(slider.value),
        allow_cloud: store.get().allowCloud,
      });
      conversationId = started.conversation_id ?? conversationId;
      thread.addUserMessage(message);
      if (input.value === message) {
        // Un texte tapé pendant la requête reste dans le champ.
        input.value = "";
        saveDraft(DRAFT, "");
      }
      const chosen = picker.selected;
      answer = thread.beginAnswer({ name: chosen?.name ?? model, origin: chosen?.origin });
      follow(started.run_id);
    } catch (failure) {
      const busy = failure instanceof ApiError ? failure.envelope : null;
      if (failure.status === 409 && busy?.code === "run_busy" && busy.detail?.run_id) {
        // Un chat tourne déjà : on le rejoint, sans erreur. Le message reste dans le champ.
        notice.textContent = t("chat.joined");
        notice.hidden = false;
        follow(busy.detail.run_id);
      } else {
        error.error = envelopeOf(failure);
      }
    } finally {
      pending = false;
      render();
    }
  }

  async function clearConversation() {
    if (running() || pending) return;
    error.error = null;
    if (conversationId !== null) {
      pending = true; // ni envoi ni second effacement pendant la requête
      render();
      try {
        await api.deleteConversation(conversationId);
      } catch (failure) {
        // Déjà effacée ailleurs (404) : même résultat. Sinon (409 : une réponse est en cours),
        // le message et l'action du serveur s'affichent et la conversation reste.
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
    status.runId = null;
    conversationId = null;
    answer = null;
    notice.textContent = t("chat.cleared");
    notice.hidden = false;
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
    notice.textContent = t("chat.model_changed", { model: picker.modelFor(tag)?.name ?? tag });
    notice.hidden = false;
    input.focus();
  });
  downloadJson.addEventListener("click", () => download("json"));
  downloadMarkdown.addEventListener("click", () => download("md"));
  slider.addEventListener("input", () => {
    sliderValue.textContent = formatNumber(Number(slider.value));
  });

  // --- Écran masqué puis revu ------------------------------------------------------------
  // Le routeur masque l'écran sans le démonter : on ferme le flux (le serveur continue la
  // génération), et au retour on reprend après le dernier `seq` reçu.
  const visibility = new MutationObserver(() => {
    if (host.hidden === wasHidden) return;
    wasHidden = host.hidden;
    if (wasHidden) {
      thread.suspend();
      stream?.close({ keepSeq: true });
      stream = null;
    } else {
      thread.resume();
      if (running()) openStream(runId);
    }
  });
  visibility.observe(host, { attributes: true, attributeFilter: ["hidden"] });

  render();
  restore();
  return () => {
    visibility.disconnect();
    stream?.close();
    stream = null;
  };
}
