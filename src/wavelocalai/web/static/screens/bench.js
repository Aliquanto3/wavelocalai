// Banc d'essai, `#/arene/banc[/<run_id>]` (UX-DR13, UX-DR17, UX-DR25, UX-DR29, AD-5, AD-6, AD-8, AD-20) :
// lancer un scénario prédéfini et savoir si la sortie respecte le format attendu.
//
// - Un seul lecteur du flux du run : cet écran (`connectRun`). Il passe chaque enveloppe à
//   `wl-run-status` (mode piloté : étape, chronomètre, Arrêter, Échap) et pose la réponse en flux.
// - À `run_ended`, l'instantané du run (`GET /api/runs/{id}`) donne ce que le serveur a calculé : le
//   verdict de format (`format_verdict`, absent sans format attendu), la sortie, le débit, le CO₂ et
//   la durée. Le front ne valide ni ne mesure rien (AD-20).
// - L'essai est conservé : `#/arene/banc/<run_id>` le relit depuis la base, sans relancer de modèle
//   (`run_not_found` : « Essai introuvable »). L'écran liste aussi les essais passés.
// - « Relancer le test » rejoue la configuration de l'essai affiché ; « Modifier le test » la reprend
//   dans le formulaire, sans lancer.
// - `409 run_busy` : l'essai en cours est rejoint (rejoué depuis le début). `ram_guard` : l'entrée est
//   gardée, « Prendre un modèle plus petit » remplace le modèle sans relancer.
// - L'écran reste en mémoire quand on va ailleurs (le routeur le masque) : masqué, il ferme son flux en
//   gardant le dernier `seq` ; de retour, il le rouvre par `?after=<seq>`.

import { api, ApiError } from "../core/api.js";
import { element } from "../core/dom.js";
import { formatNumber } from "../core/format.js";
import { t } from "../core/i18n.js";
import { onSmallerModel } from "../core/ram-guard.js";
import { screenTabs } from "../core/screen-tabs.js";
import { connectRun } from "../core/sse.js";
import { store } from "../core/store.js";
import "../components/wl-error.js";
import { readSettled } from "./arena-snapshot.js";
import { formView } from "./bench-form.js";
import { historyView } from "./bench-history.js";
import { resultView } from "./bench-result.js";

const BASE = "#/arene/banc";
let counter = 0;

function envelopeOf(error) {
  if (error instanceof ApiError && error.envelope) return error.envelope;
  return { code: "internal", message: t("bench.start_failed") };
}

// « Délai dépassé (120 s) » : le délai réel, celui que le serveur a appliqué (`detail.timeout_s`).
function withDelay(error) {
  if (error?.code !== "timeout") return error;
  const seconds = error.detail?.timeout_s;
  if (typeof seconds !== "number" || !Number.isFinite(seconds)) return error;
  return { ...error, message: t("bench.timeout", { seconds: formatNumber(seconds) }) };
}

