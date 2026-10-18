// Routeur par `hash` (UX-DR4, AD-20) : liens profonds, bouton Précédent, aucune configuration
// serveur. Un écran est un module ES qui exporte `mount(host, params)` et rend sa fonction
// `unmount` ; il est chargé par `import()` à la première visite, puis gardé en mémoire (son nœud
// est masqué, non détruit) : revenir sur un écran est instantané.
//
// À chaque route : `document.title` vaut « <Écran> · WaveLocalAI », le focus va sur le `h1` de
// l'écran et une annonce polie le dit. Une route inconnue ou `planned` renvoie à l'Accueil.
// Au chargement de la page, le focus reste en tête (lien d'évitement, puis navigation).

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

export function createRouter({ main, announcer, onRoute = () => {} }) {
  const entries = new Map(); // id d'écran -> { host, module, mounted, key, unmount }
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
      if (entry.mounted && entry.key !== key) {
        await entry.unmount?.();
        entry.host.replaceChildren();
        entry.mounted = false;
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
    if (path === null) return;
    const focus = !first;
    first = false;
    const found = findScreen(path);
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
