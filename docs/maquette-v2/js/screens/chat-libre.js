// Chat libre, `#/arene/chat` (UX-DR10, UX-DR21, stories 2.2 à 2.6) : écran MODÈLE de la maquette,
// à l'état livré. Repris de la branche feat/v2-ecran-chat (screens/chat.js), branché sur le
// simulateur (js/sim/sim.js) au lieu de l'API.
//
// - Sélecteur de modèle (défaut `chat` et sa raison), « Créativité », fil `wl-chat-thread`, étape et
//   Arrêter (`wl-run-status` piloté), saisie avec Entrée / Maj+Entrée / Échap.
// - Pied de réponse : provisoire pendant le flux, puis CO₂, débit (D3), chargement, durée totale.
// - Masqué (on change d'écran), l'écran détache son flux ; au retour il reprend après le dernier
//   `seq` reçu : la génération n'a pas été interrompue, rien n'est perdu ni doublé (AD-6).
// - Commande refusée avant le run (comme un 4xx) : `run_busy` rejoint le run actif sans erreur ;
//   `ram_guard`, `ollama_down`, `cloud_not_allowed`, `cloud_key_missing` affichent l'erreur et
//   gardent la question dans le champ.
// - « Effacer la conversation » sans confirmation ; « Télécharger » en JSON ou Markdown (Blob local).

import { element } from "../core/dom.js";
import { formatNumber } from "../core/format.js";
import { t } from "../core/i18n.js";
import { setMaquette, store } from "../core/store.js";
import { findModel, modelDefaults } from "../sim/modeles.js";
import { sim } from "../sim/sim.js";
import { errorEnvelope } from "../core/errors.js";
import { setOllamaDown } from "../sim/systeme.js";

const DEFAULT_TEMPERATURE = 0.7;
let counter = 0;
let view = null; // l'instance montée, pour les scénarios

