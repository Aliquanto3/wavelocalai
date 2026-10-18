// Routeur par `hash` (repris de static/core/router.js, UX-DR4, AD-20), piloté par donnees/routes.json.
//
// - Une route = `{slug, path, title, module, screen?, tab?, example?}` ; `path` peut porter un
//   paramètre `:nom` (`/arene/comparer/:run_id`). L'écran est le module `js/screens/<screen>.js`
//   (`screen` vaut `slug` par défaut), chargé par `import()` à la première visite avec sa feuille
//   `css/screens/<screen>.css` et ses textes `i18n/screens/<screen>.fr.json`.
// - Un écran exporte `mount(host, ctx)` (AD-20 ; `render` est accepté comme alias), qui rend sa
//   fonction de démontage, et `scenarios` (voir CONVENTIONS.md). Il est gardé en mémoire : son
//   nœud est masqué, non détruit. Un changement de paramètre le remonte.
// - À chaque route : `document.title` « <Écran> · WaveLocalAI », focus sur le `h1`, annonce polie.
//   Route inconnue : retour à l'Accueil, sans entrée de plus dans l'historique.

import { loadScreenTexts, t } from "./i18n.js";

const HOME = "/";
const CSS_ROOT = new URL("../../css/screens/", import.meta.url);

export function pathFromHash(hash) {
  if (hash === "" || hash === "#") return HOME;
  if (!hash.startsWith("#/")) return null;
  const path = hash.slice(1).split("?")[0];
  return path.length > 1 ? path.replace(/\/+$/, "") || HOME : HOME;
}

function compile(route) {
  const names = [];
  const source = route.path
    .split("/")
    .map((part) => {
      if (!part.startsWith(":")) return part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      names.push(part.slice(1));
      return "([^/]+)";
    })
    .join("/");
  return { ...route, screen: route.screen ?? route.slug, names, regex: new RegExp(`^${source}$`) };
}

export function matchRoute(routes, path) {
  for (const route of routes) {
    const found = route.regex.exec(path);
    if (!found) continue;
    try {
      const params = Object.fromEntries(route.names.map((name, i) => [name, decodeURIComponent(found[i + 1])]));
      return { route, params };
    } catch {
      return null;
    }
  }
  return null;
}

function loadCss(screen) {
  return new Promise((resolve) => {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = new URL(`${screen}.css`, CSS_ROOT).href;
    link.dataset.screen = screen;
    link.onload = link.onerror = () => resolve();
    document.head.append(link);
  });
}

// `makeContext(route, params, host, entry)` fabrique le `ctx` passé à `mount` (voir main.js).
export function createRouter({ main, announcer, routes, makeContext, onRoute = () => {} }) {
  const compiled = routes.map(compile);
  const entries = new Map(); // écran -> { host, module, mounted, key, unmount, ctx }
  let token = 0;
  let first = true;
  let current = null;
  const waiters = []; // `navigate()` en attente de la route affichée

  function announce(text) {
    announcer.textContent = "";
    requestAnimationFrame(() => {
      announcer.textContent = text;
    });
  }

  function entryFor(screen) {
    let entry = entries.get(screen);
    if (!entry) {
      const host = document.createElement("section");
      host.className = "screen";
      host.dataset.screen = screen;
      host.hidden = true;
      main.append(host);
      entry = { host, module: null, mounted: false, key: "", unmount: null, ctx: null };
      entries.set(screen, entry);
    }
    return entry;
  }

  async function loadModule(screen) {
    const [module] = await Promise.all([
      import(`../screens/${screen}.js`),
      loadCss(screen),
      loadScreenTexts(screen),
    ]);
    return module;
  }

  function showError(entry, route, error) {
    const h1 = document.createElement("h1");
    h1.textContent = route.title;
    const message = document.createElement("p");
    message.setAttribute("role", "alert");
    message.textContent = t("router.load_failed");
    const detail = document.createElement("pre");
    detail.className = "help";
    detail.textContent = String(error);
    entry.host.replaceChildren(h1, message, detail);
    entry.mounted = false;
  }

  async function mountEntry(entry, route, params) {
    const mount = entry.module.mount ?? entry.module.render;
    entry.ctx = makeContext(route, params, entry.host, { remount: () => remount(route.screen) });
    const result = await mount(entry.host, entry.ctx);
    entry.unmount = typeof result === "function" ? result : (result?.unmount ?? null);
    entry.mounted = true;
  }

  async function unmountEntry(entry) {
    await entry.unmount?.();
    entry.host.replaceChildren();
    entry.mounted = false;
  }

  // Démonte puis remonte l'écran courant (scénarios : repartir d'un état propre).
  async function remount(screen) {
    const entry = entries.get(screen);
    if (!entry || !current || current.route.screen !== screen) return;
    await unmountEntry(entry);
    await mountEntry(entry, current.route, current.params);
  }

  async function show(route, params, { focus, reason }) {
    const mine = ++token;
    const entry = entryFor(route.screen);
    const key = JSON.stringify({ slug: route.slug, params });
    try {
      entry.module ??= await loadModule(route.screen);
      if (mine !== token) return;
      if (entry.mounted && entry.key !== key) await unmountEntry(entry);
      if (!entry.mounted) {
        await mountEntry(entry, route, params);
        entry.key = key;
      }
    } catch (error) {
      console.error(`Écran ${route.screen} : échec du chargement`, error);
      showError(entry, route, error);
    }
    if (mine !== token) return;

    for (const other of entries.values()) other.host.hidden = other !== entry;
    current = { route, params, entry };
    document.title = t("router.title", { screen: route.title });
    const spoken = t("router.announce", { screen: route.title });
    announce(reason ? `${reason} ${spoken}` : spoken);
    if (focus) {
      const h1 = entry.host.querySelector("h1");
      if (h1) {
        h1.setAttribute("tabindex", "-1");
        h1.focus({ preventScroll: true });
      }
      window.scrollTo(0, 0);
    }
    onRoute(current);
    for (const done of waiters.splice(0)) done(current);
  }

  async function resolve() {
    const path = pathFromHash(location.hash);
    if (path === null && !first) return;
    const focus = !first;
    first = false;
    const found = path === null ? null : matchRoute(compiled, path);
    if (found) {
      await show(found.route, found.params, { focus });
      return;
    }
    const home = matchRoute(compiled, HOME);
    history.replaceState(null, "", "#/");
    await show(home.route, home.params, { focus, reason: path ? t("router.unknown") : null });
  }

  return {
    routes: compiled,
    start() {
      addEventListener("hashchange", resolve);
      return resolve();
    },
    current: () => current,
    module: (screen) => entries.get(screen)?.module ?? null,
    remount,
    navigate(path) {
      const target = `#${path}`;
      if (location.hash === target) return resolve().then(() => current);
      return new Promise((done) => {
        waiters.push(done);
        location.hash = target;
      });
    },
  };
}
