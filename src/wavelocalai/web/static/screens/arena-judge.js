// Notation de l'Arène (story 3.3, UX-DR20, AD-9) : le panneau replié « Critères de notation » (le juge
// et ses critères, envoyés avec la commande) et le résumé du juge retenu, publié par le serveur dans
// l'événement `judge` (badge Local ou Cloud, « un seul juge », avertissement « note peu fiable »).
//
// Le front ne décide rien : le juge par défaut est le défaut `judge` du serveur (le sélecteur le
// propose), le cloud n'y figure que si « Autoriser le cloud » est actif (le sélecteur le garantit),
// la fiabilité vient de l'événement `judge`. Les critères sont du texte libre : toujours posés par
// `textContent`, au plus 8 de 64 caractères (le serveur refuse au-delà).

import { element, icon } from "../core/dom.js";
import { t } from "../core/i18n.js";
import { reasonText } from "../components/wl-arena-lane.js";

export const MAX_CRITERIA = 8;
export const MAX_CRITERION_CHARS = 64;
const MAX_ANNOUNCED = 4; // une note par colonne au plus : les plus anciennes sortent
const DEFAULT_KEYS = ["accuracy", "relevance", "clarity"];

const defaultCriteria = () => DEFAULT_KEYS.map((key) => t(`arena.judge.defaults.${key}`));

function badge(kind) {
  const node = document.createElement("wl-badge");
  node.setAttribute("kind", ["local", "cloud"].includes(kind) ? kind : "unknown");
  return node;
}

// Les critères envoyés : sans vides ni doublons, au plus 8 de 64 caractères.
export function cleanCriteria(items) {
  const seen = new Set();
  const out = [];
  for (const item of items) {
    const text = String(item ?? "").trim().slice(0, MAX_CRITERION_CHARS);
    const key = text.toLocaleLowerCase("fr-FR");
    if (!text || seen.has(key)) continue;
    seen.add(key);
    out.push(text);
  }
  return out.slice(0, MAX_CRITERIA);
}

// Le panneau replié : sélecteur du juge (défaut `judge`), son badge, puis la liste des critères.
export function judgePanel(uid) {
  const picker = document.createElement("wl-model-picker");
  picker.setAttribute("purpose", "judge");
  picker.setAttribute("label", t("arena.judge.label"));

  const current = element("p", "arena-judge-current");
  current.hidden = true;
  const help = element("p", "help", `${t("arena.judge.help")} ${t("arena.judge.weak_help")}`);

  const legend = element("legend", "", t("arena.judge.criteria_legend"));
  const list = element("ul", "arena-criteria-list");
  const add = element("button", "btn arena-criteria-add", t("arena.judge.add"));
  add.type = "button";
  add.id = `${uid}-criteria-add`;
  const reset = element("button", "btn arena-criteria-reset", t("arena.judge.reset"));
  reset.type = "button";
  const note = element("p", "help arena-criteria-help");
  note.id = `${uid}-criteria-help`;
  add.setAttribute("aria-describedby", note.id);
  const actions = element("div", "arena-criteria-actions");
  actions.append(add, reset);
  const criteriaSet = element("fieldset", "arena-criteria");
  criteriaSet.append(legend, list, actions, note);

  const summary = element("summary", "arena-judge-summary", t("arena.judge.panel"));
  const body = element("div", "arena-judge-body");
  body.append(picker, current, help, criteriaSet);
  const el = element("details", "arena-judge-panel");
  el.append(summary, body);

  let items = defaultCriteria();

  function renderNote() {
    const full = items.length >= MAX_CRITERIA;
    add.disabled = full;
    note.textContent = full
      ? t("arena.judge.criteria_full")
      : t("arena.judge.criteria_help", {
          max: MAX_CRITERIA,
          chars: MAX_CRITERION_CHARS,
          defaults: defaultCriteria().join(", "),
        });
  }

  function renderList(focus = null) {
    list.replaceChildren(
      ...items.map((text, index) => {
        const n = index + 1;
        const input = element("input", "chat-input arena-criterion-input");
        input.type = "text";
        input.maxLength = MAX_CRITERION_CHARS;
        input.value = text;
        input.autocomplete = "off";
        input.setAttribute("aria-label", t("arena.judge.criterion_label", { n }));
        input.addEventListener("input", () => {
          items[index] = input.value;
        });
        input.addEventListener("keydown", (event) => {
          // Entrée n'envoie pas le formulaire : elle ajoute un critère après celui-ci.
          if (event.key !== "Enter") return;
          event.preventDefault();
          addAfter(index);
        });
        const remove = element("button", "btn arena-criterion-remove");
        remove.type = "button";
        remove.setAttribute("aria-label", t("arena.judge.criterion_remove", { n }));
        remove.append(icon("close"));
        remove.addEventListener("click", () => {
          items.splice(index, 1);
          renderList({ index: Math.min(index, items.length - 1) });
        });
        const row = element("li", "arena-criterion");
        row.append(input, remove);
        return row;
      }),
    );
    renderNote();
    if (focus) {
      const target = list.querySelectorAll("input")[focus.index];
      (target ?? add).focus();
    }
  }

  function addAfter(index) {
    if (items.length >= MAX_CRITERIA) return;
    items.splice(index + 1, 0, "");
    renderList({ index: index + 1 });
  }

  add.addEventListener("click", () => addAfter(items.length - 1));
  reset.addEventListener("click", () => {
    items = defaultCriteria();
    renderList({ index: 0 });
  });

  // Le juge retenu : son nom et son badge Local ou Cloud, sous le sélecteur.
  function renderCurrent() {
    const fiche = picker.value ? picker.modelFor(picker.value) : null;
    current.hidden = !picker.value;
    if (!picker.value) {
      current.replaceChildren();
      return;
    }
    current.replaceChildren(
      t("arena.judge.current", { name: fiche?.name ?? picker.value }),
      " ",
      badge(fiche?.origin),
    );
  }
  picker.addEventListener("wl-model-change", renderCurrent);

  renderList();
  return {
    el,
    picker,
    judge: () => picker.value,
    // Le juge choisi : { name, origin }, ou `null` (le résumé le dit avant l'événement `judge`).
    chosen() {
      const fiche = picker.value ? picker.modelFor(picker.value) : null;
      return picker.value ? { name: fiche?.name ?? picker.value, origin: fiche?.origin } : null;
    },
    criteria: () => cleanCriteria(items),
  };
}

