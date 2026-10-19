// Progression d'un téléchargement de modèle (`wl-progress-bytes`, DESIGN.md) : une barre et, à côté,
// le texte « Téléchargement 1,2 Go sur 4,7 Go · 26 % » (jamais la barre seule), puis « Annuler ».
// Nœuds créés une fois et mis à jour sur place : le focus et la lecture d'écran ne repartent pas à
// chaque événement `pull_progress`. Aucun calcul de mesure ici (AD-20) : octets, total, pourcentage
// et phase viennent du serveur ; seul le choix de l'unité (Mo, Go) est de la mise en forme.
// Réutilisé par la récupération du reranker (story 5.5).

import { element } from "../core/dom.js";
import { formatNumber, formatPercent } from "../core/format.js";
import { t } from "../core/i18n.js";

const GIB = 1024 ** 3;
const MIB = 1024 ** 2;

// 812 Mo, 1,2 Go : le Mo sous 0,1 Go, pour qu'un début de téléchargement ne dise pas « 0,0117 Go ».
export function formatSize(bytes) {
  if (bytes < GIB / 10) return t("models.pull.unit_mb", { n: formatNumber(bytes / MIB) });
  return t("models.pull.unit_gb", { n: formatNumber(bytes / GIB) });
}

// Le texte d'une mise à jour `pull_progress` ({phase, received_bytes, total_bytes, percent}).
export function progressText(update) {
  if (update.phase === "verifying") return t("models.pull.verifying");
  if (update.phase === "downloading" && update.total_bytes > 0) {
    return t("models.pull.downloading", {
      received: formatSize(update.received_bytes),
      total: formatSize(update.total_bytes),
      percent: formatPercent(update.percent ?? 0),
    });
  }
  return t("models.pull.starting");
}

export function createProgress({ onCancel }) {
  const el = element("div", "wl-progress-bytes");
  const text = element("p", "wl-progress-text");
  const bar = element("progress", "wl-progress-bar");
  bar.max = 100;
  const cancel = element("button", "btn wl-progress-cancel", t("models.pull.cancel"));
  cancel.type = "button";
  cancel.addEventListener("click", () => {
    if (cancel.getAttribute("aria-disabled") !== "true") onCancel();
  });
  const line = element("div", "wl-progress-line");
  line.append(bar, cancel);
  el.append(text, line);

  return {
    el,
    // `name` : le nom du modèle, pour le nom accessible de la barre et du bouton.
    update(update, name) {
      text.textContent = progressText(update);
      bar.setAttribute("aria-label", t("models.pull.progress_label", { name }));
      cancel.setAttribute("aria-label", t("models.pull.cancel_aria", { name }));
      if (update.percent === null || update.percent === undefined) bar.removeAttribute("value");
      else bar.value = update.percent;
    },
    // Annuler désactivé le temps de l'arrêt : une seule demande à la fois (le focus reste sur lui).
    cancelling(on) {
      cancel.setAttribute("aria-disabled", String(on));
    },
    focusCancel: () => cancel.focus(),
    get cancelButton() {
      return cancel;
    },
  };
}
