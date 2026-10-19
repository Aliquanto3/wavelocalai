// Discussion, `#/documents` (UX-DR8, UX-DR10, UX-DR11, UX-DR17, UX-DR19, UX-DR23, AD-6, AD-7, AD-9,
// AD-14, AD-20) : poser une question à ses documents, lire la réponse à côté de ses sources.
//
// - Un seul lecteur du flux d'un run : cet écran (`connectRun`). Il passe chaque enveloppe à
//   `wl-run-status` (mode piloté, « Recherche des extraits… » puis « Génération… ») et au fil
//   `wl-chat-thread`. `sources` arrive AVANT le premier `token` : le panneau `wl-source-panel` se
//   remplit pendant que la réponse s'écrit.
// - Un seul panneau pour plusieurs réponses : il montre les sources de la dernière réponse ; dès la
//   deuxième réponse, chacune porte « Afficher les sources » qui y charge les siennes (D-23). À
//   droite dès 1 024 px, toujours ouvert (D-22) ; en deçà, sous la réponse, replié.
// - L'écran reste en mémoire quand on va ailleurs (le routeur le masque). Masqué, il ferme son flux
//   en gardant le dernier `seq` ; de retour, il le rouvre par `?after=<seq>` (client SSE, `keepSeq`).
// - `409 run_busy` : le run actif est rejoint, sans erreur affichée. `409 rag_base_empty` : l'erreur
//   du serveur s'affiche et l'écran relit la base (le message mène alors à la Base documentaire).
// - À l'ouverture, la dernière conversation `rag` est relue au serveur ; les sources et les mesures
//   de chaque réponse viennent de son flux rejoué (`connectRun`, run fini) : le message de
//   conversation n'a ni sources ni mesures. Un document supprimé depuis rend « extrait supprimé ».
// - Les marqueurs `[n]` du texte restent tels que le modèle les a écrits ; seuls ceux que l'événement
//   `citations` confirme (le serveur les a vérifiés contre les sources) deviennent des boutons
//   (`documents-citations.js`) : survoler ou focaliser `[n]` met la source en évidence, et
//   inversement. Sans `citations`, le front n'en fabrique aucun. Pas de « Télécharger » : aucune
//   route d'export RAG (sprint-change-proposal 2026-10-19, §7 (d), point 12).
// - « Réglages avancés » (`documents-chat-settings.js`) : stratégie de recherche et nombre d'extraits,
//   envoyés avec chaque question ; HyDE commence par « Rédaction d'une réponse hypothétique… ».
// - Un modèle cloud reçoit les extraits retrouvés : l'avertissement le dit tant qu'il est choisi
//   (AD-9). `allow_cloud` du store accompagne chaque commande.

import { api, ApiError } from "../core/api.js";
import { element, icon } from "../core/dom.js";
import { loadDraft, saveDraft } from "../core/drafts.js";
import { plural } from "../core/format.js";
import { t } from "../core/i18n.js";
import { screenTabs } from "../core/screen-tabs.js";
import { connectRun } from "../core/sse.js";
import { store } from "../core/store.js";
import "../components/index.js";
import { decorateCitations, linkMarkers } from "./documents-citations.js";
import { replayAll } from "./documents-replay.js";
import { advancedSettings, firstStage } from "./documents-chat-settings.js";

const DRAFT = "documents";
let counter = 0;

function envelopeOf(error, message) {
  if (error instanceof ApiError && error.envelope) return error.envelope;
  return { code: "internal", message };
}

