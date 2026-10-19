// Accueil (UX-DR24) : le titre, l'accroche, quatre cartes d'état en direct (Système, Mode,
// Processeur, Mémoire) et les liens des modules livrés. Les cartes lisent le store, rempli par le
// flux système (AD-6) ; l'écran ne calcule aucune mesure (AD-20). Seuls appels : le résumé de la base
// documentaire (`GET /api/rag/documents`) et la carte « Références » (`GET /api/references`, story 5.8),
// lus une fois par affichage, jamais en boucle.
//
// - Squelette tant que le premier état du flux n'est pas arrivé, jamais d'écran blanc.
// - Ollama arrêté : « Indisponible », la marche à suivre et « Réessayer » ; les liens restent actifs.
// - Onglet masqué : les cartes cessent de se mettre à jour (le flux est fermé par `core/system.js`)
//   et reprennent au retour.
// - Aucune carte ne mène à un écran absent : « Démo recommandée » (`home-demo.js`, story 3.6) n'existe
//   que si l'Arène l'est. Un module n'est listé que si son écran est disponible.
// - Carte « Documents » : le résumé de la base (« N documents indexés · M extraits », story 4.9)
//   remplace la phrase d'accroche dès que le serveur l'a donné ; sans réponse, la phrase reste. Le
//   routeur garde l'Accueil monté quand on le quitte : le résumé est relu à chaque retour dessus,
//   jamais avant le repère `shell-ready` (AD-15).

import { api } from "../core/api.js";
import { element, icon } from "../core/dom.js";
import {
  formatCo2,
  formatGb,
  formatInteger,
  formatPercent,
  formatUnknown,
  plural,
} from "../core/format.js";
import { t } from "../core/i18n.js";
import { MODULES, entryScreen } from "../core/registry.js";
import { store } from "../core/store.js";
import { shellReady } from "../core/shell-ready.js";
import { recheckOllama } from "../core/system.js";
import { demoSection } from "./home-demo.js";
import { referencesCard } from "./home-references.js";

// Ne touche le DOM que si la valeur change : une carte mise à jour toutes les 2 s ne clignote pas.
function setText(node, text) {
  if (node.textContent !== text) node.textContent = text;
}

function setAttr(node, name, value) {
  if (node.getAttribute(name) !== value) node.setAttribute(name, value);
}

// Une carte : la métrique (libellé et valeur), le squelette du premier chargement, ses détails.
function metricCard(id, label) {
  const root = element("article", "home-card");
  root.dataset.card = id;
  const metric = document.createElement("wl-metric");
  metric.setAttribute("label", label);
  const bar = element("span", "home-skeleton");
  bar.append(element("span", "sr-only", t("home.loading")));
  const detail = element("div", "home-card-detail");
  root.append(metric, bar, detail);
  return { root, metric, bar, detail };
}

function setBusy(card, busy) {
  setAttr(card.root, "aria-busy", String(busy));
  card.bar.hidden = !busy;
}

function buildSystem() {
  const card = metricCard("system", t("home.system.label"));
  const up = element("div", "home-card-group");
  const version = element("p", "home-card-line");
  const loaded = element("p", "home-card-line");
  up.append(version, loaded);

  const down = element("div", "home-card-group");
  const action = element("p", "home-card-line home-card-strong", t("home.system.down_action"));
  const hint = element("p", "home-card-line home-card-hint", t("home.system.down_hint"));
  const noModel = element("p", "home-card-line", t("home.system.no_local_model"));
  const retry = element("button", "btn", t("home.system.retry"));
  retry.type = "button";
  retry.setAttribute("aria-disabled", "false");
  retry.addEventListener("click", () => {
    if (retry.getAttribute("aria-disabled") !== "true") recheckOllama();
  });
  down.append(action, hint, noModel, retry);

  const lost = element("p", "home-card-line", t("home.system.lost"));
  card.detail.append(up, down, lost);
  return { ...card, up, version, loaded, down, retry, lost };
}

function buildMode() {
  const root = element("article", "home-card");
  root.dataset.card = "mode";
  const head = element("p", "home-card-label", t("home.mode.label"));
  const value = element("p", "home-card-value");
  const badge = document.createElement("wl-badge");
  value.append(badge);
  const detail = element("p", "home-card-line");
  const co2 = element("p", "home-card-line home-card-hint");
  root.append(head, value, detail, co2);
  return { root, badge, detail, co2 };
}

