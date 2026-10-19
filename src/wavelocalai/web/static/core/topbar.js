// Barre haute (UX-DR5) : pastille Ollama et son panneau, interrupteur « Autoriser le cloud »,
// CO2 de session et son panneau, bandeaux « Connexion au serveur perdue » et « Le serveur a
// redémarré ». Le HTML porte la structure ; ce module la met à jour depuis le store, sans jamais
// recréer un bouton (le focus ne bouge pas toutes les 2 s). Tous les chiffres viennent de l'API,
// mis en forme par `core/format.js`.

import { findScreen } from "./registry.js";
import { setIcon } from "./dom.js";
import { bindDisclosure } from "./disclosure.js";
import { co2Group, formatCo2, formatGb, formatInteger, formatUnknown } from "./format.js";
import { t } from "./i18n.js";
import { store } from "./store.js";

const byId = (id) => document.getElementById(id);

// État affiché de la pastille Ollama : checking (pas encore de mesure), up, down, unknown (le
// serveur ne répond plus : l'état d'Ollama n'est plus connu).
function ollamaKey(state) {
  if (state.connection.status === "lost") return "unknown";
  if (!state.ollama.known) return "checking";
  return state.ollama.up ? "up" : "down";
}

function ollamaLabel(key) {
  if (key === "up") return t("topbar.ollama.up");
  if (key === "down") return t("topbar.ollama.down");
  if (key === "unknown") return t("topbar.ollama.unknown");
  return t("topbar.ollama.checking");
}

function ollamaState(key) {
  if (key === "up") return t("topbar.ollama.state_up");
  if (key === "down") return t("topbar.ollama.state_down");
  return formatUnknown();
}

const OLLAMA_ICONS = { up: "check", down: "error", checking: "help", unknown: "help" };

function renderOllama(state, parts) {
  const key = ollamaKey(state);
  parts.button.dataset.state = key;
  setIcon(parts.icon, OLLAMA_ICONS[key]);
  parts.label.textContent = ollamaLabel(key);

  parts.state.textContent = ollamaState(key);
  parts.version.textContent =
    key === "up" && state.ollama.version ? state.ollama.version : t("topbar.ollama.version_unknown");
  const memory = state.system.memory;
  parts.memory.textContent = memory
    ? t("topbar.ollama.memory_value", {
        used: formatGb(memory.used_gb),
        total: formatGb(memory.total_gb),
      })
    : formatUnknown();
  // Mémoire libre pour un nouveau modèle : celle que le garde-fou compare au besoin (story 4.8).
  parts.memoryFree.textContent =
    typeof memory?.available_gb === "number" ? formatGb(memory.available_gb) : formatUnknown();

  const items = [];
  const loaded = state.system.modelsLoaded;
  if (key === "up" && Array.isArray(loaded)) {
    if (loaded.length === 0) items.push(t("topbar.ollama.none_loaded"));
    for (const model of loaded) {
      items.push(t("topbar.ollama.loaded_item", { tag: model.tag, size: formatGb(model.size_gb) }));
    }
  } else {
    items.push(formatUnknown());
  }
  parts.loaded.replaceChildren(
    ...items.map((text) => {
      const li = document.createElement("li");
      li.textContent = text;
      return li;
    }),
  );

  // Même enveloppe que l'API (AD-18) ; les textes sont ceux de `errors.py`, recopiés dans fr.json.
  parts.error.error =
    key === "down"
      ? {
          code: "ollama_down",
          message: t("errors.ollama_down.message"),
          action: t("errors.ollama_down.action"),
          detail: null,
        }
      : null;

  const checking = state.ollamaChecking;
  parts.retry.setAttribute("aria-disabled", String(checking));
  parts.retry.textContent = checking ? t("topbar.ollama.retrying") : t("topbar.ollama.retry");
}

function setupOllama(getSystem) {
  const parts = {
    button: byId("ollama-button"),
    icon: byId("ollama-button").querySelector("svg"),
    label: byId("ollama-label"),
    state: byId("ollama-state"),
    version: byId("ollama-version"),
    memory: byId("ollama-memory"),
    memoryFree: byId("ollama-memory-free"),
    loaded: byId("ollama-loaded"),
    error: byId("ollama-error"),
    retry: byId("ollama-retry"),
  };
  bindDisclosure({ button: parts.button, panel: byId("ollama-panel"), scope: byId("ollama-tool") });
  parts.retry.addEventListener("click", () => {
    if (parts.retry.getAttribute("aria-disabled") !== "true") getSystem()?.recheck();
  });
  store.subscribe((state) => renderOllama(state, parts));
  renderOllama(store.get(), parts);
}

function unmeasurableText(count) {
  if (count === 0) return t("topbar.co2.unmeasurable_none");
  if (count === 1) return t("topbar.co2.unmeasurable_one");
  return t("topbar.co2.unmeasurable_many", { count: formatInteger(count) });
}

