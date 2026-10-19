// Actions sur une comparaison terminée (story 3.6, UX-DR21, AD-13, D-3) : « Relancer », « Modifier la
// question », l'export (CSV et Markdown) et « Effacer la comparaison ».
//
//   const actions = actionsView(uid);   actions.el  actions.ready(runId, snapshot)  actions.reset()
//
// - Elle ne s'arme qu'une fois l'instantané du run lu (`arena-results.js`, à `run_ended`). « Relancer »
//   et « Modifier la question » reprennent la configuration (`snapshot.config` : modèles, question,
//   critères, juge) : la vue ne la devine pas, le serveur la rend ; elle demande à l'écran de la
//   reprendre par l'événement `wl-arena-reuse`, qui remonte jusqu'à `arena.js`.
// - L'export suit les routes du serveur (`Content-Disposition: attachment`, jamais de `blob:`) :
//   deux boutons dès 768 px, un menu « Exporter » en dessous (`components/export-menu.js`, D-3).
// - « Effacer » ouvre `wl-confirm-dialog` (focus sur « Annuler ») ; confirmé, le serveur supprime le
//   texte (question, réponses, notes), garde le CO2 au registre carbone, et l'écran se vide
//   (événement `wl-arena-erased`). Le front ne décide pas si l'effacement est permis : un refus
//   (`409 arena_busy`) est affiché tel que le serveur le dit.

import { api, ApiError } from "../core/api.js";
import { element } from "../core/dom.js";
import { t } from "../core/i18n.js";
import { exportMenu } from "../components/export-menu.js";
import "../components/wl-confirm-dialog.js";

// Reprend la configuration d'une comparaison dans le formulaire ; « Relancer » la lance aussitôt (si
// le formulaire le permet : sinon la raison du bouton désactivé reste lisible), « Modifier la
// question » rend le focus à la question.
export function reuseConfig({ mode, config }, { question, picker, judging, launchReason, submit }) {
  question.value = config.prompt;
  picker.values = config.models;
  judging.restore(config);
  question.dispatchEvent(new Event("input")); // brouillon enregistré, raison du lancement recalculée
  if (mode === "rerun" && !launchReason()) {
    submit();
    return;
  }
  question.focus();
  question.scrollIntoView({ block: "center" });
}

export function actionsView(uid) {
  const el = element("div", "arena-run-actions");
  el.setAttribute("role", "group");
  el.setAttribute("aria-label", t("arena.actions.label"));
  el.hidden = true;

  const button = (label, onClick) => {
    const node = element("button", "btn", label);
    node.type = "button";
    node.addEventListener("click", onClick);
    return node;
  };
  const rerun = button(t("arena.actions.rerun"), () => reuse("rerun"));
  const edit = button(t("arena.actions.edit"), () => reuse("edit"));
  const exports = exportMenu({
    items: [
      { label: t("arena.actions.csv"), onClick: () => download("csv") },
      { label: t("arena.actions.markdown"), onClick: () => download("md") },
    ],
  });
  const erase = button(t("arena.actions.erase"), () => confirmErase());
  const dialog = document.createElement("wl-confirm-dialog");
  const problem = element("p", "arena-run-actions-problem");
  problem.id = `${uid}-actions-problem`;
  problem.setAttribute("role", "alert");
  problem.hidden = true;
  el.append(rerun, edit, exports.root, erase, problem, dialog);

  let runId = null;
  let config = null;
  let working = false;

  function sync() {
    const armed = runId !== null && !working;
    el.hidden = runId === null;
    rerun.disabled = !armed || config === null;
    edit.disabled = !armed || config === null;
    erase.disabled = !armed;
    exports.setDisabled(!armed);
  }

  function say(text) {
    problem.textContent = text;
    problem.hidden = text === "";
  }

  function reuse(mode) {
    if (config) el.dispatchEvent(new CustomEvent("wl-arena-reuse", { bubbles: true, detail: { mode, config } }));
  }

  function download(extension) {
    if (runId === null) return;
    const link = element("a");
    link.href = api.arenaExportUrl(runId, extension);
    link.download = "";
    document.body.append(link);
    link.click();
    link.remove();
  }

  // Les boutons restent actifs tant que le dialogue est ouvert : le focus doit pouvoir y revenir
  // (un bouton désactivé le perd). Ils ne se désactivent qu'une fois l'effacement confirmé.
  async function confirmErase() {
    if (runId === null || working) return;
    const id = runId;
    say("");
    const confirmed = await dialog.ask({
      title: t("arena.actions.erase_title"),
      consequence: t("arena.actions.erase_consequence"),
      confirmLabel: t("arena.actions.erase_confirm"),
    });
    if (!confirmed || id !== runId) return;
    working = true;
    sync();
    try {
      await api.deleteArenaRun(id);
      el.dispatchEvent(new CustomEvent("wl-arena-erased", { bubbles: true, detail: { runId: id, prompt: config?.prompt } }));
    } catch (failure) {
      say(failure instanceof ApiError && failure.envelope ? failure.envelope.message : t("arena.actions.erase_failed"));
    } finally {
      working = false;
      sync();
      if (!erase.disabled && !el.hidden && !document.activeElement?.closest?.(".arena-run-actions")) erase.focus();
    }
  }

  return {
    el,
    // `snapshot` : l'instantané du run terminé, ou `null` s'il n'a pas pu être lu (les exports et
    // l'effacement restent offerts, « Relancer » et « Modifier » attendent une configuration).
    ready(id, snapshot) {
      runId = id;
      config = snapshot?.config ?? null;
      say("");
      sync();
    },
    reset() {
      runId = null;
      config = null;
      working = false;
      dialog.close();
      say("");
      sync();
    },
  };
}
