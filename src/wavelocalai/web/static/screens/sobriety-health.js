// Sobriété, section « Santé du système » (story 5.1) : quatre cartes lues dans le store, rempli par
// le flux système (processeur, mémoire, accélérateur, Ollama). Aucun appel d'API, aucune mesure
// calculée ici (AD-20) : les valeurs arrivent du serveur et sont seulement mises en forme.
//
// - Squelette tant que le premier état du flux n'est pas arrivé ; « inconnu » si la connexion est
//   perdue (une valeur périmée ferait croire à un direct).
// - Accélérateur : « Aucun » sans GPU détecté par NVML (champ `gpu` absent du flux), jamais
//   « Actif » sans détection. Le bridage thermique se dit en texte, avec une icône, jamais par la
//   couleur seule.
// - Ollama arrêté : « Ollama ne répond pas » et « Réessayer » (la demande de la barre haute). La
//   version d'Ollama est la légende de la section (décision du 2026-10-19).
// - Les valeurs sont remplacées sur place, sans `aria-live` (une annonce toutes les 2 s rendrait le
//   lecteur d'écran inutilisable).

import { element, icon } from "../core/dom.js";
import {
  formatGb,
  formatInteger,
  formatNumber,
  formatPercent,
  formatUnknown,
  plural,
} from "../core/format.js";
import { t } from "../core/i18n.js";
import { recheckOllama } from "../core/system.js";

// Ne touche le DOM que si la valeur change : une carte mise à jour toutes les 2 s ne clignote pas.
export function setText(node, text) {
  if (node.textContent !== text) node.textContent = text;
}

export function setAttr(node, name, value) {
  if (node.getAttribute(name) !== value) node.setAttribute(name, value);
}

function metricCard(id, label, help) {
  const root = element("article", "sob-card");
  root.dataset.card = id;
  const metric = document.createElement("wl-metric");
  metric.setAttribute("label", label);
  metric.setAttribute("help", help);
  const bar = element("span", "sob-skeleton");
  bar.append(element("span", "sr-only", t("sobriety.loading")));
  const detail = element("div", "sob-card-detail");
  root.append(metric, bar, detail);
  return { root, metric, bar, detail };
}

function setBusy(card, busy) {
  setAttr(card.root, "aria-busy", String(busy));
  card.bar.hidden = !busy;
}

function buildCards() {
  const cpu = metricCard("cpu", t("sobriety.health.cpu_label"), t("sobriety.health.cpu_help"));

  const memory = metricCard(
    "memory",
    t("sobriety.health.memory_label"),
    t("sobriety.health.memory_help"),
  );
  memory.free = element("p", "sob-line sob-hint");
  memory.detail.append(memory.free);

  const gpu = metricCard(
    "accelerator",
    t("sobriety.health.accelerator_label"),
    t("sobriety.health.accelerator_help"),
  );
  gpu.name = element("p", "sob-line");
  gpu.temperature = element("p", "sob-line");
  gpu.throttled = element("p", "sob-line sob-warn");
  gpu.throttled.append(icon("warning"), element("span", "", t("sobriety.health.throttled")));
  gpu.none = element("p", "sob-line sob-hint", t("sobriety.health.accelerator_none_line"));
  gpu.detail.append(gpu.name, gpu.temperature, gpu.throttled, gpu.none);

  const ollama = metricCard(
    "ollama",
    t("sobriety.health.ollama_label"),
    t("sobriety.health.ollama_help"),
  );
  ollama.hint = element("p", "sob-line sob-hint", t("sobriety.health.ollama_down_hint"));
  ollama.retry = element("button", "btn", t("sobriety.health.ollama_retry"));
  ollama.retry.type = "button";
  ollama.retry.setAttribute("aria-disabled", "false");
  ollama.retry.addEventListener("click", () => {
    if (ollama.retry.getAttribute("aria-disabled") !== "true") recheckOllama();
  });
  ollama.detail.append(ollama.hint, ollama.retry);
  return { cpu, memory, gpu, ollama };
}

function renderCpu(card, ctx, state) {
  ctx.pick(card, formatPercent(state.system.cpuPercent));
}

