// Base documentaire : réglages (story 4.3, AD-15, AD-16) : modèle de représentation (embedding),
// taille des extraits, nombre d'extraits lus et stratégie de recherche par défaut.
//
// - Le serveur est la seule source : `GET /api/rag/settings` (valeurs en vigueur, bornes, modèles
//   installés, stratégies, état de la base) et `PUT` (seulement les champs que l'utilisateur a
//   changés). Les réglages vivent dans `preferences` ; l'app n'écrit jamais `wavelocalai.toml`.
// - Changer de modèle sur une base qui n'est pas vide : le serveur refuse (`409
//   embedding_change_needs_clear`), `wl-error` dit pourquoi et un bouton mène à « Vider » (les
//   boutons d'une erreur sont déduits de son code par le front, décision D-4).
// - Aucun bouton désactivé pendant un import : le contrat l'emporte, le serveur répond `409` et
//   `wl-error` l'affiche (écart ouvert n° 13).

import { api, ApiError } from "../core/api.js";
import { element } from "../core/dom.js";
import { t } from "../core/i18n.js";
import { plural } from "./documents-import-row.js";

let counter = 0;

function field(id, labelText, control, helpText) {
  const wrap = element("div", "docs-field");
  const label = element("label", "docs-field-label", labelText);
  label.htmlFor = id;
  wrap.append(label, control);
  if (helpText) {
    const help = element("p", "help", helpText);
    help.id = `${id}-help`;
    control.setAttribute("aria-describedby", help.id);
    wrap.append(help);
  }
  return wrap;
}

