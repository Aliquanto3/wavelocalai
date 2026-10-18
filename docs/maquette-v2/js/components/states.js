// États communs (UX-DR16, UX-DR17, 03 §3.8, EXPERIENCE.md « State Patterns ») : fonctions qui
// rendent un nœud prêt à insérer. Les écrans les reçoivent par `ctx.states` (ou les importent).
// Aucune couleur ni texte en dur : jetons de tokens.css, textes de i18n/maquette.fr.json.
//
//   emptyState({title, text, action: {label, onClick, href}, level})      état vide (carte)
//   loading({lines, slowAfterMs, slowText})                                 premier chargement
//   runStatus(stage, seconds)            aperçu figé : starting|loading|generating|stopping|ok|cancelled|error|interrupted
//   errorBox(code, {detail, vars, alert, onAction})                         erreur UX-DR16
//   notice(text, {tone: info|success|warning, role})                        message court
//   joinedNotice()                                                          409 rejoint
//   ollamaGuard()           bandeau « Ollama arrêté » relié au store (masqué si Ollama répond)
//   cloudGuard({model, onAllowed})   cloud désactivé puis activé, relié au store
//   scoreValue(score, reason)        « 72/100 » ou « non évalué » + raison
//   co2Value(co2)                    « 1,8 mg », « 0,9 mg (estimé) » ou « non mesurable » + aide
//   ramGuardBox(detail, onAction)    garde-fou mémoire (raccourci d'errorBox)
//   confirmAction({title, consequence, confirmLabel, cancelLabel, details}) -> Promise<boolean>
//   confirmEmail({to, subject, body, expiryMin}) -> Promise<boolean>   validation d'un email (D2)
//   closeDialog()                    ferme le dialogue de confirmation ouvert (comme « Annuler »)

import { co2Display } from "../core/co2.js";
import { element, icon } from "../core/dom.js";
import { errorEnvelope } from "../core/errors.js";
import { formatScore } from "../core/format.js";
import { t } from "../core/i18n.js";
import { store } from "../core/store.js";
import "./wl-badge.js";
import "./wl-confirm-dialog.js";
import "./wl-error.js";
import "./wl-run-status.js";
import "./wl-skeleton.js";

let counter = 0;
const uid = (prefix) => `${prefix}-${++counter}`;

function actionControl({ label, onClick, href, primary = true }) {
  const control = href ? element("a", "btn", label) : element("button", "btn", label);
  if (primary) control.classList.add("btn-primary");
  if (href) control.href = href;
  else control.type = "button";
  if (onClick) control.addEventListener("click", onClick);
  return control;
}

export function emptyState({ title, text, action = null, level = 2, iconName = "info" } = {}) {
  const root = element("section", "wl-empty");
  const titleId = uid("wl-empty");
  root.setAttribute("aria-labelledby", titleId);
  const heading = element(`h${level}`, "wl-empty-title");
  heading.id = titleId;
  heading.append(icon(iconName), element("span", "", title));
  root.append(heading);
  if (text) root.append(element("p", "wl-empty-text", text));
  if (action) root.append(actionControl(action));
  return root;
}

export function loading({ lines = 3, slowAfterMs = 2500, slowText = "" } = {}) {
  const root = element("div", "wl-loading");
  root.setAttribute("aria-busy", "true");
  const skeleton = document.createElement("wl-skeleton");
  skeleton.setAttribute("lines", String(lines));
  skeleton.setAttribute("slow-after", String(slowAfterMs));
  if (slowText) skeleton.setAttribute("slow-text", slowText);
  root.append(skeleton);
  return root;
}

export function runStatus(stage, seconds = 0) {
  const status = document.createElement("wl-run-status");
  status.setAttribute("driven", "");
  queueMicrotask(() => status.preview(stage, seconds));
  return status;
}

export function errorBox(code, { detail, vars, alert = false, onAction = null } = {}) {
  const box = document.createElement("wl-error");
  if (alert) box.setAttribute("alert", "");
  box.error = errorEnvelope(code, { detail, vars });
  if (onAction) box.addEventListener("wl-error-action", (event) => onAction(event.detail.id, event));
  return box;
}

export function ramGuardBox(detail, onAction) {
  return errorBox("ram_guard", { detail, onAction, alert: true });
}

