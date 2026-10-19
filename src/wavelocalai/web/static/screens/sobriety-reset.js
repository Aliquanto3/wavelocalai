// Sobriété, « Remettre le compteur à zéro » (story 5.2, AD-10, AD-13, décision n° 16 du 2026-10-19) :
// l'action de l'en-tête de la section « Empreinte carbone de cette session ». Un clic ouvre une
// nouvelle session par `POST /api/carbon/session/reset`, sans confirmation : rien n'est effacé, la
// session close reste dans l'historique.
//
// - Session vide (aucune réponse comptée, mesurée ou non) : le bouton est désactivé et la raison
//   est écrite dessous, jamais en infobulle seule. Tant que la session n'est pas lue, la raison le
//   dit aussi.
// - Le total repart de 0 : la réponse de la route (la nouvelle session, somme nulle) est écrite dans
//   le store, sans attendre `carbon_updated` (le flux peut être en pause, onglet masqué). La fin de
//   l'action est annoncée en `polite` (seules les fins d'action le sont), puis le focus passe au titre
//   de la section : le bouton, désactivé, ne peut pas le garder.
// - Un échec garde le bouton actif et dit, dans la même zone, le message du serveur puis son action ;
//   le compteur ne bouge pas. Le CO2 de session ne baisse jamais par un effacement (AD-13) : la remise à zéro ouvre
//   une session, elle n'en supprime aucune.

import { api, ApiError } from "../core/api.js";
import { element } from "../core/dom.js";
import { t } from "../core/i18n.js";
import { store } from "../core/store.js";
import { sessionIsEmpty } from "./sobriety-carbon.js";
import { setText } from "./sobriety-health.js";

export function buildReset({ onDone }) {
  const button = element("button", "btn sob-reset-button", t("sobriety.reset.label"));
  button.type = "button";
  const why = element("p", "help sob-reset-why");
  why.id = "sob-reset-why";
  button.setAttribute("aria-describedby", why.id);
  const status = element("p", "sob-reset-status");
  status.setAttribute("role", "status");
  const root = element("div", "sob-reset");
  root.append(button, why, status);

  let busy = false;
  let done = false; // le message affiché est « Compteur remis à zéro » (et non une erreur)

  function render(state) {
    const carbon = state.carbon;
    const reason = busy
      ? t("sobriety.reset.busy")
      : !carbon
        ? t("sobriety.reset.loading")
        : sessionIsEmpty(carbon)
          ? t("sobriety.reset.nothing")
          : "";
    const disabled = reason !== "";
    if (button.disabled !== disabled) button.disabled = disabled;
    setText(why, reason);
    why.hidden = !disabled;
    // La session a de nouveau des réponses : le message de la remise à zéro n'a plus lieu d'être.
    if (done && carbon && !sessionIsEmpty(carbon)) {
      done = false;
      setText(status, "");
    }
  }

  button.addEventListener("click", async () => {
    if (busy || button.disabled) return;
    busy = true;
    done = false;
    setText(status, "");
    render(store.get());
    try {
      const fresh = await api.resetCarbonSession();
      store.set({ carbon: fresh });
      done = true;
      setText(status, t("sobriety.reset.done"));
      onDone();
    } catch (failure) {
      const envelope = failure instanceof ApiError ? failure.envelope : null;
      setText(
        status,
        envelope ? `${envelope.message} ${envelope.action ?? ""}`.trim() : t("sobriety.reset.failed"),
      );
    } finally {
      busy = false;
      render(store.get());
    }
  });

  return { root, render };
}
