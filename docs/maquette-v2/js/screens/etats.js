// Catalogue des états communs, `#/maquette/etats` (page propre à la maquette, hors navigation) :
// chaque composant de js/components/states.js dans chacun de ses états, et chaque code d'erreur
// d'UX-DR16 (donnees/erreurs.json) avec son message, son action et ses détails techniques. Sert de
// référence aux agents d'écran et de banc d'essai axe pour tous les états.

import { element } from "../core/dom.js";
import { errorCodes, errorSpec } from "../core/errors.js";
import { t } from "../core/i18n.js";

let view = null;

function item(title, ...nodes) {
  const root = element("article", "states-item");
  root.append(element("h3", "", title), ...nodes);
  return root;
}

function section(title, id, items) {
  const root = element("section", "home-section");
  root.setAttribute("aria-labelledby", id);
  const heading = element("h2", "", title);
  heading.id = id;
  const grid = element("div", "states-grid");
  grid.append(...items);
  root.append(heading, grid);
  return root;
}

export function mount(host, ctx) {
  const s = ctx.states;
  const result = element("div", "states-result");

  async function askEmpty() {
    const ok = await s.confirmAction({
      title: t("etats.vider.title"),
      consequence: t("etats.vider.consequence"),
      confirmLabel: t("etats.vider.confirm"),
    });
    result.replaceChildren(ok ? s.notice(t("etats.vider.done"), { tone: "success" }) : s.notice(t("etats.vider.cancelled")));
  }

  async function askEmail() {
    const ok = await s.confirmEmail({
      to: "direction@ombrelune.example",
      subject: "Synthèse des ventes fictives du trimestre",
      body: "Bonjour,\n\nVoici la synthèse préparée par l'agent : les ventes fictives progressent de 4 % sur le trimestre.\n\nCordialement",
    });
    result.replaceChildren(s.notice(t(ok ? "states.email.sent" : "states.email.cancelled"), { tone: ok ? "success" : "info" }));
  }

  const emptyButton = element("button", "btn", t("etats.vider.open"));
  emptyButton.type = "button";
  emptyButton.addEventListener("click", askEmpty);
  const emailButton = element("button", "btn", t("etats.email_open"));
  emailButton.type = "button";
  emailButton.addEventListener("click", askEmail);

  const errors = errorCodes().map((code) => {
    const spec = errorSpec(code);
    const reason = spec.reasons?.[1];
    return item(
      `${code}${spec.ux_dr16 ? "" : t("etats.not_uxdr16")} · ${spec.where}`,
      s.errorBox(code, { vars: reason ? { reason } : {} }),
    );
  });

  host.replaceChildren(
    element("h1", "", ctx.route.title),
    element("p", "lead", t("etats.lead")),
    section(t("etats.general"), "etats-general", [
      item(t("etats.empty"), s.emptyState({ title: t("etats.empty_title"), text: t("etats.empty_text"), action: { label: t("etats.empty_action"), href: "#/documents/base" } })),
      item(t("etats.loading"), s.loading({ lines: 3, slowAfterMs: 1500 })),
      item(t("etats.notices"), s.notice(t("etats.notice_info")), s.notice(t("etats.notice_success"), { tone: "success" }), s.notice(t("etats.notice_warning"), { tone: "warning" })),
      item(t("etats.joined"), s.joinedNotice()),
    ]),
    section(t("etats.runs"), "etats-runs", [
      ...["starting", "loading", "generating", "stopping", "ok", "cancelled", "error", "interrupted"].map((stage, index) =>
        item(t(`components.run_status.${stage}`), s.runStatus(stage, 3 + index * 7)),
      ),
    ]),
    section(t("etats.values"), "etats-values", [
      item(t("etats.score"), s.scoreValue(72), s.scoreValue(null, "juge indisponible"), s.scoreValue(null, "réponse vide")),
      item(
        t("etats.co2"),
        s.co2Value({ mg: 1.8, method: "codecarbon", estimated: false, range_mg: null }),
        s.co2Value({ mg: 0.9, method: "ecologits", estimated: true, range_mg: { low: 0.6, high: 1.4 } }),
        s.co2Value({ mg: null, method: "unmeasurable", reason: "Anthropic ne publie pas la taille de ce modèle : son empreinte ne peut pas être calculée." }),
      ),
      item(t("etats.cloud"), s.cloudGuard()),
      item(t("etats.ram"), s.ramGuardBox({ needed_gb: 5.2, free_gb: 2.8, suggested_model: "gemma4:1b" })),
      item(t("etats.dialogs"), emptyButton, emailButton, result),
    ]),
    section(t("etats.errors"), "etats-errors", errors),
  );

  view = { askEmpty, askEmail };
  return () => {
    view = null;
    host.replaceChildren();
  };
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 50));

export const scenarios = [
  {
    id: "confirmation-vider",
    label: "Ouvrir la confirmation de « Vider la base documentaire »",
    async run() {
      view.askEmpty();
      await settle();
    },
  },
  {
    id: "validation-email",
    label: "Ouvrir la validation d'un email préparé par l'agent",
    async run() {
      view.askEmail();
      await settle();
    },
  },
  {
    id: "cloud-active",
    label: "Activer le cloud (le garde-fou cloud le confirme)",
    async run(ctx) {
      ctx.store.set({ allowCloud: true });
      await settle();
    },
  },
];
