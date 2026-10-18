// Accueil, `#/` (UX-DR24, 03 §3.5, stories 1.11 et 3.6) : écran MODÈLE de la maquette, à l'état livré.
// Repris de la branche feat/v2-accueil (screens/home.js), complété des cartes des Epics 3 à 5.
//
// - Titre, accroche, quatre cartes d'état en direct (Système, Mode, Processeur, Mémoire) lues dans
//   le store ; squelette tant que le premier état n'est pas arrivé, jamais d'écran blanc.
// - « Démo recommandée » : l'Arène, les modèles prêts (défaut `arena`), « Lancer une comparaison ».
// - Modules avec un résumé : Assistant documentaire, Agents autonomes, Sobriété et matériel,
//   Modèles, Références (FR47).
// - Ollama arrêté : « Indisponible », la marche à suivre et « Réessayer » ; les liens restent actifs ;
//   la démo dit « Aucun modèle local disponible » et propose les modèles cloud si le cloud est permis.
// - Onglet masqué (`visibilitychange`, ou l'état global « onglet masqué ») : les cartes se figent.

import { element, icon } from "../core/dom.js";
import { formatCo2, formatGb, formatInteger, formatPercent, formatScore, formatUnknown } from "../core/format.js";
import { plural, t } from "../core/i18n.js";
import { setMaquette, store } from "../core/store.js";
import { listModels, modelDefaults } from "../sim/modeles.js";
import { loseConnection, recheck, setOllamaDown } from "../sim/systeme.js";

let view = null; // l'instance montée, pour les scénarios

function setText(node, text) {
  if (node.textContent !== text) node.textContent = text;
}

function setAttr(node, name, value) {
  if (node.getAttribute(name) !== value) node.setAttribute(name, value);
}

function metricCard(id, label) {
  const root = element("article", "home-card");
  root.dataset.card = id;
  const metric = document.createElement("wl-metric");
  metric.setAttribute("label", label);
  const bar = element("span", "home-skeleton");
  bar.append(element("span", "sr-only", t("accueil.loading")));
  const detail = element("div", "home-card-detail");
  root.append(metric, bar, detail);
  return { root, metric, bar, detail };
}

function setBusy(card, busy) {
  setAttr(card.root, "aria-busy", String(busy));
  card.bar.hidden = !busy;
}

function buildSystem() {
  const card = metricCard("system", t("accueil.system.label"));
  const up = element("div", "home-card-group");
  const version = element("p", "home-card-line");
  const loaded = element("p", "home-card-line");
  up.append(version, loaded);
  const down = element("div", "home-card-group");
  const action = element("p", "home-card-line home-card-strong", t("accueil.system.down_action"));
  const hint = element("p", "home-card-line home-card-hint", t("accueil.system.down_hint"));
  const retry = element("button", "btn", t("accueil.system.retry"));
  retry.type = "button";
  retry.setAttribute("aria-disabled", "false");
  retry.addEventListener("click", () => {
    if (retry.getAttribute("aria-disabled") !== "true") recheck();
  });
  down.append(action, hint, retry);
  const lost = element("p", "home-card-line", t("accueil.system.lost"));
  card.detail.append(up, down, lost);
  return { ...card, up, version, loaded, down, retry, lost };
}

function buildMode() {
  const root = element("article", "home-card");
  root.dataset.card = "mode";
  const head = element("p", "home-card-label", t("accueil.mode.label"));
  const value = element("p", "home-card-value");
  const badge = document.createElement("wl-badge");
  value.append(badge);
  const detail = element("p", "home-card-line");
  const calls = element("p", "home-card-line home-card-hint");
  root.append(head, value, detail, calls);
  return { root, badge, detail, calls };
}

function liveCard(id, label) {
  const card = metricCard(id, label);
  card.extra = element("p", "home-card-line");
  card.live = element("p", "home-card-line home-card-hint");
  card.detail.append(card.extra, card.live);
  return card;
}

function systemKey(state, forced) {
  if (forced === "loading") return "loading";
  if (state.connection.status === "lost") return "unknown";
  if (!state.ollama.known) return "loading";
  return state.ollama.up ? "up" : "down";
}