// Le résumé du juge retenu, sous la question posée : rempli par l'événement `judge`.
export function judgeInfo() {
  const el = element("div", "arena-judge-info");
  el.hidden = true;
  let shown = false;
  let held = false; // le résumé de la comparaison en cours dit déjà le juge (D-16)
  const sync = () => {
    el.hidden = held || !shown;
  };

  function alertLine(iconName, text) {
    const line = element("p", "arena-judge-alert");
    line.setAttribute("role", "status");
    line.append(icon(iconName), element("span", "", text));
    return line;
  }

  return {
    el,
    clear() {
      shown = false;
      sync();
      el.replaceChildren();
    },
    // Masqué tant que le résumé est affiché, revu à la fin du run.
    hold(on) {
      held = on;
      sync();
    },
    // `data` : l'événement `judge` ; `name` : le nom du juge ; `criteria` : ceux de la question.
    show(data, { name, criteria }) {
      const parts = [];
      if (!data?.model) {
        parts.push(alertLine("warning", t("arena.judge.none_alert")));
      } else {
        const who = element("p", "arena-judge-who");
        who.append(t("arena.judge.info_judge", { name }), " ", badge(data.origin));
        if (data.single_judge) {
          const single = document.createElement("wl-badge");
          single.setAttribute("kind", "single-judge");
          who.append(" ", single);
        }
        const used = criteria.length ? criteria : (data.default_criteria ?? []);
        parts.push(who, element("p", "help", t("arena.judge.info_criteria", { list: used.join(", ") })));
        if (data.unreliable) parts.push(alertLine("warning", t("arena.judge.unreliable_alert")));
      }
      el.replaceChildren(...parts);
      shown = true;
      sync();
    },
  };
}

// Les notes arrivent l'une après l'autre : chacune est ajoutée à une zone d'annonce polie
// (`aria-atomic=false`), aucune n'écrase l'autre.
export function scoreAnnouncer() {
  const el = element("div", "sr-only");
  el.setAttribute("role", "status");
  el.setAttribute("aria-live", "polite");
  el.setAttribute("aria-atomic", "false");
  return {
    el,
    clear: () => el.replaceChildren(),
    // `result` : { score, reason } de la colonne ; `unreliable` : la note vient d'un petit juge.
    add(name, { score, reason }, unreliable) {
      const line =
        score === null
          ? t("arena.announce.not_evaluated", {
              name,
              reason: reasonText(reason).toLocaleLowerCase("fr-FR"),
            })
          : t(unreliable ? "arena.announce.score_unreliable" : "arena.announce.score", { name, score });
      el.append(element("p", "", line));
      while (el.children.length > MAX_ANNOUNCED) el.firstElementChild.remove();
    },
  };
}