function loadedText(models) {
  if (models.length === 0) return t("home.system.loaded_none");
  if (models.length === 1) return t("home.system.loaded_one");
  return t("home.system.loaded_many", { count: formatInteger(models.length) });
}

function renderSystem(card, state) {
  const lost = state.connection.status === "lost";
  const known = state.ollama.known;
  setBusy(card, !known && !lost);
  const key = lost ? "unknown" : !known ? "loading" : state.ollama.up ? "up" : "down";
  setAttr(card.root, "data-state", key);
  setAttr(card.metric, "value", key === "loading" ? "" : t(`home.system.${key}`));

  // « Réessayer » qui disparaît avec le focus (Ollama revenu) : le focus passe à la carte, qui
  // annonce le nouvel état, au lieu de tomber sur `body`.
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
      state.ollama.version
        ? t("home.system.version", { version: state.ollama.version })
        : t("home.system.version_unknown"),
    );
    const models = state.system.modelsLoaded;
    card.loaded.hidden = !Array.isArray(models);
    if (Array.isArray(models)) setText(card.loaded, loadedText(models));
  }
  if (key === "down") {
    const checking = state.ollamaChecking;
    setAttr(card.retry, "aria-disabled", String(checking));
    setText(card.retry, checking ? t("home.system.retrying") : t("home.system.retry"));
  }
}

function renderMode(card, state) {
  const cloud = state.allowCloud;
  setAttr(card.badge, "kind", cloud ? "cloud" : "local");
  setText(card.detail, cloud ? t("home.mode.cloud_detail") : t("home.mode.local_detail"));
  const carbon = state.carbon;
  if (!carbon) {
    setText(card.co2, t("home.mode.co2", { value: formatUnknown() }));
  } else if ((carbon.measured_runs ?? 0) === 0) {
    setText(card.co2, t("home.mode.co2_none"));
  } else {
    setText(card.co2, t("home.mode.co2", { value: formatCo2(carbon.total_mg) }));
  }
}

// Valeur d'une métrique du poste : vide pendant le squelette, « inconnu » si le serveur ne répond
// plus (une valeur périmée ferait croire à un direct), sinon la valeur mise en forme.
function renderLive(card, state, format) {
  const lost = state.connection.status === "lost";
  const waiting = !state.systemSeen && !lost;
  setBusy(card, waiting);
  setAttr(card.metric, "value", waiting ? "" : lost ? formatUnknown() : format(state.system));
  setText(card.live, lost || waiting ? "" : t("home.live"));
  return { lost, waiting };
}

function renderCpu(card, state) {
  renderLive(card, state, (system) => formatPercent(system.cpuPercent));
}

function renderMemory(card, state) {
  const { lost, waiting } = renderLive(card, state, (system) =>
    system.memory ? formatGb(system.memory.used_gb) : formatUnknown(),
  );
  const memory = state.system.memory;
  setText(
    card.total,
    lost || waiting || !memory ? "" : t("home.memory.total", { total: formatGb(memory.total_gb) }),
  );
}

// Les modules dont l'écran existe, hors Accueil. Rien n'est listé pour un écran à venir : la
// barre haute les montre déjà, désactivés, avec leur raison.
function modulesSection() {
  const items = [];
  const summaries = {};
  const references = referencesCard(); // carte « Références », à la suite de l'Arène (story 5.8)
  for (const module of MODULES) {
    if (module.id === "home") continue;
    const entry = entryScreen(module);
    if (!entry) continue;
    const link = element("a", "home-module-link");
    link.href = `#${entry.path}`;
    // Nom court du menu en titre, nom long en sous-titre, puis la phrase de résumé (D-10).
    const summary = element("span", "home-module-summary", t(`home.modules.${module.id}`));
    summaries[module.id] = summary;
    link.append(
      icon(module.icon),
      element("span", "home-module-name", t(`modules.${module.id}`)),
      element("span", "home-module-long", t(`home.modules_long.${module.id}`)),
      summary,
    );
    const li = element("li", "home-module");
    li.append(link);
    items.push(li);
    if (module.id === "arena" && references) items.push(references.el);
  }
  if (items.length === 0) return null;
  const section = element("section", "home-section");
  section.setAttribute("aria-labelledby", "home-modules-title");
  const title = element("h2", "", t("home.modules_title"));
  title.id = "home-modules-title";
  const list = element("ul", "home-module-list");
  list.append(...items);
  section.append(title, list);
  return { section, summaries, references };
}

