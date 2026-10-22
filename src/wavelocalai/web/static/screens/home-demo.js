// Carte « Démo recommandée » de l'Accueil (story 3.6, UX-DR24, D-10, D-11) : l'Arène, première étape du
// Flow 1. « Arène » en titre, « Arène des modèles » en sous-titre, sa phrase, les modèles prêts du
// défaut `arena` avec leur badge, et « Lancer une comparaison » qui ouvre l'Arène (qui présélectionne
// ce même défaut).
//
//   const demo = demoSection();   demo?.el  demo?.render(state)  demo?.dispose()
//
// - La carte n'existe que si l'écran de l'Arène est disponible (registre) : aucune carte ne mène à un
//   écran absent.
// - Sans modèle local prêt, elle dit « Aucun modèle local disponible » et, si le cloud est autorisé,
//   propose des modèles cloud ; sinon elle dit quoi faire. « Lancer une comparaison » reste actif dans
//   tous les cas : l'Arène dit alors quoi faire (D-11).
// - Les modèles viennent de `GET /api/models` et `GET /api/models/defaults?purpose=arena` (cache du
//   registre) ; ils sont relus quand le cloud est autorisé ou coupé, ou qu'Ollama change d'état. Aucun
//   calcul : la carte met en page ce que le serveur dit (AD-20).

import { api } from "../core/api.js";
import { element, icon } from "../core/dom.js";
import { t } from "../core/i18n.js";
import { MODULES, entryScreen } from "../core/registry.js";
import { shellReady } from "../core/shell-ready.js";
import "../components/wl-badge.js";

const CLOUD_PROPOSED = 3;

function modelLine(label, models) {
  const line = element("div", "home-demo-line");
  line.append(element("p", "home-demo-label", label));
  const items = element("ul", "home-demo-list");
  for (const model of models) {
    const item = element("li", "home-demo-item");
    const badge = document.createElement("wl-badge");
    badge.setAttribute("kind", model.origin === "cloud" ? "cloud" : "local");
    item.append(element("span", "home-demo-model", model.name), badge);
    items.append(item);
  }
  line.append(items);
  return line;
}

// Les lignes de la carte selon la liste des modèles et le défaut `arena` du serveur.
function modelLines(list, defaults, allowCloud) {
  const chat = (list?.models ?? []).filter((model) => model.kind === "chat");
  const ready = (defaults?.tags ?? [])
    .map((tag) => chat.find((model) => model.tag === tag))
    .filter((model) => model && model.available && model.origin === "local");
  if (ready.length) return [modelLine(t("home.demo.ready"), ready)];
  const lines = [element("p", "home-card-strong", t("home.demo.no_local"))];
  const cloud = chat.filter((model) => model.origin === "cloud" && model.available);
  if (allowCloud && cloud.length) {
    lines.push(modelLine(t("home.demo.cloud_ready"), cloud.slice(0, CLOUD_PROPOSED)));
  } else {
    const hint = allowCloud ? "home.demo.no_local_cloud_on" : "home.demo.no_local_cloud_off";
    lines.push(element("p", "home-card-hint", t(hint)));
  }
  return lines;
}

export function demoSection() {
  const arena = MODULES.find((module) => module.id === "arena");
  const compare = arena?.screens.find((screen) => screen.id === "arena-compare");
  if (!arena || !entryScreen(arena) || compare?.status !== "available") return null;

  const title = element("h2", "section-label", t("home.demo.title"));
  title.id = "home-demo-title";
  const name = element("h3", "home-demo-name");
  name.append(icon(arena.icon), element("span", "", t("modules.arena")));
  const long = element("p", "home-demo-long", t("home.modules_long.arena"));
  const text = element("p", "home-demo-text", t("home.demo.text"));
  const models = element("div", "home-demo-models");
  const skeleton = element("span", "home-skeleton");
  skeleton.append(element("span", "sr-only", t("home.loading")));
  models.append(skeleton);
  const launch = element("a", "btn home-demo-launch", t("home.demo.launch"));
  launch.href = `#${compare.path}`;
  const card = element("article", "home-demo");
  card.dataset.demo = "";
  card.append(name, long, text, models, launch);
  const el = element("section", "home-section");
  el.setAttribute("aria-labelledby", title.id);
  el.append(title, card);

  let key = "";
  let alive = true;

  async function load(allowCloud, current) {
    let list = null;
    let defaults = null;
    await shellReady(); // AD-15 : rien de `/api/` avant que la coquille soit rendue
    try {
      list = await api.models(allowCloud);
      // Sans modèle local prêt, le défaut `arena` n'a rien à dire (le serveur répondrait `no_model`) :
      // on ne le demande pas.
      const local = list.models.some((m) => m.kind === "chat" && m.origin === "local" && m.available);
      if (local) defaults = await api.modelDefaults("arena", allowCloud).catch(() => null);
    } catch {
      list = null;
    }
    if (!alive || key !== current) return;
    const lines = list
      ? modelLines(list, defaults, allowCloud)
      : [element("p", "home-card-hint", t("home.demo.unavailable"))];
    models.replaceChildren(...lines);
    card.dataset.state = list ? "ready" : "unavailable";
  }

  return {
    el,
    render(state) {
      const next = `${state.allowCloud}|${state.ollama.known}|${state.ollama.up}`;
      if (next === key) return;
      key = next;
      load(state.allowCloud, next);
    },
    dispose() {
      alive = false;
    },
  };
}