function renderSystem(card, state, forced) {
  const key = systemKey(state, forced);
  setBusy(card, key === "loading");
  setAttr(card.root, "data-state", key);
  setAttr(card.metric, "value", key === "loading" ? "" : t(`accueil.system.${key}`));
  // « Réessayer » qui disparaît avec le focus : le focus passe à la carte au lieu de tomber sur body.
  if (key !== "down" && document.activeElement === card.retry) {
    card.root.tabIndex = -1;
    card.root.focus();
  }
  card.up.hidden = key !== "up";
  card.down.hidden = key !== "down";
  card.lost.hidden = key !== "unknown";
  if (key === "up") {
    setText(
      card.version,
      state.ollama.version ? t("accueil.system.version", { version: state.ollama.version }) : t("accueil.system.version_unknown"),
    );
    const models = state.system.modelsLoaded;
    card.loaded.hidden = !Array.isArray(models);
    if (Array.isArray(models)) {
      setText(
        card.loaded,
        models.length === 0
          ? t("accueil.system.loaded_none")
          : plural("accueil.system.loaded", models.length, { count: formatInteger(models.length) }),
      );
    }
  }
  if (key === "down") {
    setAttr(card.retry, "aria-disabled", String(state.ollamaChecking));
    setText(card.retry, state.ollamaChecking ? t("accueil.system.retrying") : t("accueil.system.retry"));
  }
}

function renderMode(card, state) {
  const cloud = state.allowCloud;
  setAttr(card.badge, "kind", cloud ? "cloud" : "local");
  setText(card.detail, cloud ? t("accueil.mode.cloud_detail") : t("accueil.mode.local_detail"));
  const runs = state.carbon?.by_origin?.cloud?.runs ?? 0;
  setText(
    card.calls,
    runs === 0 ? t("accueil.mode.cloud_calls_none") : plural("accueil.mode.cloud_calls", runs, { count: formatInteger(runs) }),
  );
}

// Valeur d'une carte du poste : vide pendant le squelette, « inconnu » si le serveur ne répond plus.
function renderLive(card, state, forced, value) {
  const lost = state.connection.status === "lost";
  const waiting = forced === "loading" || (!state.systemSeen && !lost);
  setBusy(card, waiting);
  setAttr(card.metric, "value", waiting ? "" : lost ? formatUnknown() : value());
  setText(card.live, lost || waiting ? "" : t("accueil.live"));
  return { lost, waiting };
}

function buildDemo() {
  const section = element("section", "home-section");
  section.setAttribute("aria-labelledby", "home-demo-title");
  const title = element("h2", "", t("accueil.demo.title"));
  title.id = "home-demo-title";
  const card = element("article", "home-demo");
  const name = element("h3", "home-demo-name");
  name.append(icon("swords"), element("span", "", t("accueil.demo.name")));
  const text = element("p", "", t("accueil.demo.text"));
  const models = element("div", "home-demo-models");
  models.append(element("span", "home-skeleton home-skeleton-line"));
  const launch = element("a", "btn btn-primary home-demo-launch", t("accueil.demo.launch"));
  launch.href = "#/arene/comparer";
  card.append(name, text, models, launch);
  section.append(title, card);
  return { section, models };
}

function modelLine(label, list) {
  const line = element("div", "home-demo-line");
  line.append(element("p", "home-demo-label", label));
  const items = element("ul", "home-demo-list");
  for (const model of list) {
    const item = element("li", "home-demo-item");
    const badge = document.createElement("wl-badge");
    badge.setAttribute("kind", model.origin === "cloud" ? "cloud" : "local");
    item.append(element("span", "", model.name), badge);
    items.append(item);
  }
  line.append(items);
  return line;
}

async function renderDemo(demo, state, isCurrent) {
  const [list, defaults] = await Promise.all([
    listModels(state.allowCloud),
    modelDefaults("arena", state.allowCloud).catch(() => ({ tags: [] })),
  ]);
  if (!isCurrent()) return;
  const chat = list.models.filter((model) => model.kind === "chat");
  const ready = defaults.tags
    .map((tag) => chat.find((model) => model.tag === tag))
    .filter((model) => model && model.available && model.origin === "local");
  const parts = [];
  if (ready.length) {
    parts.push(modelLine(t("accueil.demo.ready"), ready));
  } else {
    parts.push(element("p", "home-card-strong", t("accueil.demo.no_local")));
    const cloud = chat.filter((model) => model.origin === "cloud" && model.available);
    if (state.allowCloud && cloud.length) parts.push(modelLine(t("accueil.demo.cloud_ready"), cloud.slice(0, 3)));
    else parts.push(element("p", "home-card-hint", t("accueil.demo.no_local_cloud_off")));
  }
  demo.models.replaceChildren(...parts);
}