// « 3 documents indexés · 14 extraits » : les documents prêts seulement (`totals`, D-26).
function baseSummary(totals) {
  return `${plural("home.documents_indexed", totals.documents)} · ${plural("docs.chunks", totals.chunks)}`;
}

export function mount(host) {
  const title = element("h1", "", t("screens.home"));
  const lead = element("p", "lead", t("home.lead"));

  const system = buildSystem();
  const mode = buildMode();
  const cpu = metricCard("cpu", t("home.cpu.label"));
  cpu.live = element("p", "home-card-line home-card-hint");
  cpu.detail.append(cpu.live);
  const memory = metricCard("memory", t("home.memory.label"));
  memory.total = element("p", "home-card-line");
  memory.live = element("p", "home-card-line home-card-hint");
  memory.detail.append(memory.total, memory.live);

  const cards = element("div", "home-cards");
  cards.append(system.root, mode.root, cpu.root, memory.root);
  const status = element("section", "home-section");
  status.setAttribute("aria-labelledby", "home-status-title");
  const statusTitle = element("h2", "", t("home.status_title"));
  statusTitle.id = "home-status-title";
  status.append(statusTitle, cards);

  const parts = [title, lead, status];
  const demo = demoSection();
  if (demo) parts.push(demo.el);
  const modules = modulesSection();
  if (modules) parts.push(modules.section);
  host.replaceChildren(...parts);

  // Le résumé de la base : une lecture à chaque affichage de l'écran (le routeur le monte masqué puis
  // l'affiche) et au retour de l'onglet s'il est affiché. Rien avant `shell-ready` (AD-15). Une
  // panne laisse la phrase d'accroche ; une réponse tardive d'un écran démonté ne touche à rien.
  let mounted = true;
  let wasHidden = host.hidden;
  const visibility = new MutationObserver(() => {
    if (host.hidden === wasHidden) return;
    wasHidden = host.hidden;
    if (!wasHidden) refreshBase();
  });
  visibility.observe(host, { attributes: true, attributeFilter: ["hidden"] });
  async function refreshBase() {
    modules?.references?.refresh(); // sa propre lecture, masquée sans références publiées
    const node = modules?.summaries.documents;
    if (!node) return;
    await shellReady();
    if (!mounted) return;
    try {
      const { totals } = await api.documents();
      if (mounted && totals) setText(node, baseSummary(totals));
    } catch {
      // l'accroche reste
    }
  }

  function render(state) {
    renderSystem(system, state);
    renderMode(mode, state);
    renderCpu(cpu, state);
    renderMemory(memory, state);
    demo?.render(state);
  }

  // Onglet masqué : on ne lit plus le store (le flux est fermé), et on reprend au retour.
  let unsubscribe = null;
  function resume() {
    if (unsubscribe) return;
    host.dataset.live = "true";
    unsubscribe = store.subscribe(render);
    render(store.get());
  }
  function pause() {
    unsubscribe?.();
    unsubscribe = null;
    host.dataset.live = "false";
  }
  function onVisibility() {
    if (document.hidden) {
      pause();
    } else {
      resume();
      if (!host.hidden) refreshBase();
    }
  }

  document.addEventListener("visibilitychange", onVisibility);
  if (document.hidden) {
    host.dataset.live = "false";
    render(store.get());
  } else {
    resume();
  }
  if (!host.hidden) refreshBase(); // monté déjà affiché : l'observateur ne verra pas de changement

  return () => {
    mounted = false;
    visibility.disconnect();
    document.removeEventListener("visibilitychange", onVisibility);
    demo?.dispose();
    modules?.references?.dispose();
    pause();
    delete host.dataset.live;
    host.replaceChildren();
  };
}
