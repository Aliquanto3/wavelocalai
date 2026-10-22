// Écran Modèles, `#/modeles` (UX-DR27, AD-5, AD-6, AD-15, AD-17, AD-20) : les modèles de ce poste, ce
// qui tient en mémoire, et l'installation d'un modèle avec sa progression chiffrée.
//
// Story 5.3 : la barre « Installer un modèle par son nom », « Sur ce poste » et le « Catalogue
// installable ». Story 5.4 : « Décharger les modèles inactifs », « Supprimer » (dialogue de
// confirmation) et « Modèles proposés par défaut ». Les suivantes ajoutent chacune leur section :
// la fiche d'un modèle (5.6). Story 5.5 : « Reclassement des extraits », l'installation du reranker
// local (même run `pull`). Story 5.6 : la fiche d'un modèle, `#/modeles/<tag>` (`models-card.js`,
// panneau à droite dès 1 120 px, au-dessus en deçà ; `update` suit l'adresse sans remonter l'écran).
// Un fichier par bloc : `models-installed.js`, `models-catalog.js`, `models-pull.js`,
// `models-unload.js`, `models-delete.js`, `models-defaults.js`, `models-rerank.js`, `models-card.js`.
//
// - Aucun appel d'API avant le repère `shell-ready` (AD-15) ; la page se construit avant.
// - Le front ne calcule rien (AD-20) : `fits`, la mémoire nécessaire et celle qui manque viennent
//   du serveur (`hardware/`) ; le débit est la médiane des runs de ce poste.
// - L'écran reste en mémoire quand on va ailleurs : masqué, le flux de l'installation se ferme en
//   gardant son `seq` ; de retour, il reprend par `?after=` et les listes se relisent.
// - Seule la fin d'une installation est annoncée (zone polie), jamais chaque pourcentage.

import { api, ApiError } from "../core/api.js";
import { element, moduleTitle } from "../core/dom.js";
import { formatGb } from "../core/format.js";
import { t } from "../core/i18n.js";
import { shellReady } from "../core/shell-ready.js";
import { store } from "../core/store.js";
import "../components/index.js";
import { createCard } from "./models-card.js";
import { createCatalog } from "./models-catalog.js";
import { createDefaults } from "./models-defaults.js";
import { createDeleter } from "./models-delete.js";
import { createInstalled } from "./models-installed.js";
import { createPull } from "./models-pull.js";
import { createRerank } from "./models-rerank.js";
import { createUnload } from "./models-unload.js";

const baseTag = (tag) => tag.replace(/:latest$/, "");

// Les écrans montés, par hôte : le routeur appelle `update` quand seule l'adresse de la fiche change.
const mounted = new WeakMap();

export function update(host, params = {}) {
  mounted.get(host)?.openCard(params.tag ?? null);
}