export function notice(text, { tone = "info", role = "status" } = {}) {
  const node = element("p", `wl-notice wl-notice-${tone}`);
  if (role) node.setAttribute("role", role);
  const icons = { info: "info", success: "check", warning: "warning" };
  node.append(icon(icons[tone] ?? "info"), element("span", "", text));
  return node;
}

export function joinedNotice() {
  return notice(t("states.joined"));
}

// Bandeau en tête de module quand Ollama ne répond pas ; se masque seul quand il revient.
export function ollamaGuard() {
  const box = document.createElement("wl-error");
  box.classList.add("wl-guard");
  const unsubscribe = store.select(
    (state) => `${state.maquette.ollamaDown}|${state.allowCloud}`,
    () => {
      const down = store.get().maquette.ollamaDown;
      box.error = down ? errorEnvelope("ollama_down") : null;
    },
  );
  box.addEventListener("wl-error-action", async (event) => {
    if (event.detail.id === "retry") (await import("../sim/systeme.js")).recheck();
  });
  box.dispose = unsubscribe;
  return box;
}

// Un modèle cloud est choisi : cloud coupé, l'erreur `cloud_not_allowed` et « Autoriser le cloud » ;
// cloud activé, un message bref le confirme. `onAllowed()` est appelé à l'activation.
export function cloudGuard({ onAllowed = () => {}, onUseLocal = () => {} } = {}) {
  const root = element("div", "wl-cloud-guard");
  const box = document.createElement("wl-error");
  const ok = notice(t("states.cloud_allowed"), { tone: "success" });
  root.append(box, ok);
  let wasAllowed = store.get().allowCloud;
  const unsubscribe = store.select(
    (state) => state.allowCloud,
    (allowed) => {
      box.error = allowed ? null : errorEnvelope("cloud_not_allowed");
      ok.hidden = !allowed || wasAllowed;
      if (allowed && !wasAllowed) onAllowed();
      wasAllowed = allowed;
    },
  );
  box.addEventListener("wl-error-action", (event) => {
    if (event.detail.id === "allow_cloud") store.set({ allowCloud: true });
    if (event.detail.id === "use_local") onUseLocal();
  });
  root.dispose = unsubscribe;
  return root;
}

export function scoreValue(score, reason = "") {
  const root = element("span", "wl-score");
  if (typeof score === "number" && Number.isFinite(score)) {
    root.textContent = formatScore(score);
    return root;
  }
  root.dataset.state = "not-evaluated";
  root.append(element("span", "wl-score-value", t("format.not_evaluated")));
  if (reason) root.append(element("span", "wl-score-reason", t("states.not_evaluated_reason", { reason })));
  return root;
}

export function co2Value(co2) {
  const display = co2Display(co2);
  const root = element("span", "wl-co2");
  root.dataset.kind = display.kind;
  root.append(element("span", "wl-co2-value", display.value));
  if (display.help) {
    const help = element("span", "wl-co2-help help", display.help);
    root.append(help);
  }
  return root;
}

function dialogHost() {
  let dialog = document.querySelector("#main > wl-confirm-dialog");
  if (!dialog) {
    dialog = document.createElement("wl-confirm-dialog");
    document.getElementById("main").append(dialog); // dans un repère (règle axe « region »)
  }
  return dialog;
}

export function confirmAction(options) {
  return dialogHost().ask(options);
}

export function closeDialog() {
  document.querySelector("#main > wl-confirm-dialog")?.close();
}

// Validation d'un email (D2) : `expiryMin` ajoute la mention « Sans réponse dans 10 min, l'envoi est
// refusé. » (EXPERIENCE.md). `closeDialog()` ferme le dialogue ouvert comme « Annuler ».
export function confirmEmail({ to, subject, body, expiryMin = 10 }) {
  return dialogHost().ask({
    note: expiryMin ? t("states.email.expiry", { minutes: expiryMin }) : "",
    title: t("states.email.title"),
    consequence: t("states.email.consequence"),
    confirmLabel: t("states.email.confirm"),
    details: [
      { label: t("states.email.to"), value: to },
      { label: t("states.email.subject"), value: subject },
      { label: t("states.email.body"), value: body },
    ],
  });
}