// Le cloud est toujours une estimation (ecologits) : « 0,9 mg (estimé) », ou « non mesurable » quand
// aucune de ses réponses n'a de mesure. Jamais 0 pour un inconnu ; 0 seulement sans réponse cloud.
function cloudText(cloud, group) {
  const runs = cloud?.runs ?? 0;
  const measured = runs - (cloud?.unmeasurable_runs ?? 0);
  if (runs > 0 && measured <= 0) return t("topbar.co2.cloud_unmeasurable");
  const value = group.format(cloud?.mg ?? 0);
  return measured > 0 ? t("topbar.co2.cloud_estimated", { value }) : value;
}

function renderCarbon(carbon, parts) {
  if (!carbon) {
    parts.value.hidden = true;
    for (const dd of [parts.total, parts.local, parts.cloud, parts.unmeasurable]) {
      dd.textContent = formatUnknown();
    }
    return;
  }
  const local = carbon.by_origin?.local?.mg ?? 0;
  const cloud = carbon.by_origin?.cloud?.mg ?? 0;
  const group = co2Group([carbon.total_mg, local, cloud]);
  parts.value.hidden = false;
  parts.value.textContent = formatCo2(carbon.total_mg);
  parts.total.textContent = group.format(carbon.total_mg);
  parts.local.textContent = group.format(local);
  parts.cloud.textContent = cloudText(carbon.by_origin?.cloud, group);
  parts.unmeasurable.textContent = unmeasurableText(carbon.unmeasurable_runs ?? 0);
}

// Le lien vers Sobriété n'est actif que si l'écran existe (registre) ; sinon il est désactivé, avec
// sa raison visible, comme les modules à venir de la barre de navigation. Appelable de nouveau
// quand le registre change.
export function bindSobrietyLink() {
  const link = byId("co2-link");
  const reason = byId("co2-link-reason");
  const found = findScreen("/sobriete");
  if (found && found.screen.status === "available") {
    link.setAttribute("href", "#/sobriete");
    for (const name of ["role", "aria-disabled", "tabindex", "aria-describedby"]) {
      link.removeAttribute(name);
    }
    reason.hidden = true;
    return;
  }
  link.removeAttribute("href");
  link.setAttribute("role", "link");
  link.setAttribute("aria-disabled", "true");
  link.setAttribute("tabindex", "0");
  reason.textContent = t("router.planned");
  reason.hidden = false;
  link.setAttribute("aria-describedby", reason.id);
}

function setupCarbon() {
  const parts = {
    value: byId("co2-value"),
    total: byId("co2-total"),
    local: byId("co2-local"),
    cloud: byId("co2-cloud"),
    unmeasurable: byId("co2-unmeasurable"),
  };
  bindDisclosure({ button: byId("co2-button"), panel: byId("co2-panel"), scope: byId("co2-tool") });
  bindSobrietyLink();
  byId("co2-link").addEventListener("click", (event) => {
    if (event.currentTarget.getAttribute("aria-disabled") === "true") event.preventDefault();
  });
  store.select(
    (state) => state.carbon,
    (carbon) => renderCarbon(carbon, parts),
  );
}

function setupCloud() {
  const input = byId("cloud-switch");
  bindDisclosure({
    button: byId("cloud-help-button"),
    panel: byId("cloud-help"),
    scope: byId("cloud-tool"),
  });
  // La bascule vit dans le store seulement (AD-20) : ni `localStorage`, ni serveur.
  input.addEventListener("change", () => store.set({ allowCloud: input.checked }));
  const footer = byId("footer-text");
  store.select(
    (state) => state.allowCloud,
    (allowed) => {
      input.checked = allowed;
      footer.textContent = allowed ? t("shell.footer_cloud") : t("shell.footer");
    },
  );
}

function setupBanners(announce) {
  const lost = byId("connection-banner");
  const restarted = byId("restart-banner");
  store.select(
    (state) => state.connection.status === "lost",
    (isLost) => {
      const wasShown = !lost.hidden;
      lost.hidden = !isLost;
      if (isLost) announce(t("topbar.connection.lost"));
      else if (wasShown) announce(t("topbar.connection.restored"));
    },
  );
  store.select(
    (state) => state.serverRestarted,
    (value) => {
      restarted.hidden = !value;
      if (value) announce(t("topbar.restarted.message"));
    },
  );
  byId("restart-reload").addEventListener("click", () => location.reload());
}

// Annonce polie des changements d'état qui comptent (Ollama disponible ou non, connexion).
function makeAnnouncer() {
  const region = byId("status-announcer");
  return (text) => {
    region.textContent = "";
    requestAnimationFrame(() => {
      region.textContent = text;
    });
  };
}

// `getSystem()` rend le contrôleur de `core/system.js` (démarré après le premier rendu).
export function initTopbar(getSystem) {
  const announce = makeAnnouncer();
  setupOllama(getSystem);
  setupCarbon();
  setupCloud();
  setupBanners(announce);
  let previous = ollamaKey(store.get());
  store.subscribe((state) => {
    const key = ollamaKey(state);
    if (key === previous) return;
    const was = previous;
    previous = key;
    // Pas d'annonce pour la première mesure : seul un changement d'état connu est une nouvelle.
    if (was !== "checking" && (key === "up" || key === "down")) announce(ollamaLabel(key));
  });
}
