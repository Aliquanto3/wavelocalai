// Installation d'un modèle, côté écran Modèles (story 5.3, AD-5, AD-6, AD-14, AD-17).
//
// Un seul run `pull` à la fois (`409 run_busy` : l'écran rejoint celui qui tourne, sans erreur). Ce
// contrôleur est le seul lecteur de son flux (`connectRun`) : `pull_progress` met à jour la barre sur
// place, `run_ended` solde (« Installé », annulé, ou `pull_failed` dans un `wl-error`). Il ne
// touche pas aux tableaux : il dit `onChange()` quand l'installation en cours change (début, fin,
// nom connu) et `onEnded()` à la fin, et l'écran relit ses listes.
//
// - Quitter l'écran ferme le flux en gardant le dernier `seq` ; y revenir le rouvre par `?after=`
//   (AD-6). Une page rechargée, ou une installation lancée ailleurs, se retrouve par `runsActive`
//   du flux système (un run `pull` actif) : son flux rejoué depuis le début redit le tag.
// - Seule la fin est annoncée (zone polie `say`) : jamais chaque pourcentage.
// - Aucun calcul de mesure (AD-20) : octets, pourcentage et phase viennent du serveur.

import { api, ApiError, request } from "../core/api.js";
import { t } from "../core/i18n.js";
import { connectRun } from "../core/sse.js";
import { store } from "../core/store.js";
import { createProgress } from "./models-progress.js";

export function createPull({ host, nameOf, onChange, onEnded, onProblem, say }) {
  let active = null; // { runId, tag } : l'installation suivie (`runId` nul le temps du POST)
  let stream = null;
  let failure = null; // { tag } : le dernier échec, son enveloppe est dans `failureNode`
  let done = null; // le tag de la dernière installation réussie
  const finished = new Set(); // runs déjà soldés : un `runsActive` périmé ne les rouvre pas

  const progress = createProgress({ onCancel: () => cancel() });
  const failureNode = document.createElement("wl-error");
  const doneNode = document.createElement("p");
  doneNode.className = "models-pull-done";
  doneNode.textContent = t("models.pull.installed");

  const label = (tag) => (tag ? nameOf(tag) : "");

  function finish(status, error) {
    const ended = active;
    if (ended === null) return;
    if (ended.runId) finished.add(ended.runId);
    stream?.close();
    stream = null;
    active = null;
    const name = label(ended.tag) || ended.tag || "";
    failure = null;
    done = null;
    if (status === "ok") {
      done = ended.tag;
      say(t("models.pull.done", { name }));
    } else if (status === "cancelled") {
      say(t("models.pull.cancelled", { name }));
    } else {
      const envelope = error ?? {
        code: "pull_failed",
        message: t("models.pull.failed", { name }),
        action: t("models.pull.failed_action"),
      };
      failure = { tag: ended.tag };
      failureNode.error = envelope;
      say(envelope.message);
    }
    progress.cancelling(false);
    onChange();
    onEnded({ status, tag: ended.tag });
  }

  const handlers = {
    run_started: (payload) => {
      if (active && !active.tag && payload?.models?.[0]) {
        active.tag = payload.models[0];
        onChange(); // le nom est connu : la barre rejoint sa ligne
      }
    },
    pull_progress: (payload) => {
      if (!active) return;
      if (!active.tag && payload.tag) {
        active.tag = payload.tag;
        onChange();
      }
      progress.update(payload, label(active.tag));
    },
    run_ended: (payload) => finish(payload?.status ?? "error", payload?.error ?? null),
  };

  function openStream() {
    const run = active;
    if (!run?.runId) return;
    stream?.close({ keepSeq: true });
    stream = connectRun(run.runId, handlers, async ({ status }) => {
      if (active !== run || !["closed", "failed"].includes(status)) return;
      // Flux fini sans `run_ended` (rien à rejouer, ou run introuvable) : l'état vient du run.
      let ended = "error";
      try {
        ended = (await request(`/api/runs/${encodeURIComponent(run.runId)}`)).status;
      } catch {
        // Run inconnu : l'installation est dite interrompue.
      }
      if (active !== run) return;
      if (ended !== "running") finish(ended, null);
      else if (!host.hidden) openStream();
    });
  }

  function follow(runId, tag) {
    active = { runId, tag };
    progress.update({ phase: "preparing", percent: null }, label(tag));
    if (!host.hidden) openStream();
    onChange();
  }

  // Lance l'installation d'un nom d'Ollama ; un clic, aucune autre action ne télécharge (AD-17).
  async function start(tag) {
    if (active) return;
    failure = null;
    done = null;
    failureNode.error = null;
    active = { runId: null, tag };
    progress.update({ phase: "preparing", percent: null }, label(tag));
    onChange();
    try {
      const started = await api.pullModel(tag);
      if (active?.tag !== tag || active.runId) return;
      active.runId = started.run_id;
      if (!host.hidden) openStream();
    } catch (cause) {
      const busy = cause instanceof ApiError && cause.status === 409 && cause.envelope?.detail?.run_id;
      active = null;
      if (busy) {
        say(t("models.pull.elsewhere"));
        follow(cause.envelope.detail.run_id, null);
        return;
      }
      onProblem(cause instanceof ApiError && cause.envelope ? cause.envelope : null);
      onChange();
    }
  }

  let cancelRequested = false;
  async function cancel() {
    const run = active;
    if (!run?.runId || cancelRequested) return;
    cancelRequested = true;
    progress.cancelling(true);
    try {
      await api.cancelRun(run.runId);
    } catch {
      progress.cancelling(false); // l'arrêt n'a pas été pris : on peut redemander
    } finally {
      cancelRequested = false;
    }
  }

  // Une installation active du serveur que cet écran ne suit pas encore (page rechargée, lancée
  // depuis un autre onglet) : on la rejoint.
  const unsubscribe = store.select(
    (state) => state.runsActive.find((run) => run.kind === "pull")?.run_id ?? null,
    (runId) => {
      if (runId && !active && !finished.has(runId)) follow(runId, null);
    },
  );

  return {
    progress,
    failureNode,
    doneNode,
    start,
    cancel,
    get busy() {
      return active !== null;
    },
    get activeTag() {
      return active?.tag ?? null;
    },
    get failedTag() {
      return failure?.tag ?? null;
    },
    get doneTag() {
      return done;
    },
    // L'écran est masqué (le routeur le garde monté) ou revu.
    setHidden(hidden) {
      if (hidden) {
        stream?.close({ keepSeq: true });
        stream = null;
      } else if (active?.runId) {
        openStream();
      }
    },
    dispose() {
      unsubscribe();
      stream?.close();
      stream = null;
    },
  };
}