export async function mount(host, ctx) {
  const uid = `chat-${++counter}`;
  const data = await ctx.data("chat-libre.json");

  // --- Structure -------------------------------------------------------------------------
  const guard = ctx.states.ollamaGuard();
  const picker = document.createElement("wl-model-picker");
  picker.setAttribute("purpose", "chat");

  const slider = element("input", "chat-slider");
  slider.type = "range";
  slider.id = `${uid}-creativity`;
  Object.assign(slider, { min: "0", max: "2", step: "0.1", value: String(DEFAULT_TEMPERATURE) });
  slider.setAttribute("aria-describedby", `${uid}-creativity-help`);
  const sliderLabel = element("label", "chat-slider-label", t("chat.creativity"));
  sliderLabel.htmlFor = slider.id;
  const sliderValue = element("output", "chat-slider-value", formatNumber(DEFAULT_TEMPERATURE));
  sliderValue.htmlFor = slider.id;
  const sliderHelp = element("p", "help", t("chat.creativity_help"));
  sliderHelp.id = `${uid}-creativity-help`;
  const sliderRow = element("div", "chat-slider-row");
  sliderRow.append(slider, sliderValue);
  const creativity = element("div", "chat-creativity");
  creativity.append(sliderLabel, sliderRow, sliderHelp);
  const settings = element("div", "chat-settings");
  settings.append(picker, creativity);

  const empty = element("p", "help chat-empty", t("chat.empty"));
  const thread = document.createElement("wl-chat-thread");
  const status = document.createElement("wl-run-status");
  status.setAttribute("driven", "");
  const firstLoad = element("p", "help chat-first-load", t("chat.first_load"));
  firstLoad.hidden = true;
  const notices = element("div", "chat-notices");
  const error = document.createElement("wl-error");
  error.setAttribute("alert", "");

  const input = element("textarea", "chat-input");
  input.id = `${uid}-message`;
  input.rows = 3;
  input.setAttribute("aria-describedby", `${uid}-keys`);
  const inputLabel = element("label", "chat-input-label", t("chat.message"));
  inputLabel.htmlFor = input.id;
  const keys = element("p", "help", t("chat.keys"));
  keys.id = `${uid}-keys`;
  const send = element("button", "btn btn-primary chat-send", t("chat.send"));
  send.type = "submit";
  const clear = element("button", "btn", t("chat.clear"));
  clear.type = "button";
  const downloadJson = element("button", "btn", t("chat.download_json"));
  downloadJson.type = "button";
  const downloadMd = element("button", "btn", t("chat.download_md"));
  downloadMd.type = "button";
  const actions = element("div", "chat-actions");
  actions.append(send, clear, downloadJson, downloadMd);
  const busyReason = element("p", "help", t("chat.busy_reason"));
  busyReason.hidden = true;
  const composer = element("form", "chat-composer");
  composer.append(inputLabel, input, keys, actions, busyReason);

  host.replaceChildren(
    element("h1", "", ctx.route.title),
    ctx.tabs(),
    element("p", "lead", t("chat.lead")),
    guard,
    settings,
    empty,
    thread,
    status,
    firstLoad,
    notices,
    error,
    composer,
  );

  // --- État ------------------------------------------------------------------------------
  let run = null; // le run suivi tant qu'il n'est pas terminé
  let attachment = null;
  let lastSeq = 0;
  let answer = null;
  let current = null; // { tag, name, origin, text, thought } de la réponse en cours
  let lastMessage = "";
  const transcript = [];
  const loaded = new Set(); // modèles déjà chargés en mémoire pendant cette visite
  let wasHidden = host.hidden;

  const running = () => run !== null;

  function render() {
    const busy = running();
    send.disabled = busy;
    clear.disabled = busy;
    downloadJson.disabled = busy;
    downloadMd.disabled = busy;
    busyReason.hidden = !busy;
    const hasContent = !thread.empty;
    clear.hidden = !hasContent;
    downloadJson.hidden = !hasContent;
    downloadMd.hidden = !hasContent;
    busyReason.hidden = !busy || !hasContent;
    empty.hidden = hasContent;
  }

  function say(text, tone = "info") {
    notices.replaceChildren(ctx.states.notice(text, { tone }));
  }

  function ensureAnswer(tag) {
    if (!answer) {
      const name = current?.name ?? tag ?? "";
      answer = thread.beginAnswer({ name, origin: current?.origin ?? "unknown" });
      current ??= { tag, name, origin: "unknown", text: "", thought: "" };
    }
    return answer;
  }

  function finish(finalStatus, data = {}) {
    ensureAnswer(null).end({ status: finalStatus });
    firstLoad.hidden = true;
    if (data.error) error.error = data.error;
    transcript.push({ role: "assistant", ...current, status: finalStatus, metrics: current.metrics ?? null });
    attachment?.close();
    run = null;
    attachment = null;
    answer = null;
    current = null;
    render();
  }

  // --- Flux ------------------------------------------------------------------------------
  const forward = (_data, envelope) => status.feed(envelope);
  const handlers = {
    "*": (_data, envelope) => {
      lastSeq = envelope.seq;
    },
    run_started: (data, envelope) => {
      ensureAnswer(Array.isArray(data?.models) ? data.models[0] : null);
      forward(data, envelope);
    },
    model_loading: (data, envelope) => {
      firstLoad.hidden = false;
      forward(data, envelope);
    },
    model_loaded: (data, envelope) => {
      firstLoad.hidden = true;
      loaded.add(data.tag);
      forward(data, envelope);
    },
    token: (data, envelope) => {
      ensureAnswer(data?.lane).token(data?.text, data?.channel);
      if (data?.channel === "thought") current.thought += data.text;
      else current.text += data.text;
      forward(data, envelope);
    },
    retry: (data) => {
      ensureAnswer(data?.lane).retry(data?.reason);
      current.text = "";
      current.thought = "";
    },
    metrics: (data) => {
      ensureAnswer(data?.lane).metrics(data);
      current.metrics = data;
    },
    run_ended: (data, envelope) => {
      forward(data, envelope);
      finish(data?.status ?? "error", data ?? {});
    },
  };

  function follow(simRun, { after = 0 } = {}) {
    run = simRun;
    lastSeq = after;
    status.runId = simRun.id;
    attachment = simRun.attach(handlers, { after });
    render();
  }

  // --- Actions ---------------------------------------------------------------------------
  async function varsFor(model, { answerKey = "default", error: code = null } = {}) {
    const text = data.answers[answerKey];
    const metrics = { lane: model.tag, ...(data.metrics[model.tag] ?? data.metrics.default_local) };
    return {
      tag: model.tag,
      temperature: Number(slider.value),
      loading: model.origin === "local" && !loaded.has(model.tag),
      load_s: metrics.load_s,
      thought: model.reasoning ? text.thought : "",
      answer: text.text,
      partial: text.partial,
      tps: metrics.tps,
      metrics,
      error: code ? errorEnvelope(code, { detail: model.provider_name ? { provider: model.provider, provider_name: model.provider_name } : {} }) : null,
    };
  }

  // `options.script` et `options.answer` : choisis par un scénario (erreur, réponse longue…).
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
      error.error = { code: "no_model", message: t("chat.no_model"), action: t("chat.no_model_action") };
      return null;
    }
    // Ce que `POST /api/chat/runs` refuserait avant de créer le run.
    const refused = sim.precheck({ origin: model.origin, kind: "chat", model });
    if (refused?.code === "run_busy") {
      const other = sim.get(refused.detail.run_id);
      const joined = (await findModel(other.options.vars?.tag)) ?? model;
      current = { tag: joined.tag, name: joined.name, origin: joined.origin, text: "", thought: "" };
      say(t("chat.joined"));
      follow(other);
      return run;
    }
    if (refused) {
      error.error = refused; // la question reste dans le champ (garde-fou mémoire compris)
      return null;
    }
    lastMessage = message;
    thread.addUserMessage(message);
    transcript.push({ role: "user", text: message });
    input.value = "";
    current = { tag: model.tag, name: model.name, origin: model.origin, text: "", thought: "" };
    answer = thread.beginAnswer({ name: model.name, origin: model.origin });
    const vars = await varsFor(model, { answerKey: options.answer, error: options.error });
    const simRun = sim.play(options.script ?? "chat-libre-reponse", null, {
      vars,
      kind: "chat",
      origin: model.origin,
      module: "chat",
    });
    follow(simRun);
    return simRun;
  }

  function clearConversation() {
    if (running()) return;
    thread.clear();
    transcript.length = 0;
    status.runId = null;
    error.error = null;
    say(t("chat.cleared"), "success");
    render();
    input.focus();
  }

  function download(kind) {
    const lines = transcript.map((message) =>
      message.role === "user" ? `**Vous** : ${message.text}` : `**${message.name}** (${message.origin}) : ${message.text}`,
    );
    const content =
      kind === "json"
        ? JSON.stringify({ model_choice: picker.value, messages: transcript }, null, 2)
        : `# Conversation WaveLocalAI\n\n${lines.join("\n\n")}\n`;
    const blob = new Blob([content], { type: kind === "json" ? "application/json" : "text/markdown" });
    const link = element("a");
    link.href = URL.createObjectURL(blob);
    link.download = `conversation.${kind === "json" ? "json" : "md"}`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
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
  clear.addEventListener("click", clearConversation);
  downloadJson.addEventListener("click", () => download("json"));
  downloadMd.addEventListener("click", () => download("md"));
  slider.addEventListener("input", () => {
    sliderValue.textContent = formatNumber(Number(slider.value));
  });

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
      const defaults = await modelDefaults("chat", false).catch(() => ({ tags: [] }));
      if (defaults.tags[0]) picker.value = defaults.tags[0];
      error.error = null;
    } else if (id === "smaller") {
      const suggested = error.error?.detail?.suggested_model;
      const model = suggested ? await findModel(suggested) : null;
      if (model) picker.value = model.tag;
      setMaquette({ ramGuard: false });
      error.error = null;
      say(t("chat.smaller", { name: model?.name ?? suggested ?? "" }), "success");
    } else if (id === "unload") {
      setMaquette({ ramGuard: false });
      error.error = null;
      say(t("chat.unloaded"), "success");
    }
  });

  // --- Écran masqué puis revu (reprise par `?after=<seq>`) --------------------------------
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
    status,
    submit,
    get run() {
      return run;
    },
    get answerText() {
      return current?.text ?? "";
    },
    whenPickerReady: () => waitUntil(() => picker.selected !== null || picker.querySelector("wl-error:not([hidden])"), 5000),
    // Conversation rouverte (GET /api/conversations/{id}) : rendue d'un coup, sans flux.
    reopen() {
      for (const message of data.conversation.messages) {
        if (message.role === "user") {
          thread.addUserMessage(message.text);
          transcript.push({ role: "user", text: message.text });
          continue;
        }
        const replay = thread.beginAnswer({ name: message.name, origin: message.origin });
        if (message.thought) replay.token(message.thought, "thought");
        replay.token(message.text, "answer");
        const metrics = { lane: message.tag, ...data.metrics[message.metrics] };
        replay.metrics(metrics);
        replay.end({ status: "ok" });
        transcript.push({ role: "assistant", ...message, metrics });
      }
      say(t("chat.reopened"));
      render();
    },
  };

  render();
  return () => {
    view = null;
    visibility.disconnect();
    guard.dispose?.();
    attachment?.close();
  };
}

