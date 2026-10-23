// <wl-error> : affichage d'erreur unique (UX-DR16, AD-18). `el.error = {code, message, action,
// detail}` (l'enveloppe de l'API, telle quelle) affiche `message`, puis `action`, et `detail`
// replié sous « Détails techniques ». Le front n'invente ni message ni code. Sans Shadow DOM.
// L'attribut `alert` ajoute `role="alert"` (erreur qui surgit pendant que l'utilisateur agit).
//
// Garde-fou mémoire (`ram_guard`, story 4.8) : l'enveloppe porte `detail.needed_gb`, `free_gb` et
// `suggested_model`, dont le composant tire ses deux boutons ; il ne calcule rien. Tout écran qui
// affiche un `wl-error` reçoit donc le garde-fou sans code de plus :
// - « Prendre un modèle plus petit » (si le serveur propose un modèle) émet `wl-use-model`
//   (bubbles, `detail.model` : le tag de `suggested_model`) ; l'écran le choisit dans son
//   `wl-model-picker` sans relancer ;
// - « Décharger les modèles inactifs » appelle `POST /api/models/unload` et dit le résultat sous
//   les boutons ; la mémoire libre se met à jour par le flux système.

import { api, ApiError } from "../core/api.js";
import { element } from "../core/dom.js";
import { formatGb } from "../core/format.js";
import { t } from "../core/i18n.js";

// Les textes du catalogue citent les commandes entre accents graves (`ollama serve`) : rendues
// en `<code>`, jamais telles quelles.
function richText(tag, className, text) {
  const node = element(tag, className);
  const parts = String(text ?? "").split("`");
  parts.forEach((part, index) => {
    if (!part) return;
    const code = index % 2 === 1 && index < parts.length - 1;
    node.append(code ? element("code", "", part) : document.createTextNode(part));
  });
  return node;
}

function detailText(detail) {
  if (detail === null || detail === undefined) return "";
  if (typeof detail === "string") return detail;
  const { technical, ...machine } = detail;
  const lines = [];
  if (technical) lines.push(String(technical));
  for (const [key, value] of Object.entries(machine)) lines.push(`${key} : ${JSON.stringify(value)}`);
  return lines.join("\n");
}

function unloadSummary(report) {
  const lines = [];
  lines.push(
    report.unloaded.length
      ? t("components.error.unloaded", {
          models: report.unloaded.join(", "),
          free: formatGb(report.free_gb),
        })
      : t("components.error.unload_none", { free: formatGb(report.free_gb) }),
  );
  if (report.kept.length) {
    lines.push(t("components.error.unload_kept", { models: report.kept.map((m) => m.tag).join(", ") }));
  }
  if (report.failed.length) {
    lines.push(t("components.error.unload_failed", { models: report.failed.join(", ") }));
  }
  return lines.join(" ");
}

export class WlError extends HTMLElement {
  #error = null;

  get error() {
    return this.#error;
  }

  set error(value) {
    this.#error = value ?? null;
    if (this.isConnected) this.render();
  }

  // Les deux actions du garde-fou mémoire (UX-DR16) ; rien d'autre n'a de bouton ici. Le résultat
  // du déchargement s'écrit dans une zone `role="status"` déjà présente, sans refaire le rendu :
  // le bouton garde son focus et la lecture d'écran annonce le texte.
  #ramGuardActions(detail) {
    const buttons = element("div", "wl-error-buttons");
    const suggested = typeof detail?.suggested_model === "string" ? detail.suggested_model : "";
    if (suggested) {
      const smaller = element("button", "btn", t("components.error.ram_guard_smaller"));
      smaller.type = "button";
      smaller.addEventListener("click", () => {
        this.dispatchEvent(
          new CustomEvent("wl-use-model", { bubbles: true, detail: { model: suggested } }),
        );
      });
      buttons.append(smaller);
    }
    const unload = element("button", "btn", t("components.error.ram_guard_unload"));
    unload.type = "button";
    const result = element("p", "wl-error-result");
    result.setAttribute("role", "status");
    result.hidden = true;
    unload.addEventListener("click", () => this.#unloadIdle(unload, result));
    buttons.append(unload);
    const help = element(
      "p",
      "wl-error-help",
      suggested
        ? t("components.error.ram_guard_suggested", { model: suggested })
        : t("components.error.ram_guard_none"),
    );
    return [buttons, help, result];
  }

  async #unloadIdle(button, result) {
    if (button.disabled) return;
    const error = this.#error;
    const say = (text) => {
      if (this.#error !== error) return; // une autre erreur est affichée entre-temps
      result.textContent = text;
      result.hidden = false;
    };
    const focused = document.activeElement === button; // désactivé, il perd le focus
    button.disabled = true;
    say(t("components.error.unloading"));
    try {
      say(unloadSummary(await api.unloadModels()));
    } catch (failure) {
      say(
        failure instanceof ApiError && failure.envelope
          ? failure.envelope.message
          : t("components.error.unload_failed_generic"),
      );
    } finally {
      button.disabled = false;
      if (focused) button.focus();
    }
  }

  connectedCallback() {
    this.render();
  }

  render() {
    const error = this.#error;
    this.className = "wl-error";
    if (this.hasAttribute("alert")) this.setAttribute("role", "alert");
    if (!error) {
      this.replaceChildren();
      this.hidden = true;
      return;
    }
    this.hidden = false;
    this.dataset.code = error.code ?? "";
    const parts = [richText("p", "wl-error-message", error.message)];
    if (error.action) parts.push(richText("p", "wl-error-action", error.action));
    if (error.code === "ram_guard") parts.push(...this.#ramGuardActions(error.detail));
    const technical = detailText(error.detail);
    if (technical) {
      const details = element("details", "wl-error-details");
      details.append(
        element("summary", "", t("components.error.details")),
        element("pre", "wl-error-technical", technical),
      );
      parts.push(details);
    }
    this.replaceChildren(...parts);
  }
}

if (!customElements.get("wl-error")) customElements.define("wl-error", WlError);