function moduleLink(href, iconName, name) {
  const link = element("a", "home-module-link");
  link.href = href;
  const summary = element("span", "home-module-summary");
  const skeleton = element("span", "home-skeleton home-skeleton-line");
  skeleton.append(element("span", "sr-only", t("accueil.loading")));
  summary.append(skeleton);
  const open = element("span", "home-module-open", t("accueil.open"));
  open.setAttribute("aria-hidden", "true");
  link.append(icon(iconName), element("span", "home-module-name", name), summary, open);
  const item = element("li", "home-module");
  item.append(link);
  return { item, summary };
}

function buildModules() {
  const section = element("section", "home-section");
  section.setAttribute("aria-labelledby", "home-modules-title");
  const title = element("h2", "", t("accueil.modules_title"));
  title.id = "home-modules-title";
  const list = element("ul", "home-module-list");
  const links = {
    documents: moduleLink("#/documents", "description", t("accueil.modules.documents.name")),
    agents: moduleLink("#/agents/seul", "smart-toy", t("accueil.modules.agents.name")),
    sobriety: moduleLink("#/sobriete", "eco", t("accueil.modules.sobriety.name")),
    models: moduleLink("#/modeles", "deployed-code", t("accueil.modules.models.name")),
    references: moduleLink("#/arene/references", "swords", t("accueil.modules.references.name")),
  };
  list.append(...Object.values(links).map((link) => link.item));
  section.append(title, list);
  return { section, links };
}

function renderSummaries(links, summary) {
  const docs = summary.documents;
  links.documents.summary.textContent =
    docs.documents === 0
      ? t("accueil.modules.documents.summary_empty")
      : plural("accueil.modules.documents.summary", docs.documents, {
          count: formatInteger(docs.documents),
          chunks: formatInteger(docs.chunks),
        });
  links.agents.summary.textContent = t("accueil.modules.agents.summary", {
    tools: formatInteger(summary.agents.tools),
    disabled: formatInteger(summary.agents.disabled),
    reason: summary.agents.disabled_reason,
  });
  links.models.summary.textContent = t("accueil.modules.models.summary", {
    installed: formatInteger(summary.models.installed),
    installable: formatInteger(summary.models.installable),
  });
  const ref = summary.references;
  links.references.summary.textContent = t("accueil.modules.references.summary", {
    usage: ref.usage,
    model: ref.model,
    score: formatScore(ref.score),
    source: ref.source,
  });
}

function renderSobriety(link, carbon) {
  if (!carbon) return;
  setText(
    link.summary,
    carbon.measured_runs
      ? t("accueil.modules.sobriety.summary", { value: formatCo2(carbon.total_mg) })
      : t("accueil.modules.sobriety.summary_none"),
  );
}