export function createSettings({ onClear, say }) {
  const uid = `docs-set-${++counter}`;
  let current = null; // dernière réponse du serveur
  let shownModel = ""; // modèle affiché dans la liste : celui de la base, sinon le défaut choisi

  const embedding = element("select", "docs-select");
  embedding.id = `${uid}-embedding`;
  const chunkSize = element("input", "docs-number");
  Object.assign(chunkSize, { type: "number", step: "50", id: `${uid}-chunk` });
  const topK = element("input", "docs-number");
  Object.assign(topK, { type: "number", step: "1", id: `${uid}-topk` });
  const strategy = element("select", "docs-select");
  strategy.id = `${uid}-strategy`;
  const save = element("button", "btn docs-primary", t("docs.save"));
  save.type = "submit";
  save.disabled = true; // tant que les réglages du serveur ne sont pas lus

  const legend = element("legend", "sr-only", t("docs.settings_legend"));
  const fields = element("fieldset", "docs-settings-fields");
  fields.append(
    legend,
    field(embedding.id, t("docs.embedding"), embedding, t("docs.embedding_help")),
    field(chunkSize.id, t("docs.chunk_size"), chunkSize, t("docs.chunk_size_help")),
    field(topK.id, t("docs.top_k"), topK, t("docs.top_k_help")),
    field(strategy.id, t("docs.strategy"), strategy),
  );
  const rerankLine = element("p", "docs-rerank");
  const volatile = element("p", "docs-notice", t("docs.index_volatile"));
  volatile.hidden = true;
  const problem = document.createElement("wl-error");
  const clear = element("button", "btn", t("docs.clear"));
  clear.type = "button";
  clear.hidden = true;
  const form = element("form", "docs-settings-form");
  form.noValidate = true;
  form.append(fields, rerankLine, volatile, problem, clear, save);

  const summary = element("summary", "docs-settings-summary", t("docs.settings_loading"));
  const root = element("details", "docs-settings");
  root.append(summary, form);

  const nameOf = (tag) => current?.embedding_models.find((m) => m.tag === tag)?.name ?? tag;

  function fill() {
    const models = [...current.embedding_models];
    shownModel = current.base.embedding_model ?? current.embedding_model ?? "";
    if (shownModel && !models.some((m) => m.tag === shownModel)) {
      models.push({ tag: shownModel, name: shownModel });
    }
    const options = [
      Object.assign(element("option", "", t("docs.embedding_default")), { value: "" }),
      ...models.map((m) =>
        Object.assign(element("option", "", m.name === m.tag ? m.tag : `${m.name} (${m.tag})`), {
          value: m.tag,
        }),
      ),
    ];
    embedding.replaceChildren(...options);
    embedding.value = shownModel;
    strategy.replaceChildren(
      ...current.strategies.map((key) =>
        Object.assign(element("option", "", t(`docs.strategy_${key}`)), { value: key }),
      ),
    );
    strategy.value = current.strategy;
    const { chunk_size: size, top_k: k } = current.limits;
    Object.assign(chunkSize, { min: String(size.min), max: String(size.max) });
    Object.assign(topK, { min: String(k.min), max: String(k.max) });
    chunkSize.value = String(current.chunk_size);
    topK.value = String(current.top_k);
    volatile.hidden = current.index.persistent !== false;
    // Reclassement par un reranker local (story 4.7) : l'état et la raison viennent du serveur.
    const rerank = current.reranker;
    rerankLine.textContent = rerank?.available
      ? t("docs.rerank_line_on", { model: rerank.model })
      : t("docs.rerank_line_off", { reason: rerank?.reason ?? "" });
    rerankLine.hidden = !rerank;
    save.disabled = false;
    summary.textContent = t("docs.settings_summary", {
      embedding: shownModel ? nameOf(shownModel) : t("docs.embedding_default"),
      rerank: t(`docs.rerank_${rerank?.available ? "on" : "off"}`),
      k: plural("docs.settings_extracts", current.top_k),
      strategy: t(`docs.strategy_${current.strategy}`),
    });
  }

  // Lit les réglages du serveur ; ne touche pas à un formulaire que l'utilisateur est en train de
  // remplir (`touched`).
  let touched = false;
  let pending = null; // réglages demandés quand le serveur a répondu « videz d'abord »
  async function load() {
    try {
      current = await api.ragSettings();
    } catch {
      if (!current) {
        problem.error = {
          code: "settings_failed",
          message: t("docs.settings_failed"),
          action: t("docs.settings_failed_action"),
        };
      }
      return;
    }
    if (problem.error?.code === "settings_failed") problem.error = null;
    if (!touched) fill();
  }
  for (const control of [embedding, chunkSize, topK, strategy]) {
    control.addEventListener("input", () => (touched = true));
  }

  function changes() {
    const next = {};
    if (embedding.value !== shownModel) next.embedding_model = embedding.value || null;
    if (Number(chunkSize.value) !== current.chunk_size) next.chunk_size = Number(chunkSize.value);
    if (Number(topK.value) !== current.top_k) next.top_k = Number(topK.value);
    if (strategy.value !== current.strategy) next.strategy = strategy.value;
    return next;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!current) return;
    problem.error = null;
    clear.hidden = true;
    if (!form.reportValidity()) return;
    const update = changes();
    if (Object.keys(update).length === 0) {
      say(t("docs.saved"));
      return;
    }
    await apply(update);
  });

  async function apply(update, append = false) {
    save.disabled = true;
    try {
      current = await api.saveRagSettings(update);
      touched = false;
      fill();
      say(
        update.embedding_model
          ? t("docs.embed_changed", { name: nameOf(update.embedding_model) })
          : t("docs.saved"),
        append,
      );
    } catch (failure) {
      const envelope = failure instanceof ApiError ? failure.envelope : null;
      problem.error = envelope ?? {
        code: "settings_failed",
        message: t("docs.settings_failed"),
        action: t("docs.settings_failed_action"),
      };
      if (envelope?.code === "embedding_change_needs_clear") {
        pending = update;
        embedding.value = shownModel; // rien n'a changé : la liste revient au modèle de la base
        clear.hidden = false;
      }
    } finally {
      save.disabled = false;
    }
  }

  clear.addEventListener("click", async () => {
    if (await onClear()) {
      clear.hidden = true;
      problem.error = null;
      touched = false;
      await load(); // base vide : le modèle de la liste redevient libre
      if (pending) await apply(pending, true); // les réglages qui avaient été refusés
    }
    pending = null;
  });

  // Pendant un import, « Vider » est désactivé comme celui du tableau (décision n° 13) : la raison
  // est la phrase `describedBy` de l'écran Base.
  function setLocked(locked, describedBy) {
    clear.disabled = locked;
    if (locked) clear.setAttribute("aria-describedby", describedBy);
    else clear.removeAttribute("aria-describedby");
  }

  return { el: root, load, setLocked };
}