export function mount(host, params = {}) {
  const uid = `bench-${++counter}`;
  let scenarios = [];
  let form = null;
  const scenarioName = (id) => scenarios.find((item) => item.id === id)?.name ?? id ?? "";
  const modelName = (tag) => form?.picker.modelFor(tag)?.name;

  // --- Structure -------------------------------------------------------------------------
  const slot = element("div", "bc-slot");
  const notice = element("p", "chat-notice");
  notice.setAttribute("role", "status");
  notice.hidden = true;
  const error = document.createElement("wl-error");
  error.setAttribute("alert", "");
  const result = resultView(uid);
  const past = historyView(uid, { scenarioName, modelName });
  const missingTitle = element("h2", "", t("bench.missing.title"));
  missingTitle.id = `${uid}-missing-title`;
  const missingText = element("p", "");
  const missingError = document.createElement("wl-error");
  const missingLink = element("a", "btn", t("bench.missing.new"));
  missingLink.href = BASE;
  const missing = element("section", "bc-missing");
  missing.setAttribute("role", "alert");
  missing.setAttribute("aria-labelledby", missingTitle.id);
  missing.hidden = true;
  missing.append(missingTitle, missingText, missingError, missingLink);
  const live = element("div", "sr-only");
  live.setAttribute("role", "status");
  live.setAttribute("aria-live", "polite");
  live.setAttribute("aria-atomic", "true");

  host.replaceChildren(
    element("h1", "", t("screens.arena-bench")),
    screenTabs("arena", "arena-bench"),
    element("p", "lead", t("bench.lead")),
    missing,
    slot,
    notice,
    error,
    result.el,
    past.el,
    live,
  );

  // --- État ------------------------------------------------------------------------------
  let runId = null; // l'essai suivi, tant qu'il n'est pas terminé
  let stream = null;
  let pending = false; // commande envoyée, réponse du serveur attendue
  let text = "";
  let phase = "idle"; // idle | running | done
  let final = { verdict: undefined, measures: null, hasSchema: false, ok: true };
  let shown = null; // configuration de l'essai affiché (« Relancer », « Modifier »)
  let adopt = false; // essai rejoint : le formulaire prend sa configuration
  let joined = null;
  let frame = 0;
  let ticket = 0; // une lecture tardive d'un essai précédent n'écrase pas le courant
  let alive = true;
  let wasHidden = host.hidden;

  const running = () => runId !== null;

  function announce(message) {
    live.textContent = ""; // vider puis remplir : un même texte est de nouveau annoncé
    requestAnimationFrame(() => {
      live.textContent = message;
    });
  }

  function paint() {
    cancelAnimationFrame(frame);
    frame = 0;
    result.show({ phase, text, ...final });
    form?.refresh();
  }

  function schedule() {
    if (!frame) frame = requestAnimationFrame(paint);
  }

  function clearRun() {
    ticket += 1;
    cancelAnimationFrame(frame);
    frame = 0;
    text = "";
    phase = "idle";
    final = { verdict: undefined, measures: null, hasSchema: false, ok: true };
    error.error = null;
    missing.hidden = true;
    result.status.runId = null;
  }

  // --- Flux ------------------------------------------------------------------------------
  async function finish(state) {
    const id = runId;
    runId = null;
    stream?.close();
    stream = null;
    const mine = ++ticket;
    const snapshot = id ? await readSettled(id, () => mine === ticket) : null;
    if (mine !== ticket || !alive) return;
    phase = "done";
    if (snapshot?.bench) {
      text = snapshot.bench.output || text;
      final = {
        verdict: snapshot.format_verdict,
        measures: snapshot.metrics,
        hasSchema: Boolean(scenarios.find((item) => item.id === snapshot.bench.scenario)?.schema),
        ok: state === "ok",
      };
    } else {
      final = { verdict: undefined, measures: null, hasSchema: false, ok: false };
    }
    paint();
    past.refresh();
    const verdict = final.verdict;
    let key = "failed";
    if (state === "cancelled") key = "cancelled";
    else if (state === "ok") key = verdict ? (verdict.ok ? "ok" : "ko") : "done";
    announce(t(`bench.announce.${key}`));
  }

  const forward = (_data, envelope) => result.status.feed(envelope);
  const handlers = {
    run_started: (data, envelope) => {
      if (data?.kind !== "bench") {
        // Le run rejoint n'est pas un banc d'essai : on le dit, sans le suivre.
        stream?.close();
        stream = null;
        runId = null;
        clearRun();
        notice.textContent = t("bench.other_run");
        notice.hidden = false;
        paint();
        return;
      }
      joined = {
        scenario: data.params?.scenario,
        model: Array.isArray(data.models) ? data.models[0] : undefined,
        force_format: Boolean(data.params?.force_format),
        concise: Boolean(data.params?.concise),
      };
      phase = "running";
      forward(data, envelope);
      schedule();
    },
    bench_input: (data) => {
      const config = { ...joined, scenario: data?.scenario ?? joined?.scenario, input: data?.text ?? "" };
      shown = config;
      if (adopt) form?.apply(config);
    },
    model_loading: forward,
    model_loaded: forward,
    token: (data, envelope) => {
      if ((data?.channel ?? "answer") === "answer") text += data?.text ?? "";
      forward(data, envelope);
      schedule();
    },
    retry: () => {
      text = ""; // génération relancée : le texte partiel n'est plus la réponse
      schedule();
    },
  };
  handlers.run_ended = (data, envelope) => {
    const failure = data?.error ? withDelay(data.error) : null;
    forward(data, { ...envelope, data: { ...data, error: failure } });
    const status = ["ok", "cancelled", "error"].includes(data?.status) ? data.status : "interrupted";
    finish(status);
  };

  function openStream(id) {
    stream?.close({ keepSeq: true });
    stream = connectRun(id, handlers, ({ status }) => {
      // Run inconnu ou serveur muet après plusieurs essais, sans `run_ended` : on le dit.
      if (status === "failed" && running()) {
        result.status.abandon();
        finish("interrupted");
      }
    });
  }

  function follow(id, { adopting = false } = {}) {
    clearRun();
    runId = id;
    adopt = adopting;
    phase = "running";
    result.status.runId = id;
    if (!host.hidden) openStream(id); // masqué : le flux s'ouvrira au retour (AD-6)
    paint();
  }

  // --- Actions ---------------------------------------------------------------------------
  async function submit() {
    if (!form || form.reason()) return;
    const config = form.config();
    notice.hidden = true;
    error.error = null;
    missing.hidden = true;
    const refocus = document.activeElement === form.launch;
    pending = true;
    form.refresh();
    try {
      const started = await api.startBench({ ...config, allow_cloud: store.get().allowCloud });
      shown = config;
      if (location.hash.startsWith(`${BASE}/`)) resetAddress();
      follow(started.run_id);
      past.refresh();
      announce(t("bench.announce.started"));
    } catch (failure) {
      const busy = failure instanceof ApiError ? failure.envelope : null;
      if (failure.status === 409 && busy?.code === "run_busy" && busy.detail?.run_id) {
        follow(busy.detail.run_id, { adopting: true });
        notice.textContent = t("bench.notice.joined");
        notice.hidden = false;
      } else {
        error.error = envelopeOf(failure);
      }
    } finally {
      pending = false;
      form.refresh();
      if (refocus && !running()) form.launch.focus();
    }
  }

  // L'adresse d'un essai rouvert laisse la place à celle de l'écran : le nouvel essai n'a pas encore
  // d'adresse qui le désigne, et recharger ne doit pas rouvrir l'ancien.
  function resetAddress() {
    try {
      window.history.replaceState(null, "", BASE);
    } catch {
      // Adresse laissée telle quelle.
    }
  }

  function again(kind) {
    if (!form || !shown || running()) return;
    form.apply(shown);
    if (kind === "rerun") submit();
    else {
      form.input.focus();
      form.input.scrollIntoView?.({ block: "center" });
    }
  }
  result.onAction(again);

  // --- Rouvrir ---------------------------------------------------------------------------
  function showMissing(reason, envelope = null) {
    clearRun();
    missingText.textContent = t(`bench.missing.${reason}`);
    missingError.error = envelope;
    missing.dataset.code = envelope?.code ?? reason;
    missing.hidden = false;
    paint();
  }

  async function reopen(id) {
    const mine = ++ticket;
    let snapshot;
    try {
      snapshot = await api.run(id);
    } catch (failure) {
      if (mine !== ticket || !alive) return;
      if (failure instanceof ApiError && failure.envelope?.code === "run_not_found") showMissing("unknown", failure.envelope);
      else error.error = envelopeOf(failure);
      return;
    }
    if (mine !== ticket || !alive) return;
    if (snapshot?.kind !== "bench") {
      showMissing("unknown", { code: "run_not_found", message: t("bench.missing.unknown") });
      return;
    }
    const config = {
      scenario: snapshot.bench?.scenario,
      model: snapshot.model,
      input: snapshot.bench?.input ?? "",
      force_format: Boolean(snapshot.bench?.force_format),
      concise: Boolean(snapshot.bench?.concise),
    };
    form.apply(config);
    shown = config;
    if (["running", "awaiting_approval"].includes(snapshot.status)) {
      follow(id, { adopting: true });
      return;
    }
    clearRun();
    text = snapshot.bench?.output ?? "";
    phase = "done";
    final = {
      verdict: snapshot.format_verdict,
      measures: snapshot.metrics,
      hasSchema: Boolean(scenarios.find((item) => item.id === config.scenario)?.schema),
      ok: snapshot.status === "ok",
    };
    if (snapshot.error) error.error = withDelay(snapshot.error);
    notice.textContent = t("bench.notice.reopened");
    notice.hidden = false;
    paint();
  }

  // --- Démarrage -------------------------------------------------------------------------
  const cleanups = [];
  const onVisibility = () => {
    if (host.hidden === wasHidden) return;
    wasHidden = host.hidden;
    if (wasHidden) {
      stream?.close({ keepSeq: true });
      stream = null;
    } else if (running()) openStream(runId);
  };
  const visibility = new MutationObserver(onVisibility);
  visibility.observe(host, { attributes: true, attributeFilter: ["hidden"] });

  async function start() {
    try {
      scenarios = (await api.scenarios()).scenarios ?? [];
    } catch (failure) {
      if (!alive) return;
      error.error = envelopeOf(failure);
      return;
    }
    if (!alive) return;
    if (scenarios.length === 0) {
      error.error = { code: "internal", message: t("bench.no_scenario") };
      return;
    }
    form = formView(uid, scenarios);
    form.setBusy(() => running() || pending);
    slot.replaceChildren(form.el);
    form.el.addEventListener("submit", (event) => {
      event.preventDefault();
      submit();
    });
    cleanups.push(
      onSmallerModel(host, (tag) => {
        form.picker.value = tag;
        form.refresh();
        const name = form.picker.modelFor(tag)?.name ?? tag;
        notice.textContent = t("bench.notice.smaller", { name });
        notice.hidden = false;
        announce(notice.textContent);
      }),
      store.select((state) => state.allowCloud, () => form.refresh()),
    );
    form.refresh();
    past.refresh();
    if (params.run_id) {
      reopen(params.run_id);
      return;
    }
    // Un essai en cours (flux système) est rejoint : quitter son adresse ne le perd pas.
    const active = (store.get().runsActive ?? []).find((run) => run?.kind === "bench" && run.run_id);
    if (active) {
      notice.textContent = t("bench.notice.joined");
      notice.hidden = false;
      follow(active.run_id, { adopting: true });
    }
  }
  start();

  return () => {
    alive = false;
    for (const stop of cleanups) stop();
    visibility.disconnect();
    cancelAnimationFrame(frame);
    stream?.close();
    stream = null;
  };
}
