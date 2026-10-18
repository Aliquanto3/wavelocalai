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

import { api, ApiError } from "../core/api.js";
import { element } from "../core/dom.js";
import { loadDraft, saveDraft } from "../core/drafts.js";
import { formatNumber } from "../core/format.js";
import { t } from "../core/i18n.js";
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
  const clear = element("button", "btn", t("chat.clear"));
  clear.type = "button";
  const actions = element("div", "chat-actions");
  actions.append(send, clear);
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

  const running = () => runId !== null;

  function render() {
    clear.disabled = running();
    send.disabled = running();
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
    },
  };

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
    openStream(id);
    render();
  }

  // --- Actions ---------------------------------------------------------------------------
  async function submit() {
    if (running()) return;
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
    send.disabled = true; // pas de second envoi pendant la requête
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
      input.value = "";
      saveDraft(DRAFT, "");
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
        render();
      }
    }
  }

  function clearConversation() {
    if (running()) return;
    thread.clear();
    status.runId = null;
    conversationId = null;
    answer = null;
    notice.hidden = true;
    error.error = null;
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
  return () => {
    visibility.disconnect();
    stream?.close();
    stream = null;
  };
}