function renderMemory(card, ctx, state) {
  const memory = state.system.memory;
  ctx.pick(
    card,
    memory
      ? t("sobriety.health.memory_value", {
          used: formatNumber(memory.used_gb),
          total: formatGb(memory.total_gb),
        })
      : formatUnknown(),
  );
  // « Disponibles » : la mémoire que compare le garde-fou, donnée par le serveur (aucune soustraction ici).
  const shown = !ctx.waiting && !ctx.lost && memory && memory.available_gb != null;
  setText(
    card.free,
    shown ? t("sobriety.health.memory_free", { value: formatGb(memory.available_gb) }) : "",
  );
}

function renderGpu(card, ctx, state) {
  const gpu = state.system.gpu;
  const known = !ctx.waiting && !ctx.lost;
  ctx.pick(
    card,
    gpu
      ? t("sobriety.health.memory_value", {
          used: formatNumber(gpu.memory_used_gb),
          total: formatGb(gpu.memory_total_gb),
        })
      : t("sobriety.health.accelerator_none"),
  );
  setText(card.name, known && gpu ? gpu.name : "");
  setText(
    card.temperature,
    known && gpu && gpu.temperature_c != null
      ? t("sobriety.health.temperature", { value: formatInteger(Math.round(gpu.temperature_c)) })
      : "",
  );
  card.throttled.hidden = !(known && gpu && gpu.thermal_throttle === true);
  card.none.hidden = !known || Boolean(gpu);
}

function renderOllama(card, ctx, state) {
  const down = state.ollama.known && !state.ollama.up;
  const models = state.system.modelsLoaded;
  let value = formatUnknown();
  let help = t("sobriety.health.ollama_help");
  if (down) {
    value = t("sobriety.health.ollama_down");
  } else if (Array.isArray(models)) {
    value =
      models.length === 0
        ? t("sobriety.health.ollama_none")
        : plural("sobriety.health.ollama_loaded", models.length, {
            count: formatInteger(models.length),
          });
    if (models.length > 0) {
      const names = models
        .map((model) =>
          t("sobriety.health.ollama_model", { tag: model.tag, size: formatGb(model.size_gb) }),
        )
        .join(", ");
      help = `${help} ${plural("sobriety.health.ollama_names", models.length, { names })}`;
    }
  }
  ctx.pick(card, value);
  setAttr(card.metric, "help", help);
  const showDown = !ctx.waiting && !ctx.lost && down;
  card.hint.hidden = !showDown;
  card.retry.hidden = !showDown;
  // « Réessayer » qui disparaît avec le focus (Ollama revenu) : le focus passe à la carte.
  if (!showDown && document.activeElement === card.retry) {
    card.root.tabIndex = -1;
    card.root.focus();
  }
  setAttr(card.retry, "aria-disabled", String(state.ollamaChecking));
  setText(
    card.retry,
    state.ollamaChecking ? t("sobriety.health.ollama_retrying") : t("sobriety.health.ollama_retry"),
  );
}

export function buildHealth() {
  const title = element("h2", "", t("sobriety.health.title"));
  title.id = "sob-health-title";
  const version = element("p", "help sob-legend");
  version.dataset.legend = "ollama-version";
  const live = element("p", "help sob-legend");
  live.dataset.legend = "live";
  const cards = buildCards();
  const grid = element("div", "sob-cards");
  grid.append(cards.cpu.root, cards.memory.root, cards.gpu.root, cards.ollama.root);
  const section = element("section", "sob-section");
  section.setAttribute("aria-labelledby", title.id);
  section.append(title, version, live, grid);

  // `paused` : l'onglet est masqué, le flux fermé, les dernières valeurs restent affichées.
  function render(state, { paused = false } = {}) {
    const lost = state.connection.status === "lost";
    const waiting = !state.systemSeen && !lost;
    const ctx = {
      lost,
      waiting,
      pick(card, value) {
        setBusy(card, waiting);
        setAttr(card.metric, "value", waiting ? "" : lost ? formatUnknown() : value);
      },
    };
    renderCpu(cards.cpu, ctx, state);
    renderMemory(cards.memory, ctx, state);
    renderGpu(cards.gpu, ctx, state);
    renderOllama(cards.ollama, ctx, state);

    const up = state.ollama.known && state.ollama.up;
    setText(
      version,
      lost || waiting || !up
        ? ""
        : state.ollama.version
          ? t("sobriety.health.ollama_version", { version: state.ollama.version })
          : t("sobriety.health.ollama_version_unknown"),
    );
    setText(
      live,
      lost
        ? t("sobriety.health.lost")
        : paused
          ? t("sobriety.health.paused")
          : t("sobriety.health.live"),
    );
  }

  return { section, render };
}
