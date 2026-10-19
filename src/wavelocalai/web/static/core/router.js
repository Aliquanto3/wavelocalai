// Routeur par `hash` (UX-DR4, AD-20) : liens profonds, bouton Précédent, aucune configuration
// serveur. Un écran est un module ES qui exporte `mount(host, params)` et rend sa fonction
// `unmount`, et facultativement `update(host, params)` quand seul son paramètre de chemin change
// (sinon il est démonté puis remonté) ; il est chargé par `import()` à la première visite, puis gardé en mémoire (son nœud
// est masqué, non détruit) : revenir sur un écran est instantané.
//
// À chaque route : `document.title` vaut « <Écran> · WaveLocalAI », le focus va sur le `h1` de
// l'écran et une annonce polie le dit. Une route inconnue ou `planned` renvoie à l'Accueil.
// Au chargement de la page, le focus reste en tête (lien d'évitement, puis navigation) : décision B16
// de la story 8.2, RGAA 12.7. Le titre et l'annonce polie sont posés dès le premier rendu ; un test
// (`test_accessibilite.py`) garde ce comportement.

import { findScreen } from "./registry.js";
import { t } from "./i18n.js";

const HOME = "/";

// Le chemin d'un hash (`#/arene/chat` -> `/arene/chat`), ou null pour une ancre qui n'est pas
// une route (`#main`) : le routeur n'y touche pas.
export function pathFromHash(hash) {
  if (hash === "" || hash === "#") return HOME;
  if (!hash.startsWith("#/")) return null;
  const path = hash.slice(1).split("?")[0];
  return path.length > 1 ? path.replace(/\/+$/, "") || HOME : HOME;
}

let adopt = () => {}; // posée par `createRouter`

// Réécrit l'adresse sans entrée d'historique ni `hashchange` (`history.replaceState`) et y accorde
// la clé de l'écran monté : un retour par l'historique sur cette adresse ne le remonte pas (revue 8.1b).
export function replaceAddress(hash) {
  history.replaceState(null, "", hash);
  adopt(hash);
}

export function createRouter({ main, announcer, onRoute = () => {} }) {
  const entries = new Map(); // id d'écran -> { host, module, mounted, key, unmount }
  adopt = (hash) => {
    const path = pathFromHash(hash);
    const found = path === null ? null : findScreen(path);
    const entry = found && entries.get(found.screen.id);
    if (entry?.mounted) entry.key = JSON.stringify(found.params);
  };
  let token = 0;
  let first = true;

  function announce(text) {
    // Vider puis remplir : un même texte est de nouveau annoncé.
    announcer.textContent = "";
    requestAnimationFrame(() => {
      announcer.textContent = text;
    });
  }

  function entryFor(screen) {
    let entry = entries.get(screen.id);
    if (!entry) {
      const host = document.createElement("section");
      host.className = "screen";
      host.dataset.screen = screen.id;
      host.hidden = true;
      main.append(host);
      entry = { host, module: null, mounted: false, key: "", unmount: null };
      entries.set(screen.id, entry);
    }
    return entry;
  }

  function showError(entry, screen) {
    entry.host.replaceChildren();
    const h1 = document.createElement("h1");
    h1.textContent = t(`screens.${screen.id}`);
    const message = document.createElement("p");
    message.setAttribute("role", "alert");
    message.textContent = t("router.load_failed");
    entry.host.append(h1, message);
    entry.mounted = false;
  }

  async function show(screen, params, { focus, reason }) {
    const mine = ++token;
    const entry = entryFor(screen);
    const key = JSON.stringify(params);
    try {
      entry.module ??= await screen.load();
      // Route supplantée pendant le chargement : ne pas monter un écran qui ne sera pas montré.
      if (mine !== token) return;
      if (entry.mounted && entry.key !== key) {
        if (typeof entry.module.update === "function") {
          // L'écran suit lui-même le changement de paramètre (la fiche d'un modèle, story 5.6) :
          // il n'est ni démonté ni reconstruit, ses listes et ses installations restent.
          await entry.module.update(entry.host, params);
          entry.key = key;
        } else {
          await entry.unmount?.();
          entry.host.replaceChildren();
          entry.mounted = false;
        }
      }
      if (!entry.mounted) {
        entry.unmount = (await entry.module.mount(entry.host, params)) ?? null;
        entry.mounted = true;
        entry.key = key;
      }
    } catch (error) {
      console.error(`Écran ${screen.id} : échec du chargement`, error);
      showError(entry, screen);
    }
    if (mine !== token) return; // une route plus récente a pris la main

    for (const other of entries.values()) other.host.hidden = other !== entry;
    const name = t(`screens.${screen.id}`);
    document.title = t("router.title", { screen: name });
    const spoken = t("router.announce", { screen: name });
    announce(reason ? t("router.redirected", { reason }) + " " + spoken : spoken);
    if (focus) {
      const h1 = entry.host.querySelector("h1");
      if (h1) {
        h1.setAttribute("tabindex", "-1");
        h1.focus({ preventScroll: true });
      }
      window.scrollTo(0, 0);
    }
    onRoute(screen, params);
  }

  async function resolve() {
    const path = pathFromHash(location.hash);
    // Une ancre qui n'est pas une route (`#main`) est ignorée, sauf au chargement de la page :
    // il faut alors un écran, donc l'Accueil (branche « inconnue » ci-dessous).
    if (path === null && !first) return;
    const focus = !first;
    first = false;
    const found = path === null ? null : findScreen(path);
    if (found && found.screen.status === "available") {
      await show(found.screen, found.params, { focus });
      return;
    }
    // Route inconnue ou à venir : retour à l'Accueil, sans entrée de plus dans l'historique.
    const home = findScreen(HOME);
    history.replaceState(null, "", "#/");
    const reason = found ? t("router.planned") : null;
    await show(home.screen, home.params, { focus, reason });
  }

  return {
    start() {
      addEventListener("hashchange", resolve);
      return resolve();
    },
  };
}
