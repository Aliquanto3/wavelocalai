// Réglages avancés de la Discussion (UX-DR23, story 4.6) : la stratégie de recherche et le nombre
// d'extraits. Les noms techniques (HyDE, Self-RAG, Top-K) ne figurent qu'en aide. Chaque réglage est
// envoyé avec la question suivante (`POST /api/rag/runs {strategy, top_k}`) : il agit réellement sur
// le run suivant. La stratégie et le nombre d'extraits par défaut, et le plafond, viennent du
// serveur (`GET /api/rag/settings`, réglés à l'écran Base), jamais d'une valeur écrite ici.
// Le bloc dit aussi si un reranker local reclasse les extraits, ou pourquoi il ne le fait pas
// (story 4.7) : l'état et la raison viennent du serveur (`settings.reranker`), rien n'est deviné ici.

import { element } from "../core/dom.js";
import { t } from "../core/i18n.js";

export const STRATEGIES = ["naive", "hyde", "self_rag"];

// Étape que dit `wl-run-status` dès le démarrage du run : HyDE commence par rédiger sa réponse
// hypothétique, les autres par chercher. Les étapes suivantes viennent de `retrieval_step`.
const FIRST_STAGE = { naive: "retrieving", hyde: "hypothesizing", self_rag: "retrieving" };

export function firstStage(strategy) {
  return FIRST_STAGE[strategy] ?? "retrieving";
}

// Le bloc « Réglages avancés » : `node` (un `details` replié), `strategy()` et `topK()` (nombre
// entier choisi, ou `null` : défaut du serveur), `configure({ topK, maxTopK, strategy, reranker })`
// pour les défauts et bornes que donne le serveur (sans effet sur un champ que l'utilisateur a déjà
// changé) et l'état du reclassement.
export function advancedSettings(uid) {
  const strategy = element("select", "docs-select");
  strategy.id = `${uid}-strategy`;
  for (const key of STRATEGIES) {
    const option = element("option", "", t(`discussion.strategy_${key}`));
    option.value = key;
    strategy.append(option);
  }
  const strategyLabel = element("label", "docs-field-label", t("discussion.strategy"));
  strategyLabel.htmlFor = strategy.id;
  const strategyHelp = element("p", "help");
  strategyHelp.id = `${uid}-strategy-help`;
  strategy.setAttribute("aria-describedby", strategyHelp.id);
  const showHelp = () => {
    strategyHelp.textContent = t(`discussion.strategy_help_${strategy.value}`);
  };
  let strategyTouched = false;
  strategy.addEventListener("change", () => {
    strategyTouched = true;
    showHelp();
  });
  showHelp();

  const topK = element("input", "docs-number");
  topK.id = `${uid}-top-k`;
  topK.type = "number";
  topK.min = "1";
  topK.step = "1";
  topK.inputMode = "numeric";
  const topKLabel = element("label", "docs-field-label", t("discussion.top_k"));
  topKLabel.htmlFor = topK.id;
  const topKHelp = element("p", "help", t("discussion.top_k_help"));
  topKHelp.id = `${uid}-top-k-help`;
  topK.setAttribute("aria-describedby", topKHelp.id);
  let touched = false;
  // Un nombre hors des bornes est ramené dans les bornes, et le champ le montre.
  const read = () => {
    const value = Number.parseInt(topK.value, 10);
    const max = Number.parseInt(topK.max, 10);
    if (!Number.isInteger(value)) return null;
    return Math.min(Math.max(value, 1), Number.isInteger(max) ? max : value);
  };
  topK.addEventListener("input", () => {
    touched = true;
  });
  topK.addEventListener("change", () => {
    const value = read();
    topK.value = value === null ? "" : String(value);
  });

  const rerankNote = element("p", "docs-rerank");
  rerankNote.hidden = true;

  const body = element("div", "docs-advanced-body");
  body.append(strategyLabel, strategy, strategyHelp, topKLabel, topK, topKHelp, rerankNote);
  const node = element("details", "docs-advanced");
  node.append(element("summary", "", t("discussion.advanced")), body);
  return {
    node,
    strategy: () => strategy.value,
    topK: read,
    configure({ topK: byDefault, maxTopK, strategy: byDefaultStrategy, reranker }) {
      showReranker(rerankNote, reranker);
      if (Number.isInteger(maxTopK)) topK.max = String(maxTopK);
      if (!touched && Number.isInteger(byDefault)) topK.value = String(byDefault);
      if (!strategyTouched && STRATEGIES.includes(byDefaultStrategy)) {
        strategy.value = byDefaultStrategy;
        showHelp();
      }
    },
  };
}

// L'état du reclassement : actif (avec le modèle), ou indisponible avec la raison du serveur.
function showReranker(note, reranker) {
  if (!reranker || typeof reranker !== "object") {
    note.hidden = true;
    return;
  }
  note.textContent = reranker.available
    ? t("discussion.rerank_on", { model: reranker.model })
    : t("discussion.rerank_off", { reason: reranker.reason ?? "" });
  note.dataset.reranker = reranker.available ? "on" : "off";
  note.hidden = false;
}
