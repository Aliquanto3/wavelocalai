// <wl-model-picker> : sélecteur de modèle (UX-DR9, AD-8, AD-9, AD-15, AD-20). Combobox WAI-ARIA
// APG « editable combobox with list autocomplete » : un champ de saisie (`role="combobox"`) qui
// filtre une liste (`role="listbox"`), pilotée au clavier (flèches, Entrée, Échap).
//
// - Alimenté par `GET /api/models` et `GET /api/models/defaults` ; la bascule cloud vient du store.
//   Aucun modèle d'embedding ni reranker n'est proposé (seul `kind == "chat"`).
// - Groupes « Sur cette machine » puis « Cloud » (ce dernier seulement si le cloud est autorisé).
//   Règle de tri explicite : dans un groupe, le défaut d'abord, puis les modèles qui tiennent en
//   mémoire, puis ceux dont le besoin est inconnu, puis ceux qui ne tiennent pas, puis le nom.
// - Chaque ligne : nom, badge d'origine (toujours un texte), taille, « tient en mémoire » ou un
//   avertissement (le modèle reste choisissable), débit mesuré s'il existe, pastilles « outils
//   vérifiés », « raisonnement », « MoE n B actifs ». Le front ne calcule rien : `fits`,
//   `needed_gb` et le débit viennent de l'API.
// - Mode `multi` : cases dans la liste, choix en pastilles retirables, un modèle une seule fois.
// - Cloud coupé alors qu'un modèle cloud est choisi : il est retiré, le composant le dit en texte
//   et propose le défaut local.
//
// Attributs : `purpose` (défaut `chat`), `multi`, `label`, `eligible-only` (ne propose que les
// modèles éligibles à l'usage, liste du serveur dans les défauts : un modèle inéligible n'est pas
// proposé plutôt que refusé à l'enregistrement, décision du 2026-10-19). Propriétés : `values` (liste choisie),
// `value` (premier choix, ou ""), `loaded` (la liste est arrivée), `ollamaUp`, `localReadyCount`
// (modèles locaux listés et disponibles, `null` avant la première liste). Événements :
// `wl-model-change` (`detail.values`, le choix change) et `wl-models-loaded` (après chaque
// rechargement de la liste : `selected` peut avoir changé de fiche, par exemple sa créativité par
// défaut). Sans Shadow DOM.

import { api, ApiError } from "../core/api.js";
import { element, icon } from "../core/dom.js";
import { t } from "../core/i18n.js";
import { store } from "../core/store.js";
import { buildOption, matchesQuery } from "./model-picker-option.js";
import "./wl-error.js";

let counter = 0;

const FITS_RANK = (model) => (model.fits === true ? 0 : model.fits == null ? 1 : 2);

export class WlModelPicker extends HTMLElement {
  static observedAttributes = ["purpose", "label", "multi", "eligible-only"];

  #uid = `wl-picker-${++counter}`;
  #known = new Map(); // tag -> modèle (cumulé : savoir l'origine d'un modèle qui disparaît de la liste)
  #models = []; // modèles de conversation de la dernière liste
  #values = [];
  #defaults = null; // { tags, reason } du dernier appel
  #localDefaults = null; // défaut local, quand le cloud est coupé
  #ollamaUp = true;
  #error = null;
  #notice = null; // { removed: [noms], proposal: [tags] }
  #loaded = false;
  #preselected = false;
  #open = false;
  #query = "";
  #active = -1;
  #visible = [];
  #groups = [];
  #token = 0;
  #unsubscribe = null;
  #dom = null;

