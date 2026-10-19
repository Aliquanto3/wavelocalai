// Écran Modèles, `#/modeles` (UX-DR27, AD-5, AD-6, AD-15, AD-17, AD-20) : les modèles de ce poste, ce
// qui tient en mémoire, et l'installation d'un modèle avec sa progression chiffrée.
//
// Cette story (5.3) livre la barre « Installer un modèle par son nom », « Sur ce poste » et le
// « Catalogue installable ». Les suivantes ajoutent chacune leur section à `sections` : « Décharger »
// et la suppression (5.4), les modèles par défaut (5.4), le reranker (5.5), la fiche d'un modèle
// (5.6). Un fichier par bloc : `models-installed.js`, `models-catalog.js`, `models-pull.js`.
//
// - Aucun appel d'API avant le repère `shell-ready` (AD-15) ; la page se construit avant.
// - Le front ne calcule rien (AD-20) : `fits`, la mémoire nécessaire et celle qui manque viennent
//   du serveur (`hardware/`) ; le débit est la médiane des runs de ce poste.
// - L'écran reste en mémoire quand on va ailleurs : masqué, le flux de l'installation se ferme en
//   gardant son `seq` ; de retour, il reprend par `?after=` et les listes se relisent.
// - Seule la fin d'une installation est annoncée (zone polie), jamais chaque pourcentage.

import { api, ApiError } from "../core/api.js";
import { element } from "../core/dom.js";
import { formatGb } from "../core/format.js";
import { t } from "../core/i18n.js";
import { shellReady } from "../core/shell-ready.js";
import { store } from "../core/store.js";
import "../components/index.js";
import { createCatalog } from "./models-catalog.js";
import { createInstalled } from "./models-installed.js";
import { createPull } from "./models-pull.js";

const baseTag = (tag) => tag.replace(/:latest$/, "");

export function mount(host) {
  // --- Structure (construite avant tout appel au serveur) ----------------------------------
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
  actions.append(form, help, reason, panel, memory);

  const installed = createInstalled();
  let catalog = null; // créé après `pull` (le tableau lit l'installation en cours)

  // --- Installation -------------------------------------------------------------------------
  const say = (text) => {
    notice.textContent = text;
  };
  const nameOf = (tag) =>
    catalog?.find(tag)?.name ??
    installedModels.find((model) => baseTag(model.tag) === baseTag(tag))?.name ??
    tag;
  let installedModels = [];
  let ollamaUp = true;
  let inCatalogWhileBusy = true; // l'installation en cours avait sa ligne au catalogue

  const pull = createPull({
    host,
    nameOf,
    say,
    onChange: () => onChange(),
    onEnded: ({ status }) => {
      if (status === "ok") load(); // le registre est relu avant `run_ended` : le modèle y est
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

  // Pourquoi « Installer » est désactivé : une installation en cours, ou Ollama muet.
  function blockedReason() {
    if (pull.busy) return t("models.actions.install_busy", { tag: pull.activeTag ?? "…" });
    return ollamaUp ? null : t("models.actions.install_ollama_down");
  }

  function onChange() {
    if (catalog === null) return; // le flux système peut rejoindre une installation dès la création
    catalog.render();
    const tag = pull.activeTag;
    if (pull.busy) inCatalogWhileBusy = tag !== null && catalog.find(tag) !== null;
    // Hors du catalogue (nom saisi), la progression, l'échec ou « Installé » sont sous la barre.
    const parts = [];
    if (pull.busy) {
      if (!inCatalogWhileBusy) parts.push(pull.progress.el);
    } else if (pull.failedTag !== null && !catalog.find(pull.failedTag)) {
      parts.push(pull.failureNode);
    } else if (pull.doneTag !== null && !inCatalogWhileBusy) {
      parts.push(pull.doneNode);
    }
    panel.replaceChildren(...parts);
    panel.hidden = parts.length === 0;
    const why = blockedReason();
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

  async function read() {
    await shellReady(); // AD-15 : rien de `/api/` avant que la coquille soit rendue
    try {
      const [list, installable] = await Promise.all([api.models(false), api.installableModels()]);
      installedModels = list.models;
      ollamaUp = list.ollama_up;
      loadedOnce = true;
      if (problem.error?.code === "list_failed") problem.error = null;
      installed.setModels(list.models);
      catalog.setData(installable);
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
  renderMemory(store.get());

  // Ollama s'arrête ou revient : les boutons suivent le flux système sans relire les listes.
  const unsubscribeOllama = store.select(
    (state) => (state.ollama.known ? state.ollama.up : null),
    (up) => {
      if (up === null) return;
      ollamaUp = up;
      down.hidden = up;
      onChange();
    },
  );

  host.replaceChildren(
    element("h1", "", t("screens.models")),
    element("p", "lead", t("models.lead")),
    actions,
    notice,
    problem,
    down,
    loading,
    installed.el,
    catalog.el,
  );

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
    unsubscribeMemory();
    unsubscribeOllama();
    installed.dispose();
    pull.dispose();
  };
}
