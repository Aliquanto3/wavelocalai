// Bandeau du juge de l'Arène, au-dessus des colonnes (story 9.3, maquette `docs/maquette-v2-mise-en-
// page/index.html`, `.judge-banner` : refonte visuelle complète en 9.7, classe reprise telle quelle
// ici). Dit le juge retenu pendant son chargement, puis sa progression de notation (`judge_progress`),
// ou qu'il n'y en a pas (ou qu'il est en panne) sans compteur. Région live polie : le texte ne change
// qu'aux étapes (chargement -> N sur Total), jamais par jeton ni par seconde écoulée affichée.
//
//   const banner = judgeBannerView();
//   banner.el                      à placer au-dessus des colonnes
//   banner.setJudge(data, name)    l'événement `judge` ({ model }) et le nom affiché du juge
//   banner.update(data, nameOf)    l'événement `judge_progress` ; `nameOf(tag)` donne le nom d'une colonne
//   banner.scored()                un `judge_score` noté : le juge marche, la panne (s'il y en avait une) est levée
//   banner.unavailable()           un `judge_score` « juge indisponible » avant toute note réussie : panne
//   banner.reset()                 une nouvelle comparaison

import { element, icon } from "../core/dom.js";
import { formatClock } from "../core/format.js";
import { t } from "../core/i18n.js";

const TICK_MS = 1000;

export function judgeBannerView() {
  const el = element("p", "judge-banner arena-judge-banner");
  el.setAttribute("role", "status");
  el.setAttribute("aria-live", "polite");
  el.hidden = true;
  const textEl = element("span", "");
  el.append(icon("gavel"), textEl);
  let judgeName = "";
  let known = false; // `judge` reçu au moins une fois (même sans juge) : le bandeau peut parler
  let hasJudge = false;
  let down = false;
  let succeeded = false; // au moins une note réussie : une panne passée n'est plus affichée
  let scoring = null; // { position, total, lane } pendant la notation de cette colonne
  let startedAt = null;
  let timer = null;

  function stopTimer() {
    clearInterval(timer);
    timer = null;
  }

  function text() {
    if (!hasJudge) return t("arena.judge.banner_none");
    if (down) return t("arena.judge.banner_down");
    if (scoring) {
      const elapsed = startedAt === null ? 0 : Math.max(0, (Date.now() - startedAt) / 1000);
      return t("arena.judge.banner_scoring", { ...scoring, clock: formatClock(elapsed) });
    }
    return t("arena.judge.banner_loading", { name: judgeName });
  }

  function render() {
    el.hidden = !known;
    if (el.hidden) return;
    const value = text();
    if (textEl.textContent !== value) textEl.textContent = value;
  }

  return {
    el,
    setJudge(data, name) {
      known = true;
      hasJudge = Boolean(data?.model);
      judgeName = name || "";
      down = false;
      succeeded = false;
      scoring = null;
      startedAt = null;
      stopTimer();
      render();
    },
    update(data, nameOf) {
      // Les colonnes avancent en parallèle (une attend son tour pendant qu'une autre est notée) :
      // le `queued`/`loading` d'une AUTRE colonne n'efface pas la notation en cours de celle-ci.
      // Seul un nouveau `scoring` (même colonne reprise, ou colonne suivante) remplace l'affichage.
      if (!hasJudge || down || data?.phase !== "scoring") return;
      scoring = { position: data.position, total: data.total, lane: nameOf(data.lane) ?? data.lane };
      startedAt ??= Date.now();
      timer ??= setInterval(render, TICK_MS);
      render();
    },
    scored() {
      succeeded = true;
      down = false;
    },
    unavailable() {
      if (!hasJudge || succeeded) return;
      down = true;
      scoring = null;
      stopTimer();
      render();
    },
    reset() {
      known = false;
      hasJudge = false;
      down = false;
      succeeded = false;
      scoring = null;
      judgeName = "";
      startedAt = null;
      stopTimer();
      el.hidden = true;
      textEl.textContent = "";
    },
  };
}