  connectedCallback() {
    this.#build();
    this.#renderAll();
    this.#unsubscribe = store.select(
      (state) => `${state.allowCloud}|${state.ollama.up}`,
      () => this.reload(),
    );
  }

  disconnectedCallback() {
    this.#unsubscribe?.();
    this.#unsubscribe = null;
    this.#token += 1; // une réponse tardive ne touche plus un composant détaché
  }

  attributeChangedCallback(name, old, value) {
    if (!this.#dom) return;
    this.#renderAll();
    // Autre usage : son défaut et sa raison changent (le choix fait reste).
    if (name === "purpose" && old !== value && this.#unsubscribe) this.reload();
  }

  get multi() {
    return this.hasAttribute("multi");
  }

  get values() {
    return [...this.#values];
  }

  set values(list) {
    const next = [];
    for (const tag of Array.isArray(list) ? list : [list]) {
      if (typeof tag === "string" && tag && !next.includes(tag)) next.push(tag);
    }
    this.#values = this.multi ? next : next.slice(0, 1);
    this.#preselected = true;
    if (this.#dom) this.#renderAll();
  }

  get value() {
    return this.#values[0] ?? "";
  }

  set value(tag) {
    this.values = tag ? [tag] : [];
  }

  get loaded() {
    return this.#loaded;
  }

  get ollamaUp() {
    return this.#ollamaUp;
  }

  // Nombre de modèles locaux prêts (listés, Ollama répond), `null` avant la première liste.
  get localReadyCount() {
    if (!this.#loaded) return null;
    return this.#models.filter((model) => model.origin !== "cloud" && model.available).length;
  }

  // La fiche de l'API du premier modèle choisi (nom, origine…), ou null.
  get selected() {
    return this.#known.get(this.value) ?? null;
  }

  // La fiche de l'API d'un modèle déjà listé, ou null.
  modelFor(tag) {
    return this.#known.get(tag) ?? null;
  }

  // Les fiches de tous les modèles choisis, dans l'ordre du choix (mode multi : l'Arène).
  get selectedModels() {
    return this.#values.map(
      (tag) => this.#known.get(tag) ?? { tag, name: tag, origin: "unknown" },
    );
  }

  // --- Données ------------------------------------------------------------------------------

  async reload() {
    const token = ++this.#token;
    const allowCloud = store.get().allowCloud;
    const purpose = this.getAttribute("purpose") || "chat";
    const [list, defaults] = await Promise.allSettled([
      api.models(allowCloud),
      api.modelDefaults(purpose, allowCloud),
    ]);
    if (token !== this.#token || !this.isConnected) return;

    this.#error = null;
    if (list.status === "fulfilled") {
      this.#ollamaUp = list.value.ollama_up !== false;
      this.#models = list.value.models.filter((model) => model.kind === "chat");
      for (const model of this.#models) this.#known.set(model.tag, model);
      this.#loaded = true;
    } else {
      this.#error = this.#envelope(list.reason);
    }
    this.#defaults = defaults.status === "fulfilled" ? defaults.value : null;
    if (!this.#defaults && !this.#models.length && defaults.status === "rejected" && !this.#error) {
      this.#error = this.#envelope(defaults.reason); // `no_model` : le message dit quoi faire
    }
    if (!allowCloud && this.#defaults) this.#localDefaults = this.#defaults;
    this.#dropCloudChoices(allowCloud);
    this.#preselect();
    this.#renderAll();
    this.dispatchEvent(new CustomEvent("wl-models-loaded", { bubbles: true }));
  }

  #envelope(reason) {
    if (reason instanceof ApiError && reason.envelope) return reason.envelope;
    return { code: "internal", message: t("components.picker.load_failed") };
  }

  // Cloud coupé : un modèle cloud choisi est retiré, dit en texte, et le défaut local est proposé.
  #dropCloudChoices(allowCloud) {
    if (allowCloud) return;
    const removed = this.#values.filter((tag) => this.#known.get(tag)?.origin === "cloud");
    if (!removed.length) return;
    this.#values = this.#values.filter((tag) => !removed.includes(tag));
    const proposal = (this.#localDefaults?.tags ?? []).filter((tag) =>
      this.#models.some((model) => model.tag === tag),
    );
    this.#notice = {
      removed: removed.map((tag) => this.#name(tag)),
      proposal: this.multi ? proposal : proposal.slice(0, 1),
    };
    this.#preselected = true; // on propose, on ne choisit pas à la place de la personne
    this.#emit();
  }

  // Au premier chargement, sans choix de l'appelant : le défaut de l'usage.
  #preselect() {
    if (this.#preselected || this.#values.length || !this.#defaults) return;
    const tags = this.#defaults.tags.filter((tag) => this.#models.some((m) => m.tag === tag));
    if (!tags.length) return;
    this.#values = this.multi ? tags : tags.slice(0, 1);
    this.#preselected = true;
    this.#emit();
  }

  #name(tag) {
    return this.#known.get(tag)?.name ?? tag;
  }

  #emit() {
    this.dispatchEvent(
      new CustomEvent("wl-model-change", { bubbles: true, detail: { values: this.values } }),
    );
  }

  // --- Structure ----------------------------------------------------------------------------

  #build() {
    const id = this.#uid;
    const label = element("label", "wl-picker-label");
    label.htmlFor = `${id}-input`;
    label.id = `${id}-label`;

    const input = element("input", "wl-picker-input");
    input.id = `${id}-input`;
    input.type = "text";
    input.autocomplete = "off";
    input.spellcheck = false;
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-haspopup", "listbox");
    input.setAttribute("aria-controls", `${id}-listbox`);
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-describedby", `${id}-help`);

    const listbox = element("div", "wl-picker-listbox");
    listbox.id = `${id}-listbox`;
    listbox.setAttribute("role", "listbox");
    listbox.setAttribute("aria-labelledby", label.id);
    listbox.hidden = true;

    const empty = element("p", "wl-picker-empty");
    empty.hidden = true;

    const popup = element("div", "wl-picker-popup");
    popup.hidden = true;
    popup.append(listbox, empty);

    const box = element("div", "wl-picker-box");
    box.append(input, popup);

    const help = element("p", "help wl-picker-help");
    help.id = `${id}-help`;

    const chips = element("ul", "wl-picker-chips");
    chips.setAttribute("aria-label", t("components.picker.chosen"));

    const notice = element("div", "wl-picker-notice");
    notice.setAttribute("role", "status");

    const error = document.createElement("wl-error");

    const live = element("div", "sr-only");
    live.setAttribute("role", "status");

    this.className = "wl-picker";
    this.replaceChildren(label, box, help, chips, notice, error, live);
    this.#dom = { label, input, popup, listbox, empty, help, chips, notice, error, live };

    input.addEventListener("input", () => {
      this.#query = input.value;
      this.#setOpen(true);
      this.#active = this.#compute().length ? 0 : -1;
      this.#renderList();
    });
    // Un choix unique est sélectionné dans le champ : la saisie le remplace au lieu de s'y ajouter.
    input.addEventListener("click", () => {
      if (!this.multi && !this.#open) input.select();
      this.#setOpen(true);
    });
    input.addEventListener("keydown", (event) => this.#onKey(event));
    this.addEventListener("focusout", (event) => {
      if (!event.relatedTarget || !this.contains(event.relatedTarget)) this.#setOpen(false);
    });
    // La souris ne prend pas le focus : le champ le garde, la liste ne se ferme pas.
    popup.addEventListener("mousedown", (event) => event.preventDefault());
    listbox.addEventListener("click", (event) => {
      const option = event.target.closest('[role="option"]');
      if (option && option.getAttribute("aria-disabled") !== "true") this.#choose(option.dataset.tag);
    });
    chips.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-tag]");
      if (button) this.#remove(button.dataset.tag);
    });
    notice.addEventListener("click", (event) => {
      if (!event.target.closest("button")) return;
      this.#values = [...(this.#notice?.proposal ?? [])];
      this.#notice = null;
      this.#renderAll();
      this.#emit();
      this.#dom.input.focus();
    });
  }

  // --- Liste affichée -------------------------------------------------------------------------

  #defaultTags() {
    return new Set(this.#defaults?.tags ?? []);
  }

  // Modèles filtrés et ordonnés : « Sur cette machine » d'abord, « Cloud » ensuite.
  #compute() {
    const defaults = this.#defaultTags();
    const order = (a, b) =>
      Number(defaults.has(b.tag)) - Number(defaults.has(a.tag)) ||
      FITS_RANK(a) - FITS_RANK(b) ||
      a.name.localeCompare(b.name, "fr-FR");
    const eligible = this.hasAttribute("eligible-only") ? new Set(this.#defaults?.eligible ?? []) : null;
    const shown = this.#models.filter(
      (model) => (eligible === null || eligible.has(model.tag)) && matchesQuery(model, this.#query),
    );
    const local = shown.filter((model) => model.origin !== "cloud").sort(order);
    const cloud = store.get().allowCloud
      ? shown.filter((model) => model.origin === "cloud").sort(order)
      : [];
    this.#groups = [
      { id: "local", title: t("components.picker.group_local"), models: local },
      { id: "cloud", title: t("components.picker.group_cloud"), models: cloud },
    ].filter((group) => group.models.length);
    this.#visible = this.#groups.flatMap((group) => group.models);
    return this.#visible;
  }

  #optionId(index) {
    return `${this.#uid}-option-${index}`;
  }

  #renderAll() {
    const { label, input, help } = this.#dom;
    label.textContent =
      this.getAttribute("label") ||
      t(this.multi ? "components.picker.label_multi" : "components.picker.label");
    this.#dom.listbox.setAttribute("aria-multiselectable", String(this.multi));
    this.#syncInput();
    this.#renderList();
    this.#renderHelp(help);
    this.#renderChips();
    this.#renderNotice();
    this.#dom.error.error = this.#error;
    this.#dom.error.hidden = !this.#error;
  }

  // Fermé, le champ d'un choix unique porte le nom du modèle choisi ; ouvert, il porte la saisie.
  #syncInput() {
    const { input } = this.#dom;
    if (this.#open && this.#query !== "") return;
    input.value = this.multi ? "" : this.#values.length ? this.#name(this.#values[0]) : "";
  }

  #renderHelp(help) {
    const parts = [];
    const first = this.#defaults?.tags?.[0];
    if (first && this.#defaults.reason) {
      const names = this.#defaults.tags.map((tag) => this.#name(tag)).join(", ");
      parts.push(t("components.picker.default_help", { name: names, reason: this.#defaults.reason }));
    } else if (!first && this.#defaults?.reason) {
      parts.push(this.#defaults.reason); // sans défaut (Agent, story 6.4) : la raison dit pourquoi
    }
    if (!this.#loaded && !this.#error) parts.push(t("components.picker.loading"));
    if (this.#loaded && !this.#ollamaUp && this.#models.some((m) => m.origin !== "cloud")) {
      parts.push(t("components.picker.ollama_down"));
    }
    help.textContent = parts.join(" ");
    help.hidden = parts.length === 0;
  }

  #renderChips() {
    const { chips } = this.#dom;
    chips.hidden = !this.multi || !this.#values.length;
    if (!this.multi) {
      chips.replaceChildren();
      return;
    }
    chips.replaceChildren(
      ...this.#values.map((tag) => {
        const item = element("li", "wl-picker-chip");
        const name = this.#name(tag);
        const button = element("button", "wl-picker-chip-remove");
        button.type = "button";
        button.dataset.tag = tag;
        button.setAttribute("aria-label", t("components.picker.remove", { name }));
        button.append(icon("close"));
        item.append(element("span", "wl-picker-chip-name", name), button);
        return item;
      }),
    );
  }

  #renderNotice() {
    const { notice } = this.#dom;
    const info = this.#notice;
    if (!info) {
      notice.replaceChildren();
      notice.hidden = true;
      return;
    }
    notice.hidden = false;
    const quoted = info.removed.map((name) => `« ${name} »`).join(", ");
    const text = element(
      "p",
      "wl-picker-notice-text",
      t(
        info.removed.length > 1
          ? "components.picker.cloud_removed_many"
          : "components.picker.cloud_removed_one",
        { names: quoted },
      ),
    );
    const parts = [text];
    if (info.proposal.length) {
      const button = element(
        "button",
        "btn",
        t("components.picker.use_default", { name: info.proposal.map((tag) => this.#name(tag)).join(", ") }),
      );
      button.type = "button";
      parts.push(button);
    }
    notice.replaceChildren(...parts);
  }

  #renderList() {
    const { input, popup, listbox, empty, live } = this.#dom;
    const options = this.#open ? this.#compute() : [];
    if (this.#active >= options.length) this.#active = options.length - 1;
    if (!this.#open) {
      popup.hidden = true;
      listbox.hidden = true;
      empty.hidden = true;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
      return;
    }
    popup.hidden = false;
    listbox.hidden = options.length === 0;
    empty.hidden = options.length > 0;
    input.setAttribute("aria-expanded", String(options.length > 0));
    if (!options.length) {
      empty.textContent = this.#query
        ? t("components.picker.empty", { query: this.#query })
        : t(this.hasAttribute("eligible-only") ? "components.picker.none_eligible" : "components.picker.none");
      input.removeAttribute("aria-activedescendant");
      live.textContent = empty.textContent;
      return;
    }

    let index = 0;
    const chosen = new Set(this.#values);
    const defaults = this.#defaultTags();
    listbox.replaceChildren(
      ...this.#groups.map((group) => {
        const title = element("div", "wl-picker-group-title", group.title);
        title.id = `${this.#uid}-group-${group.id}`;
        const section = element("div", "wl-picker-group");
        section.setAttribute("role", "group");
        section.setAttribute("aria-labelledby", title.id);
        section.append(
          title,
          ...group.models.map((model) =>
            this.#optionRow(model, index++, chosen.has(model.tag), defaults.has(model.tag)),
          ),
        );
        return section;
      }),
    );
    const active = this.#active >= 0 ? this.#optionId(this.#active) : null;
    if (active) {
      input.setAttribute("aria-activedescendant", active);
      document.getElementById(active)?.scrollIntoView({ block: "nearest" });
    } else {
      input.removeAttribute("aria-activedescendant");
    }
    const count = options.length;
    live.textContent = t(
      count === 1 ? "components.picker.results_one" : "components.picker.results_many",
      { count },
    );
  }

  #optionRow(model, index, selected, isDefault) {
    return buildOption(model, {
      id: this.#optionId(index),
      multi: this.multi,
      active: index === this.#active,
      selected,
      isDefault,
    });
  }

  // --- Interaction ----------------------------------------------------------------------------

  #setOpen(open) {
    if (open === this.#open) return;
    this.#open = open;
    if (open) {
      const selected = this.#compute().findIndex((model) => this.#values.includes(model.tag));
      this.#active = selected >= 0 ? selected : this.#visible.length ? 0 : -1;
    } else {
      this.#query = "";
      this.#active = -1;
    }
    this.#syncInput();
    this.#renderList();
  }

  #move(step) {
    const count = this.#compute().length;
    if (!count) return;
    // Sans option active, ↑ va à la dernière et ↓ à la première.
    const from = this.#active < 0 ? (step < 0 ? 0 : -1) : this.#active;
    this.#active = (from + step + count) % count;
    this.#renderList();
  }

  #onKey(event) {
    if (event.altKey || event.ctrlKey || event.metaKey) {
      if (event.altKey && event.key === "ArrowDown") {
        event.preventDefault();
        this.#setOpen(true);
      }
      return;
    }
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        if (!this.#open) this.#setOpen(true);
        else this.#move(1);
        break;
      case "ArrowUp":
        event.preventDefault();
        if (!this.#open) {
          this.#setOpen(true);
          this.#active = this.#visible.length - 1;
          this.#renderList();
        } else {
          this.#move(-1);
        }
        break;
      case "Enter":
        if (this.#open) {
          event.preventDefault();
          const model = this.#visible[this.#active];
          if (model && model.available) this.#choose(model.tag);
        }
        break;
      case "Escape":
        if (this.#open) {
          event.preventDefault();
          event.stopPropagation(); // Échap a fermé la liste : il n'arrête pas un run
          this.#setOpen(false);
        }
        break;
      case "Backspace":
        if (this.multi && this.#dom.input.value === "" && this.#values.length) {
          this.#remove(this.#values[this.#values.length - 1]);
        }
        break;
      default:
    }
  }

  #choose(tag) {
    this.#notice = null;
    this.#preselected = true;
    if (this.multi) {
      this.#values = this.#values.includes(tag)
        ? this.#values.filter((value) => value !== tag)
        : [...this.#values, tag];
      this.#renderAll();
    } else {
      this.#values = [tag];
      this.#setOpen(false);
      this.#renderAll();
    }
    this.#emit();
  }

  #remove(tag) {
    this.#notice = null;
    this.#preselected = true;
    this.#values = this.#values.filter((value) => value !== tag);
    this.#renderAll();
    this.#emit();
    this.#dom.input.focus();
  }
}

if (!customElements.get("wl-model-picker")) customElements.define("wl-model-picker", WlModelPicker);