export function mount(host) {
  const uid = `documents-${++counter}`;

  // --- Structure -------------------------------------------------------------------------
  const summary = element("p", "docs-count docs-chat-summary");
  const baseLink = element("a", "docs-chat-link", t("discussion.base_link"));
  baseLink.href = "#/documents/base";
  const summaryText = element("span", "docs-chat-count");
  summary.append(summaryText, baseLink);
  summary.hidden = true;
  const indexingNote = element("p", "help docs-chat-indexing");
  indexingNote.hidden = true;
  const problem = document.createElement("wl-error");

  const emptyTitle = element("h2", "");
  const emptyText = element("p", "");
  const emptyAction = element("a", "btn docs-primary");
  emptyAction.href = "#/documents/base";
  const emptyCard = element("section", "docs-card");
  emptyCard.hidden = true;
  emptyCard.append(emptyTitle, emptyText, emptyAction);

  const picker = document.createElement("wl-model-picker");
  picker.setAttribute("purpose", "rag");
  const cloudNote = element("p", "docs-cloud-note");
  cloudNote.hidden = true;
  const pickerColumn = element("div", "docs-chat-picker");
  pickerColumn.append(picker, cloudNote);

  const advanced = advancedSettings(uid);
  const settings = element("div", "docs-chat-settings");
  settings.append(pickerColumn, advanced.node);

  const empty = element("p", "help chat-empty", t("discussion.empty_thread"));
  const thread = document.createElement("wl-chat-thread");
  const status = document.createElement("wl-run-status");
  status.setAttribute("driven", "");
  status.setAttribute("first-stage", "retrieving");
  const notice = element("p", "chat-notice");
  notice.setAttribute("role", "status");
  notice.hidden = true;
  const error = document.createElement("wl-error");
  error.setAttribute("alert", "");
  const main = element("div", "docs-chat-main");
  main.append(empty, thread, status, notice, error);
  const panel = document.createElement("wl-source-panel");
  panel.classList.add("docs-chat-sources");

  const input = element("textarea", "chat-input");
  input.id = `${uid}-question`;
  input.rows = 3;
  input.value = loadDraft(DRAFT);
  input.setAttribute("aria-describedby", `${uid}-keys`);
  const inputLabel = element("label", "chat-input-label", t("discussion.question"));
  inputLabel.htmlFor = input.id;
  const keys = element("p", "help", t("discussion.keys"));
  keys.id = `${uid}-keys`;
  const send = element("button", "btn chat-send", t("discussion.send"));
  send.type = "submit";
  const clear = element("button", "btn", t("discussion.clear"));
  clear.type = "button";
  const actions = element("div", "chat-actions");
  actions.append(send, clear);
  const composer = element("form", "chat-composer");
  composer.append(inputLabel, input, keys, actions);

  const layout = element("div", "docs-chat-layout");
  layout.append(main, panel, composer);
  const workspace = element("div", "docs-chat-workspace");
  workspace.append(settings, layout);

  host.replaceChildren(
    element("h1", "", t("screens.documents-chat")),
    screenTabs("documents", "documents-chat"),
    element("p", "lead", t("discussion.lead")),
    summary,
    indexingNote,
    problem,
    emptyCard,
    workspace,
  );

  // --- État ------------------------------------------------------------------------------
  let base = null; // dernière réponse de GET /api/rag/documents
  let conversationId = null;
  let runId = null; // le run suivi, tant qu'il n'est pas terminé
  let stream = null;
  let answer = null; // la réponse du fil qui reçoit le flux
  let current = null; // son enregistrement : { name, sources, node, button }
  let displayed = null; // l'enregistrement dont le panneau montre les sources
  const records = [];
  let wasHidden = host.hidden;
  let pending = false; // commande envoyée, réponse du serveur attendue
  let refreshing = false;

  const running = () => runId !== null;

  // --- Rendu -----------------------------------------------------------------------------
  function renderBase() {
    const ready = base?.totals?.documents ?? null;
    const indexing = (base?.documents ?? []).filter((doc) => doc.status === "indexing").length;
    summary.hidden = base === null;
    if (base !== null) {
      summaryText.textContent = `${plural("discussion.documents", ready)} · ${plural("docs.chunks", base.totals.chunks)}`;
    }
    indexingNote.hidden = indexing === 0;
    if (indexing) indexingNote.textContent = plural("discussion.indexing", indexing);
    // Base sans document prêt et aucune conversation : un message mène à la Base documentaire.
    const blocked = ready === 0 && thread.empty && !running();
    emptyCard.hidden = !blocked;
    workspace.hidden = blocked;
    if (blocked) {
      error.error = null; // le message de la carte dit déjà quoi faire
      notice.hidden = true;
      const waiting = indexing > 0;
      emptyTitle.textContent = t(waiting ? "discussion.indexing_only_title" : "discussion.empty_title");
      emptyText.textContent = t(waiting ? "discussion.indexing_only_text" : "discussion.empty_text");
      emptyAction.textContent = t(waiting ? "discussion.indexing_only_action" : "discussion.empty_action");
    }
  }

  function render() {
    clear.disabled = running() || pending;
    send.disabled = running() || pending;
    clear.hidden = thread.empty;
    empty.hidden = !thread.empty;
    renderBase();
  }

  function updateCloudNote() {
    const model = picker.selected;
    const cloud = model?.origin === "cloud";
    cloudNote.hidden = !cloud;
    cloudNote.replaceChildren();
    if (cloud) {
      cloudNote.append(icon("warning"), element("span", "", t("discussion.cloud_warning", { name: model.name })));
    }
  }

  async function refreshBase() {
    if (refreshing) return;
    refreshing = true;
    try {
      base = await api.documents();
      // Défauts et bornes de la recherche : réglages de l'écran Base, relus à chaque rafraîchissement.
      // Sans eux (route en échec), aucun `top_k` n'est envoyé et le serveur applique le sien.
      api.ragSettings().then(
        (settings) =>
          advanced.configure({
            topK: settings.top_k,
            maxTopK: settings.limits?.top_k?.max,
            strategy: settings.strategy,
            reranker: settings.reranker,
          }),
        () => {},
      );
      problem.error = null;
    } catch (failure) {
      problem.error = envelopeOf(failure, t("docs.list_failed"));
      if (!(failure instanceof ApiError && failure.envelope)) problem.error.action = t("docs.list_failed_action");
    } finally {
      refreshing = false;
      render();
    }
  }

  // --- Sources et réponses ---------------------------------------------------------------
  function refreshButtons() {
    for (const record of records) {
      if (!record.sources.length || !record.node?.actions) continue;
      if (!record.button) {
        const button = element("button", "btn docs-show-sources", t("discussion.show_sources"));
        button.type = "button";
        button.setAttribute("aria-label", t("discussion.show_sources_for", { name: record.name }));
        button.addEventListener("click", () => showSources(record));
        record.node.actions.append(button);
        record.button = button;
      }
      // Avec une seule réponse, le panneau la montre déjà : le bouton sert dès la deuxième (D-23).
      record.button.hidden = records.length < 2;
      record.button.setAttribute("aria-pressed", String(displayed === record));
    }
  }

  function showSources(record) {
    if (displayed === record && panel.sources === record.sources) return refreshButtons();
    displayed = record;
    panel.sources = record.sources;
    refreshButtons();
  }

  // Citations vérifiées : survoler ou focaliser `[n]` met la source n en évidence, et inversement.
  const citeHooks = {
    enter(record, n) {
      showSources(record);
      panel.highlight(n);
      linkMarkers(record.node.body, n);
    },
    leave(record) {
      panel.highlight(null);
      linkMarkers(record.node.body, null);
    },
    click(record, n) {
      showSources(record);
      panel.open(n);
    },
  };
  panel.addEventListener("wl-source-link", (event) => {
    if (displayed?.node) linkMarkers(displayed.node.body, event.detail.n);
  });

  function register(record) {
    record.citations ??= [];
    // Chaque rendu du texte (flux, fin, réponse rouverte) repasse par les citations confirmées.
    record.node.decorator = (body) => decorateCitations(body, record, citeHooks);
    records.push(record);
    return record;
  }

  function ensureAnswer(tag) {
    if (!answer) {
      answer = thread.beginAnswer({ name: tag ?? "", origin: "unknown" });
      current = register({ name: tag ?? "", sources: [], node: answer, button: null });
    }
    empty.hidden = true;
    return answer;
  }

  function finish(finalStatus) {
    ensureAnswer(null).end({ status: finalStatus });
    runId = null;
    stream = null;
    answer = null;
    current = null;
    refreshButtons();
    render();
    refreshBase(); // les documents ont pu changer pendant la réponse
  }

  // --- Flux ------------------------------------------------------------------------------
  const forward = (_data, envelope) => status.feed(envelope);
  const handlers = {
    run_started: (data, envelope) => {
      ensureAnswer(Array.isArray(data?.models) ? data.models[0] : null);
      forward(data, envelope);
    },
    retrieval_step: forward,
    citations: (data) => {
      if (!answer || !current) return;
      current.citations = Array.isArray(data?.citations) ? data.citations : [];
      answer.refresh(); // le texte est rendu de nouveau : les marqueurs confirmés deviennent des boutons
    },
    sources: (data, envelope) => {
      ensureAnswer(null);
      current.sources = Array.isArray(data?.sources) ? data.sources : [];
      showSources(current);
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
    if (!host.hidden) openStream(id); // masqué : le flux s'ouvrira au retour (AD-6)
    render();
  }

  // --- Conversation rouverte -------------------------------------------------------------
  function showReply(run, message, replayed) {
    const record = {
      name: run?.model ?? "",
      sources: replayed?.sources ?? [],
      citations: replayed?.citations ?? [],
      node: null,
      button: null,
    };
    // Le décorateur est posé avant le rendu : une réponse rouverte a ses citations dès l'affichage.
    record.node = thread.restoreAnswer({
      name: run?.model ?? "",
      origin: replayed?.metrics?.origin ?? "unknown",
      text: message?.content ?? "",
      thought: message?.reasoning ?? "",
      result: replayed?.metrics ?? null,
      status: run?.status ?? "ok",
      decorator: (body) => decorateCitations(body, record, citeHooks),
    });
    register(record);
  }

  async function showConversation(view) {
    const ids = new Set();
    for (const message of view.messages) {
      const run = message.run;
      if (run && run.status !== "running") ids.add(run.run_id);
    }
    const finished = await replayAll(ids);
    // Une personne qui a déjà écrit n'est pas dérangée par la conversation d'avant.
    if (conversationId !== null || running() || pending || !thread.empty) return false;
    conversationId = view.id;
    const answered = new Set(
      view.messages.filter((m) => m.role === "assistant" && m.run).map((m) => m.run.run_id),
    );
    for (const message of view.messages) {
      if (message.role === "user") {
        thread.addUserMessage(message.content);
        const run = message.run;
        // Run fini sans réponse écrite (arrêté, en erreur) : la réponse vide et son marqueur.
        if (run && run.status !== "running" && !answered.has(run.run_id)) {
          showReply(run, null, finished.get(run.run_id));
        }
      } else if (message.role === "assistant") {
        showReply(message.run, message, finished.get(message.run?.run_id));
      }
    }
    const last = [...records].reverse().find((record) => record.sources.length);
    if (last) showSources(last);
    return true;
  }

  async function restore() {
    let view;
    try {
      const latest = (await api.conversations("rag", 1)).conversations[0];
      if (!latest) return;
      view = await api.conversation(latest.id);
    } catch {
      return; // pas d'historique lisible : l'écran reste vide, sans erreur
    }
    if (!(await showConversation(view))) return;
    if (view.model) {
      picker.value = view.model;
      updateCloudNote(); // le setter n'émet pas `wl-model-change` : l'avertissement cloud (AD-9)
    }
    if (view.active_run_id) follow(view.active_run_id);
    render();
  }

  // --- Actions ---------------------------------------------------------------------------
  async function submit() {
    if (running() || pending) return;
    const question = input.value;
    if (!question.trim()) {
      input.focus();
      return;
    }
    const model = picker.value;
    notice.hidden = true;
    error.error = null;
    if (!model) {
      error.error = { code: "no_model", message: t("discussion.no_model"), action: t("discussion.no_model_action") };
      return;
    }
    pending = true; // pas de second envoi (bouton ni Entrée) ni d'effacement pendant la requête
    render();
    try {
      const started = await api.startRag({
        conversation_id: conversationId,
        question,
        model,
        strategy: advanced.strategy(),
        ...(advanced.topK() === null ? {} : { top_k: advanced.topK() }),
        allow_cloud: store.get().allowCloud,
      });
      conversationId = started.conversation_id ?? conversationId;
      thread.addUserMessage(question);
      if (input.value === question) {
        // Un texte tapé pendant la requête reste dans le champ.
        input.value = "";
        saveDraft(DRAFT, "");
      }
      const chosen = picker.selected;
      answer = thread.beginAnswer({ name: chosen?.name ?? model, origin: chosen?.origin });
      current = register({ name: chosen?.name ?? model, sources: [], node: answer, button: null });
      displayed = null;
      panel.clear(); // les sources de la réponse d'avant ne sont pas celles de cette question
      refreshButtons(); // plus aucun « Afficher les sources » n'est enfoncé
      status.setAttribute("first-stage", firstStage(advanced.strategy())); // HyDE rédige d'abord
      follow(started.run_id);
    } catch (failure) {
      const busy = failure instanceof ApiError ? failure.envelope : null;
      if (failure.status === 409 && busy?.code === "run_busy" && busy.detail?.run_id) {
        // Une question tourne déjà : on la rejoint, sans erreur. La question reste dans le champ.
        notice.textContent = t("discussion.joined");
        notice.hidden = false;
        follow(busy.detail.run_id);
      } else {
        error.error = envelopeOf(failure, t("discussion.start_failed"));
        if (busy?.code === "rag_base_empty") refreshBase(); // le message mène à la Base documentaire
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
      pending = true;
      render();
      try {
        await api.deleteConversation(conversationId);
      } catch (failure) {
        // Déjà effacée ailleurs (404) : même résultat. Sinon le message et l'action du serveur
        // s'affichent et la conversation reste.
        if (!(failure instanceof ApiError && failure.status === 404)) {
          error.error = envelopeOf(failure, t("discussion.start_failed"));
          pending = false;
          render();
          return;
        }
      }
      pending = false;
    }
    thread.clear();
    records.length = 0;
    displayed = null;
    panel.clear();
    status.runId = null;
    conversationId = null;
    answer = null;
    current = null;
    notice.textContent = t("discussion.cleared");
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
  picker.addEventListener("wl-model-change", updateCloudNote);
  picker.addEventListener("wl-models-loaded", updateCloudNote);

  // --- Écran masqué puis revu ------------------------------------------------------------
  // Le routeur masque l'écran sans le démonter : on ferme le flux (le serveur continue), et au
  // retour on reprend après le dernier `seq` reçu ; la base est relue (un import a pu finir).
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
      refreshBase();
    }
  });
  visibility.observe(host, { attributes: true, attributeFilter: ["hidden"] });

  render();
  updateCloudNote();
  // `data-restored` : la conversation d'avant a été relue (ou il n'y en avait pas).
  refreshBase()
    .then(restore)
    .finally(() => {
      host.dataset.restored = "";
    });
  return () => {
    visibility.disconnect();
    stream?.close();
    stream = null;
  };
}