export async function mount(host, ctx) {
  const title = element("h1", "", t("screens.home"));
  const lead = element("p", "lead", t("accueil.lead"));
  const system = buildSystem();
  const mode = buildMode();
  const cpu = liveCard("cpu", t("accueil.cpu.label"));
  const memory = liveCard("memory", t("accueil.memory.label"));
  const cards = element("div", "home-cards");
  cards.append(system.root, mode.root, cpu.root, memory.root);
  const status = element("section", "home-section");
  status.setAttribute("aria-labelledby", "home-status-title");
  const statusTitle = element("h2", "", t("accueil.status_title"));
  statusTitle.id = "home-status-title";
  status.append(statusTitle, cards);
  const demo = buildDemo();
  const modules = buildModules();
  host.replaceChildren(title, lead, status, demo.section, modules.section);

  let forced = null; // « loading » : squelettes forcés par un scénario
  let alive = true;
  let demoKey = "";

  function render(state) {
    renderSystem(system, state, forced);
    renderMode(mode, state);
    renderLive(cpu, state, forced, () => formatPercent(state.system.cpuPercent));
    const { lost, waiting } = renderLive(memory, state, forced, () =>
      state.system.memory ? formatGb(state.system.memory.used_gb) : formatUnknown(),
    );
    const total = state.system.memory?.total_gb;
    setText(memory.extra, lost || waiting || !total ? "" : t("accueil.memory.total", { total: formatGb(total) }));
    renderSobriety(modules.links.sobriety, state.carbon);
    const key = `${state.allowCloud}|${state.maquette.ollamaDown}|${state.maquette.noLocalModel}`;
    if (key !== demoKey) {
      demoKey = key;
      renderDemo(demo, state, () => alive && demoKey === key);
    }
  }

  // Mises à jour en direct, en pause quand l'onglet est masqué (réel ou simulé).
  let unsubscribe = null;
  const paused = () => document.hidden || store.get().maquette.livePaused;
  function pause() {
    unsubscribe?.();
    unsubscribe = null;
    host.dataset.live = "false";
    setText(cpu.live, "");
    setText(memory.live, "");
  }
  function resume() {
    if (unsubscribe) return;
    host.dataset.live = "true";
    unsubscribe = store.subscribe((state) => render(state));
    render(store.get());
  }
  const onVisibility = () => (paused() ? pause() : resume());
  document.addEventListener("visibilitychange", onVisibility);
  const unwatchPause = store.select((state) => state.maquette.livePaused, onVisibility);

  const summary = await ctx.data("accueil.json");
  const summaryTimer = setTimeout(
    () => {
      if (alive && forced !== "loading") renderSummaries(modules.links, summary);
    },
    summary.delay_ms / (store.get().maquette.speed || 1),
  );

  view = {
    force(state) {
      forced = state;
      render(store.get());
    },
  };

  return () => {
    alive = false;
    view = null;
    clearTimeout(summaryTimer);
    document.removeEventListener("visibilitychange", onVisibility);
    unwatchPause();
    pause();
    host.replaceChildren();
  };
}

const pauseFor = (ctx, ms) => new Promise((resolve) => setTimeout(resolve, ms / (ctx.store.get().maquette.speed || 1)));

// Scénarios (panneau Scénarios, tests) : chacun repart de l'état d'ouverture (`ctx.reset()`).
export const scenarios = [
  {
    id: "nominal",
    label: "Poste prêt (Ollama disponible, mode Local)",
    run: (ctx) => ctx.reset(),
  },
  {
    id: "premier-chargement",
    label: "Premier chargement : squelettes des cartes",
    async run(ctx) {
      await ctx.reset();
      view?.force("loading");
    },
  },
  {
    id: "ollama-arrete",
    label: "Ollama arrêté : « Indisponible » et marche à suivre",
    async run(ctx) {
      await ctx.reset();
      setOllamaDown(true);
    },
  },
  {
    id: "ollama-arrete-cloud",
    label: "Ollama arrêté, cloud autorisé : modèles cloud proposés",
    async run(ctx) {
      await ctx.reset();
      setOllamaDown(true);
      ctx.store.set({ allowCloud: true });
    },
  },
  {
    id: "aucun-modele-local",
    label: "Aucun modèle local installé",
    async run(ctx) {
      await ctx.reset();
      setMaquette({ noLocalModel: true });
    },
  },
  {
    id: "cloud-autorise",
    label: "Cloud autorisé : carte Mode en Cloud",
    async run(ctx) {
      await ctx.reset();
      ctx.store.set({ allowCloud: true });
    },
  },
  {
    id: "connexion-perdue",
    label: "Connexion au serveur perdue",
    async run(ctx) {
      await ctx.reset();
      loseConnection();
      await pauseFor(ctx, 1200);
    },
  },
  {
    id: "memoire-haute",
    label: "Mémoire presque pleine (garde-fou mémoire armé)",
    async run(ctx) {
      await ctx.reset();
      setMaquette({ ramGuard: true });
    },
  },
  {
    id: "onglet-masque",
    label: "Onglet masqué : cartes figées",
    async run(ctx) {
      await ctx.reset();
      setMaquette({ livePaused: true });
    },
  },
  {
    id: "suivre-demo-recommandee",
    label: "Suivre la démo recommandée (vers l'Arène)",
    run: (ctx) => ctx.navigate("/arene/comparer"),
  },
];
