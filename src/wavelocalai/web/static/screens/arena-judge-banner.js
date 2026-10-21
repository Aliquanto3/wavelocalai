// Bandeau du juge de l'Arène, au-dessus des colonnes (story 9.3, maquette `docs/maquette-v2-mise-en-
// page/index.html`, `.judge-banner` : refonte visuelle complète en 9.7, classe reprise telle quelle
// ici). Un seul modèle d'état, d'où le texte et l'horloge sont tirés à chaque événement :
//
//   pas de juge          « Comparaison sans juge… », sans compteur ni horloge
//   juge en panne        « Juge indisponible… » (dernière note « juge indisponible », aucune phase
//                        `loading`/`scoring` ni note réussie depuis), sans compteur, horloge arrêtée
//   aucune colonne au travail  « Juge : X · en attente des réponses » (génération en cours, ou
//                        colonnes en file pour la place locale), puis « notation terminée » à la fin
//   une colonne au travail     « Juge : X · chargement » (phase `loading`), ou « Notation n sur N ·
//                        colonne » (`scoring`)
//   plusieurs à la fois  juge cloud, sans place locale : « Notation : k notées sur N · m en cours »,
//                        chaque colonne dit elle-même « Notation en cours »
//
// L'horloge (temps écoulé de la phase en cours, remis à zéro à chaque colonne et au chargement) est
// un élément à part, `aria-hidden`, hors de la région live : celle-ci n'annonce que les étapes. Un
// seul minuteur, actif seulement tant qu'une colonne est chargée ou notée ; `end()` et `reset()`
// l'arrêtent (fin du run, nouvelle comparaison, démontage de l'écran).
//
//   const banner = judgeBannerView();
//   banner.el                      à placer au-dessus des colonnes
//   banner.setJudge(data, name)    l'événement `judge` ({ model }) et le nom affiché du juge
//   banner.progress(data, nameOf)  l'événement `judge_progress` ; `nameOf(tag)` : nom d'une colonne
//   banner.score(data)             l'événement `judge_score`
//   banner.end()                   fin du run (ou flux perdu) : plus rien ne tourne
//   banner.reset()                 nouvelle comparaison, ou écran démonté
//   banner.ticking                 vrai tant que le minuteur tourne (tests)

import { element, icon } from "../core/dom.js";
import { formatClock } from "../core/format.js";
import { t } from "../core/i18n.js";

const TICK_MS = 1000;
// Raison d'un `judge_score` dont le juge n'a pas répondu : `NOT_EVALUATED_UNAVAILABLE` du serveur
// (`inference/judge_port.py`, égalité vérifiée par `tests/v2/unit/test_arena_judge_banner_static.py`).
export const JUDGE_UNAVAILABLE = "non évalué : juge indisponible";
const WORKING = new Set(["loading", "scoring"]);

function fresh() {
  // `active` : colonnes chez le juge, tag -> { phase, position, lane, since } ; `scored` : notes
  // rendues pour des colonnes passées au juge (`seen`), réussies ou non.
  return {
    known: false,
    hasJudge: false,
    name: "",
    down: false,
    ended: false,
    total: 0,
    scored: 0,
    active: new Map(),
    seen: new Set(),
  };
}

export function judgeBannerView() {
  const el = element("div", "judge-banner arena-judge-banner");
  el.hidden = true;
  const textEl = element("span", "arena-judge-banner-text");
  textEl.setAttribute("role", "status");
  textEl.setAttribute("aria-live", "polite");
  const clockEl = element("span", "arena-judge-banner-clock");
  clockEl.setAttribute("aria-hidden", "true");
  el.append(icon("gavel"), textEl, clockEl);

  let state = fresh();
  let timer = null;

  const working = () => [...state.active.values()].filter(({ phase }) => WORKING.has(phase));

  function text(busy) {
    if (!state.hasJudge) return t("arena.judge.banner_none");
    if (state.down) return t("arena.judge.banner_down");
    const { name, total, scored } = state;
    if (busy.length > 1) return t("arena.judge.banner_parallel", { done: scored, total, count: busy.length });
    if (busy.length === 1) {
      const [{ phase, position, lane }] = busy;
      if (phase === "loading") return t("arena.judge.banner_loading", { name });
      return t("arena.judge.banner_scoring", { position, total, lane });
    }
    return t(state.ended ? "arena.judge.banner_done" : "arena.judge.banner_waiting", { name });
  }

  function renderClock(busy = working()) {
    const since = Math.min(...busy.map((entry) => entry.since));
    clockEl.textContent = busy.length ? formatClock(Math.max(0, (Date.now() - since) / 1000)) : "";
  }

  function stopTimer() {
    clearInterval(timer);
    timer = null;
  }

  function render() {
    el.hidden = !state.known;
    const busy = state.hasJudge && !state.down && !state.ended ? working() : [];
    const value = state.known ? text(busy) : "";
    if (textEl.textContent !== value) textEl.textContent = value; // la région ne parle qu'aux étapes
    renderClock(busy);
    if (busy.length === 0) stopTimer();
    else timer ??= setInterval(() => renderClock(), TICK_MS);
  }

  return {
    el,
    get ticking() {
      return timer !== null;
    },
    setJudge(data, name) {
      state = { ...fresh(), known: true, hasJudge: Boolean(data?.model), name: name || "" };
      render();
    },
    progress(data, nameOf) {
      const tag = data?.lane;
      if (!state.hasJudge || state.ended || typeof tag !== "string") return;
      const previous = state.active.get(tag);
      const asked = WORKING.has(data.phase) ? data.phase : "queued";
      // Une colonne ne recule jamais : un `queued` tardif ne la sort pas de la notation.
      const phase = WORKING.has(previous?.phase) && asked === "queued" ? previous.phase : asked;
      const since = previous?.phase === phase ? previous.since : Date.now(); // par phase et par colonne
      state.active.set(tag, { phase, position: data.position, lane: nameOf(tag) ?? tag, since });
      state.seen.add(tag);
      if (Number.isInteger(data.total)) state.total = data.total;
      if (WORKING.has(phase)) state.down = false; // le juge répond de nouveau
      render();
    },
    score(data) {
      const tag = data?.lane;
      if (!state.hasJudge || !state.seen.has(tag)) return; // réponse vide : le juge n'y était pas
      state.active.delete(tag);
      state.scored += 1;
      if (typeof data?.score === "number") state.down = false;
      else if (data?.reason === JUDGE_UNAVAILABLE) state.down = true;
      render();
    },
    end() {
      state.ended = true;
      state.active.clear();
      render();
    },
    reset() {
      state = fresh();
      render();
    },
  };
}