export function mount(host, params = {}) {
  // --- Structure (construite avant tout appel au serveur) ----------------------------------
  const layout = element("div", "models-layout");
  layout.dataset.fiche = "false";
  const notice = element("p", "models-notice");
  notice.setAttribute("role", "status");
  const problem = document.createElement("wl-error");
  const loading = element("p", "help", t("models.loading"));
  loading.setAttribute("role", "status");
  const down = element("p", "help models-down", t("models.ollama_down"));
  down.hidden = true;

  const input = element("input", "models-input");
  input.type = "text";
  input.id = "models-install-name";
  input.autocomplete = "off";
  input.spellcheck = false;
  input.setAttribute("aria-describedby", "models-install-help models-install-reason");
  const label = element("label", "", t("models.actions.install_label"));
  label.htmlFor = input.id;
  const installButton = element("button", "btn models-install-named", t("models.actions.install"));
  installButton.type = "submit";
  installButton.setAttribute("aria-label", t("models.actions.install_aria"));
  const help = element("p", "help", t("models.actions.install_help"));
  help.id = "models-install-help";
  const reason = element("p", "help models-reason");
  reason.id = "models-install-reason";
  reason.hidden = true;
  const form = element("form", "models-install-form");
  form.noValidate = true;
  form.append(label, input, installButton);
  const memory = element("p", "help models-memory");
  memory.hidden = true;
  const panel = element("div", "models-pull-panel");
  panel.hidden = true;
  const actions = element("section", "models-actions");
  actions.setAttribute("aria-label", t("models.actions.title"));

  // --- Textes d'état, installés, défauts, déchargement, suppression --------------------------
  const say = (text) => {
    notice.textContent = text;
  };
  const setProblem = (envelope) => {
    problem.error = envelope;
  };
  const nameOf = (tag) =>
    catalog?.find(tag)?.name ??
    installedModels.find((model) => baseTag(model.tag) === baseTag(tag))?.name ??
    defaults.nameOf(tag);
  let installedModels = [];
  let ollamaUp = true;
  let catalog = null; // créé après `pull` (le tableau lit l'installation en cours)
  let rerank = null; // idem : la section du reranker lit l'installation en cours
  let card = null; // idem : la fiche lit l'installation en cours

  const defaults = createDefaults({ say, allowCloud: () => store.get().allowCloud });
  const unload = createUnload({ say, onProblem: setProblem, nameOf });
  const deleter = createDeleter({
    say,
    onProblem: setProblem,
    usagesOf: defaults.usagesOf,
    onDone: async () => {
      await load();
      host.querySelector("#models-installed-title")?.focus(); // la ligne supprimée n'existe plus
    },
  });
  const installed = createInstalled({ onDelete: deleter.ask, ollamaUp: () => ollamaUp });
  actions.append(unload.el, form, help, reason, panel, memory);

  // --- Installation -------------------------------------------------------------------------
  let inCatalogWhileBusy = true; // l'installation en cours avait sa ligne au catalogue

  const pull = createPull({
    host,
    nameOf,
    say,
    onChange: () => onChange(),
    onEnded: ({ status }) => {
      if (status === "ok") {
        load(); // le registre est relu avant `run_ended` : le modèle y est
        card?.reload(); // la fiche ouverte dit « installé »
      }
    },
    onProblem: (envelope) => {
      problem.error = envelope ?? {
        code: "pull_failed",
        message: t("models.pull.start_failed"),
        action: t("models.pull.start_failed_action"),
      };
    },
  });
  catalog = createCatalog({
    pull,
    ollamaUp: () => ollamaUp,
    onInstall: (tag) => install(tag),
  });
  rerank = createRerank({
    pull,
    onInstall: (model) => {
      problem.error = null;
      pull.start(model, { reranker: true });
    },
  });

  card = createCard({
    onInstall: (tag) => install(tag),
    blockedReason: () => blockedReason(),
    onChange: () => {
      installed.refresh(); // `aria-current` du lien de la fiche ouverte
      catalog.render();
      layout.dataset.fiche = String(card.tag !== null);
    },
  });

  // Pourquoi « Installer » est désactivé : une installation en cours, ou Ollama muet.
  function blockedReason() {
    if (pull.busy) return t("models.actions.install_busy", { tag: pull.activeTag ?? "…" });
    return ollamaUp ? null : t("models.actions.install_ollama_down");
  }

  let lastReason = null;

  function onChange() {
    // Le flux système peut rejoindre une installation dès la création.
    if (catalog === null || rerank === null || card === null) return;
    catalog.render();
    rerank.render();
    const tag = pull.activeTag;
    if (pull.busy) inCatalogWhileBusy = tag !== null && catalog.find(tag) !== null;
    // Hors du catalogue (nom saisi), la progression, l'échec ou « Installé » sont sous la barre ; ceux du
    // reranker sont dans sa section.
    const parts = [];
    if (pull.busy) {
      if (!inCatalogWhileBusy && !pull.activeReranker) parts.push(pull.progress.el);
    } else if (pull.failedTag !== null && !pull.failedReranker && !catalog.find(pull.failedTag)) {
      parts.push(pull.failureNode);
    } else if (pull.doneTag !== null && !pull.doneReranker && !inCatalogWhileBusy) {
      parts.push(pull.doneNode);
    }
    panel.replaceChildren(...parts);
    panel.hidden = parts.length === 0;
    const why = blockedReason();
    if (why !== lastReason) {
      lastReason = why;
      card.refresh(); // le bouton « Installer » de la fiche suit
    }
    reason.hidden = why === null;
    reason.textContent = why ?? "";
    installButton.setAttribute("aria-disabled", String(why !== null));
  }

  function install(tag) {
    problem.error = null;
    const known = installedModels.find((model) => baseTag(model.tag) === baseTag(tag));
    if (known) {
      say(t("models.pull.already", { name: known.name }));
      return;
    }
    pull.start(tag);
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (installButton.getAttribute("aria-disabled") === "true") return;
    const tag = input.value.trim();
    if (!tag) {
      say(t("models.actions.install_empty"));
      input.focus();
      return;
    }
    install(tag);
  });

  // --- Lecture des listes -------------------------------------------------------------------
  let loadedOnce = false;
  let reading = null;
  let readAgain = false;

  // Une lecture à la fois ; une demande arrivée pendant la lecture en déclenche une de plus (la
  // lecture en cours peut dater d'avant la fin d'une installation) et son appelant l'attend.
  async function load() {
    if (reading) {
      readAgain = true;
      return reading;
    }
    reading = (async () => {
      do {
        readAgain = false;
        await read();
      } while (readAgain);
      reading = null;
    })();
    return reading;
  }

  // L'état du reranker vient des réglages de la base documentaire ; son échec ne casse pas les listes.
  let rerankReads = 0;
  async function readRerank() {
    const mine = ++rerankReads; // la dernière lecture lancée gagne
    try {
      const value = (await api.ragSettings()).reranker ?? null;
      if (mine === rerankReads) rerank.setSettings(value);
    } catch {
      if (mine === rerankReads) rerank.setUnknown();
    }
  }

  async function read() {
    await shellReady(); // AD-15 : rien de `/api/` avant que la coquille soit rendue
    try {
      const allowCloud = store.get().allowCloud;
      const [list, installable] = await Promise.all([
        api.models(allowCloud),
        api.installableModels(),
      ]);
      // « Sur ce poste » ne montre que les modèles de ce poste ; les défauts nomment aussi le cloud.
      installedModels = list.models.filter((model) => model.origin === "local");
      ollamaUp = list.ollama_up;
      loadedOnce = true;
      if (problem.error?.code === "list_failed") problem.error = null;
      installed.setModels(installedModels);
      catalog.setData(installable);
      await defaults.load(list.models);
      readRerank(); // hors de la lecture des listes : sa lenteur ne les retient pas
    } catch (failure) {
      problem.error =
        failure instanceof ApiError && failure.envelope
          ? failure.envelope
          : {
              code: "list_failed",
              message: t("models.list_failed"),
              action: t("models.list_failed_action"),
            };
    } finally {
      loading.hidden = loadedOnce || problem.error !== null;
      down.hidden = ollamaUp;
      onChange();
    }
  }

  // La mémoire libre du poste, lue sur le flux système (la même que la barre haute).
  function renderMemory(state) {
    const value = state.system.memory;
    memory.hidden = !value;
    if (!value) return;
    memory.textContent = t("models.actions.free", {
      free: formatGb(value.available_gb),
      total: formatGb(value.total_gb),
    });
  }
  const unsubscribeMemory = store.subscribe(renderMemory);
  // Le cloud autorisé ou coupé change les noms et les défauts affichés : relecture.
  const unsubscribeCloud = store.subscribe((state, previous) => {
    if (state.allowCloud !== previous.allowCloud) load();
  });
  renderMemory(store.get());

  // Ollama s'arrête ou revient : les boutons suivent le flux système sans relire les listes.
  const unsubscribeOllama = store.select(
    (state) => (state.ollama.known ? state.ollama.up : null),
    (up) => {
      if (up === null) return;
      ollamaUp = up;
      down.hidden = up;
      installed.refresh();
      onChange();
    },
  );

  // La fiche (panneau) et le reste de l'écran : à droite dès 1 120 px, au-dessus en deçà (D-40).
  const main = element("div", "models-main");
  // Ordre de la maquette (DECISIONS.md §6, story 9.9) : le reranker d'abord (pas de défilement
  // pour l'atteindre), puis « Sur ce poste », le catalogue, et les défauts en dernier.
  main.append(
    actions,
    notice,
    problem,
    down,
    loading,
    rerank.el,
    installed.el,
    catalog.el,
    defaults.el,
    deleter.el,
  );
  layout.append(card.el, main);
  host.replaceChildren(
    moduleTitle("deployed-code", "models", t("screens.models")),
    element("p", "lead", t("models.lead")),
    layout,
  );
  mounted.set(host, { openCard: (tag) => card.open(tag) });
  if (params.tag) card.open(params.tag);

  // --- Écran masqué puis revu ---------------------------------------------------------------
  let wasHidden = host.hidden;
  const visibility = new MutationObserver(() => {
    if (host.hidden === wasHidden) return;
    wasHidden = host.hidden;
    pull.setHidden(wasHidden);
    if (!wasHidden) load();
  });
  visibility.observe(host, { attributes: true, attributeFilter: ["hidden"] });

  onChange();
  load();

  return () => {
    visibility.disconnect();
    mounted.delete(host);
    unsubscribeMemory();
    unsubscribeCloud();
    unsubscribeOllama();
    unload.dispose();
    installed.dispose();
    pull.dispose();
  };
}