// --- Scénarios ----------------------------------------------------------------------------

const speedOf = () => store.get().maquette.speed || 1;

function waitUntil(condition, timeoutMs = 20000) {
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

const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms / speedOf()));

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
}

async function ask(ctx, { model, question, ...options } = {}) {
  if (model) await choose(model);
  const data = await ctx.data("chat-libre.json");
  view.input.value = question ?? data.default_question;
  return view.submit(options);
}

const untilTokens = (count = 80) => waitUntil(() => view.answerText.length >= count);
const untilDone = (simRun) => simRun?.done ?? Promise.resolve();

export const scenarios = [
  {
    id: "vide",
    label: "Conversation vide",
    run: (ctx) => fresh(ctx),
  },
  {
    id: "reponse-locale",
    label: "Réponse locale complète (raisonnement replié, CO₂ mesuré)",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await ask(ctx));
    },
  },
  {
    id: "reponse-en-cours",
    label: "Réponse en cours : débit provisoire, Arrêter",
    async run(ctx) {
      await fresh(ctx);
      await ask(ctx);
      await untilTokens(120);
    },
  },
  {
    id: "premier-chargement-lent",
    label: "Premier chargement lent du modèle (8 à 26 s)",
    async run(ctx) {
      await fresh(ctx, () => setMaquette({ slowLoad: true }));
      await ask(ctx);
      await waitUntil(() => view.status.dataset.stage === "loading");
    },
  },
  {
    id: "arret",
    label: "Arrêter pendant la génération : partiel gardé, « Arrêté »",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await ask(ctx);
      await untilTokens(100);
      await view.status.cancel();
      await untilDone(simRun);
    },
  },
  {
    id: "reponse-cloud-estimee",
    label: "Réponse cloud : CO₂ « estimé »",
    async run(ctx) {
      await fresh(ctx, () => ctx.store.set({ allowCloud: true }));
      await untilDone(await ask(ctx, { model: "gpt-5-mini" }));
    },
  },
  {
    id: "reponse-cloud-non-mesurable",
    label: "Réponse cloud : CO₂ « non mesurable » avec sa raison",
    async run(ctx) {
      await fresh(ctx, () => ctx.store.set({ allowCloud: true }));
      await untilDone(await ask(ctx, { model: "claude-haiku-4-5" }));
    },
  },
  {
    id: "conversation-rouverte",
    label: "Conversation rouverte (plusieurs échanges terminés)",
    async run(ctx) {
      await fresh(ctx);
      view.reopen();
    },
  },
  {
    id: "reprise-au-retour",
    label: "Aller sur l'Accueil pendant la réponse, puis revenir : reprise sans perte",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await ask(ctx);
      await untilTokens(60);
      await ctx.navigate("/");
      await pause(1500);
      await ctx.navigate("/arene/chat");
      await untilDone(simRun);
    },
  },
  {
    id: "rejoint-409",
    label: "Une réponse tourne déjà (autre onglet) : 409 rejoint",
    async run(ctx) {
      await fresh(ctx);
      const data = await ctx.data("chat-libre.json");
      const model = await findModel("qwen3.5:2b");
      sim.play("chat-libre-reponse", null, {
        kind: "chat",
        module: "chat",
        vars: { tag: model.tag, temperature: 0.7, loading: false, load_s: null, thought: "", answer: data.answers.default.text, partial: "", tps: 41, metrics: { lane: model.tag, ...data.metrics[model.tag] } },
      });
      await pause(400);
      await ask(ctx);
      await untilTokens(40);
    },
  },
  {
    id: "relance-automatique",
    label: "Ollama coupe la génération : relance automatique réussie",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await ask(ctx, { script: "chat-libre-relance" }));
    },
  },
  {
    id: "erreur-interrompue",
    label: "Erreur « interrupted » : la relance échoue",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await ask(ctx, { script: "chat-libre-interrompu", error: "interrupted" }));
    },
  },
  {
    id: "erreur-delai",
    label: "Erreur « timeout » : délai dépassé",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await ask(ctx, { script: "chat-libre-delai", error: "timeout" }));
    },
  },
  {
    id: "erreur-ollama-arrete",
    label: "Ollama arrêté : bandeau et erreur à l'envoi",
    async run(ctx) {
      await fresh(ctx, () => setOllamaDown(true));
      await ask(ctx, { model: "qwen3.5:2b" });
    },
  },
  {
    id: "erreur-cloud-injoignable",
    label: "Fournisseur cloud injoignable",
    async run(ctx) {
      await fresh(ctx, () => ctx.store.set({ allowCloud: true }));
      await untilDone(await ask(ctx, { model: "claude-haiku-4-5", script: "chat-libre-erreur", error: "cloud_unreachable" }));
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
      // Le modèle cloud est choisi, puis le cloud coupé juste avant l'envoi : la commande est
      // refusée (défense en profondeur), et le sélecteur retire le modèle en le disant.
      ctx.store.set({ allowCloud: true });
      await choose("gpt-5-mini");
      view.input.value = (await ctx.data("chat-libre.json")).default_question;
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
    label: "Garde-fou mémoire : question gardée, deux issues",
    async run(ctx) {
      await fresh(ctx, () => setMaquette({ ramGuard: true }));
      await ask(ctx, { model: "qwen3.6:7b" });
    },
  },
  {
    id: "aucun-modele",
    label: "Aucun modèle de conversation installé",
    async run(ctx) {
      await fresh(ctx, () => setMaquette({ noLocalModel: true }));
    },
  },
  {
    id: "connexion-perdue",
    label: "Connexion perdue pendant la réponse, puis reprise sans doublon",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await ask(ctx);
      await untilTokens(60);
      simRun.cut(4000);
      await pause(1500);
      await untilDone(simRun);
      await waitUntil(() => ctx.store.get().connection.status === "open");
    },
  },
  {
    id: "aller-a-la-fin",
    label: "Longue réponse, défilement remonté : « Aller à la fin »",
    async run(ctx) {
      await fresh(ctx);
      const data = await ctx.data("chat-libre.json");
      const simRun = await ask(ctx, { question: data.long_question, answer: "long" });
      await untilDone(simRun);
      const log = view.thread.querySelector(".wl-thread-log");
      log.scrollTop = 0;
      log.dispatchEvent(new Event("scroll"));
      await waitUntil(() => !view.thread.querySelector(".wl-thread-end").hidden);
    },
  },
  {
    id: "serveur-redemarre",
    label: "Le serveur redémarre pendant la réponse : « Interrompu »",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await ask(ctx);
      await untilTokens(60);
      sim.restartServer();
      await untilDone(simRun);
    },
  },
];
