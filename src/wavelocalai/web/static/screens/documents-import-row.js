// Une ligne par fichier de l'import en cours, pour la Base documentaire (UX-DR22) : nœuds créés une
// fois, mis à jour sur place (le focus et la lecture d'écran ne repartent pas à chaque événement).
// L'annulation n'est pas ici : un seul « Annuler l'import » pour le lot, au-dessus des lignes (D-25).

import { element } from "../core/dom.js";
import { formatInteger } from "../core/format.js";
import { t } from "../core/i18n.js";

export const FINAL = new Set(["ready", "duplicate", "failed", "cancelled", "interrupted"]);

export const plural = (base, n, vars = {}) =>
  t(`${base}_${n < 2 ? "one" : "other"}`, { n: formatInteger(n), ...vars });

function failureMessage(error) {
  // « Le fichier n'a pas pu être indexé : <raison>. » (l'enveloppe fournit le message et la raison).
  const base = String(error?.message ?? t("docs.failed_default")).replace(/[.\s]+$/, "");
  const reason = error?.detail?.reason;
  return reason ? t("docs.failed_with", { message: base, reason }) : `${base}.`;
}

function failureEnvelope(error) {
  const technical = error?.detail?.technical;
  const reason = error?.detail?.reason;
  return {
    code: error?.code ?? "ingest_failed",
    message: failureMessage(error),
    action: error?.action,
    detail: technical && technical !== reason ? { technical } : null,
  };
}

export class ImportRow {
  constructor(key, name) {
    this.key = key;
    this.name = name;
    this.state = "waiting";
    this.listed = false; // le document de ce fichier figure dans la liste du serveur
    this.uploaded = false; // l'envoi du navigateur est terminé (ligne née de cet écran)
    this.percent = 0;
    this.done = 0;
    this.total = 0;
    this.chunks = 0;
    this.error = null;
    this.el = element("li", "docs-import");
    this.title = element("p", "docs-import-name", name);
    this.line = element("p", "docs-import-state");
    this.bar = element("progress", "docs-import-progress");
    this.bar.max = 100;
    this.bar.setAttribute("aria-label", t("docs.row_progress", { file: name }));
    this.failure = document.createElement("wl-error");
    this.el.append(this.title, this.line, this.bar, this.failure);
    this.render();
  }

  get final() {
    return FINAL.has(this.state);
  }

  trail() {
    const parts = [];
    if (this.uploaded) parts.push(t("docs.row_sent"));
    if (this.state === "waiting") parts.push(t("docs.row_waiting"));
    if (this.state === "extract") parts.push(t("docs.row_extract"));
    if (this.state === "split" || this.state === "embed") parts.push(t("docs.row_split"));
    if (this.state === "embed") {
      parts.push(
        t("docs.row_embed", { done: formatInteger(this.done), total: formatInteger(this.total) }),
      );
    }
    return parts.join(" · ");
  }

  text() {
    switch (this.state) {
      case "uploading":
        return t("docs.row_sending", { percent: formatInteger(Math.round(this.percent)) });
      case "ready":
        return plural("docs.row_done", this.chunks);
      case "duplicate":
        return t("docs.row_duplicate");
      case "cancelled":
        return t("docs.row_cancelled");
      case "interrupted":
        return t("docs.row_interrupted");
      case "failed":
        return "";
      default:
        return this.trail();
    }
  }

  render() {
    this.el.dataset.state = this.state;
    this.line.textContent = this.text();
    this.line.hidden = this.state === "failed";
    this.failure.error = this.state === "failed" ? failureEnvelope(this.error) : null;
    const active = !this.final;
    this.bar.hidden = !active;
    if (this.state === "uploading") this.bar.value = this.percent;
    else if (this.state === "embed" && this.total > 0) this.bar.value = (100 * this.done) / this.total;
    else this.bar.removeAttribute("value"); // progression indéterminée
  }
}
