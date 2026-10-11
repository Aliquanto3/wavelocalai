---
id: SPEC-benchmark-qualite-difficile
companions:
  - ../../planning-artifacts/architecture/architecture-wavelocalai-2026-10-10/ARCHITECTURE-SPINE.md
  - modeles.md
  - pistes-et-questions.md
  - campagne-et-reprise.md
  - juge-et-calibration.md
  - statistiques.md
  - ../../../AGENTS.md
sources:
  - ../../planning-artifacts/research/technical-benchmark-qualite-slm-2026-10-10/research.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# Benchmark de qualité difficile pour les SLM locaux (wavelocalai)

## Why

C'est une douleur à résoudre. Le banc qualité actuel compte environ 30 items (14 de raisonnement, 8 de consignes, 4 d'outils). Il sature et ne départage plus les meilleurs modèles : un écart de 10 points n'y est détecté que dans 8 à 10 % des cas. Le catalogue de wavelocalai doit pourtant dire, usage par usage, quel petit modèle local choisir parmi 20. Les jeux publics connus sont saturés, contaminés ou biaisés pour des SLM, et aucun framework existant ne parle l'API native d'Ollama ni ne fait de comparaison appariée. D'où un banc maison, plus dur, en grande partie en français et protégé contre la contamination.

## Capabilities

- **CAP-1** — Jeu de questions difficile et non contaminé
  - **intent:** Chaque usage dispose de questions discriminantes, reproductibles depuis une graine, sous licence compatible ou privées.
  - **success:**
    - régénérer avec la même graine redonne les mêmes empreintes ;
    - chaque question porte `usage`, `group`, `source` et `license` ;
    - ~800 questions en piste coupée et 400 en piste activée (composition dans `pistes-et-questions.md`) ;
    - aucune question privée dans le dépôt, seulement son empreinte.
- **CAP-2** — Génération sur les deux pistes
  - **intent:** Chaque modèle répond en raisonnement coupé, et ceux qui en sont capables aussi en raisonnement activé, dans des conditions fixées et consignées.
  - **success:**
    - chaque ligne de `generation.jsonl` porte les champs de `campagne-et-reprise.md` (sortie brute, tokens, durées, `think`, `seed`, `num_ctx`, version d'Ollama…), sans score ;
    - un modèle sans capacité thinking n'est pas lancé en piste activée ;
    - une troncature au plafond de tokens est enregistrée (`status = truncated`), puis comptée comme échec, à part.
- **CAP-3** — Campagne reprenable sans perte
  - **intent:** L'opérateur arrête, plante ou redémarre la campagne et la reprend en ne perdant au plus que la question en cours.
  - **success:**
    - un arrêt brutal du processus puis une reprise donnent un JSONL sans doublon de clé ni trou ;
    - Ctrl+C ou le fichier `STOP` termine la question en cours, puis sort ;
    - un manifeste différent bloque la reprise : jeu de questions, configuration, digest d'un modèle, version d'Ollama, machine ou empreinte du harnais ;
    - une panne d'Ollama déclenche un nouvel essai de la question une fois le service revenu ;
    - la machine ne se met pas en veille pendant la campagne.
- **CAP-4** — Correction déterministe
  - **intent:** Toute question hors rédaction est notée sans juge, et sa note se recalcule hors ligne depuis `generation.jsonl`.
  - **success:**
    - chaque correcteur passe des tests sur des cas à verdict connu ;
    - seule la phase de correction écrit les scores, dans `grading.jsonl`, rédaction comprise (depuis les verdicts du juge retenu) ;
    - recorriger le même `generation.jsonl` redonne un `grading.jsonl` identique, sans régénérer.
- **CAP-5** — Jugement découplé de la rédaction en français
  - **intent:** Les réponses de rédaction sont notées par le juge retenu, critère par critère en questions fermées, dans une phase séparée et reprenable.
  - **success:**
    - le jugement relit `generation.jsonl` et écrit son propre `judgment.jsonl` en ajout seul, avec la clé de génération plus le critère ;
    - il reprend après un arrêt sans re-juger ce qui est fait.
- **CAP-6** — Juge calibré
  - **intent:** Le juge de campagne est choisi sur son accord avec des étiquettes humaines, et son biais envers Qwen est mesuré.
  - **success:**
    - sur ~100 étiquettes produites par Anaël, un rapport donne l'accord et le coût de chacune des 4 configurations de `juge-et-calibration.md` ;
    - il donne l'écart d'accord entre candidats Qwen et non-Qwen ;
    - le choix du juge est consigné avant la campagne.
- **CAP-7** — Classement statistiquement fondé
  - **intent:** Le rapport dit quels modèles se distinguent vraiment, par piste et par usage, et si le classement concorde avec une référence externe.
  - **success:** à partir de `grading.jsonl` et de `generation.jsonl` seulement, le rapport produit :
    - le score par question ;
    - un intervalle de Wilson par modèle ;
    - des comparaisons appariées corrigées pour les tests multiples ;
    - des groupes de modèles indiscernables ;
    - le taux de troncature ;
    - la corrélation de Spearman avec l'indice Artificial Analysis selon le critère de `statistiques.md`.
- **CAP-8** — Pilote de validation
  - **intent:** Avant la campagne complète, un pilote sur 4 modèles vérifie que le banc discrimine et tient le budget.
  - **success:** le rapport de pilote donne :
    - la part de questions discordantes entre modèles ;
    - les usages au plafond ou au plancher ;
    - le taux de réponses changeantes sur un sous-ensemble rejoué ;
    - la distribution des tokens de réflexion et le taux de troncature ;
    - une projection de durée de la campagne complète ;
    - un contrôle de cohérence de l'ordre des modèles avec l'ancien banc et l'indice AA.

## Constraints

- **Banc existant :** ne pas modifier `scripts/benchmark_slm.py` ni ce qu'il importe de `src/core/` (dont `config.py`). Le nouveau banc est le paquet `scripts/quality_bench/` de la v1 et ne dépend d'aucun des deux, sauf `disable_telemetry` (AD-1).
- **Langue :** identifiants en anglais (paquet, champs JSON, valeurs fermées, sous-commandes). Docs, journaux et rapports en français.
- **Ollama :**
  - API native `/api/chat` seulement, jamais `/v1` ;
  - une seule version pour toute la campagne (0.40.2 sur la tour au 2026-10-10) : une autre version au manifeste interdit la reprise ;
  - hygiène de requête détaillée dans `campagne-et-reprise.md`.
- **Hors ligne :** aucun téléchargement ni appel réseau pendant la génération. Le juge, cloud ou local, n'intervient que dans la phase de jugement, découplée. Le juge local est défini par le contrat `POST /v1/systemone` sur `localhost`, pas par un serveur précis, et ne tourne jamais en même temps que la génération.
- **Correction :** déterministe pour tous les usages sauf la rédaction en français. Le score ne vit que dans `grading.jsonl` ; `generation.jsonl` reste brut (AD-3).
- **Machine :** tour-rtx3050 seule (RTX 3050 8 Go, 31 Go de RAM). Contexte long plafonné entre 8K et 32K selon la mémoire. Windows se met en veille après 5 h.
- **Budget :** campagne complète en 5 à 6 jours, estimée entre 105 et 140 h avec la piste activée à 400 questions et des plafonds de 4 096 tokens en raisonnement et de 2 048 ailleurs. Si la projection du pilote dépasse 6 jours, appliquer dans l'ordre :
  1. abaisser les plafonds de tokens ;
  2. vérifier que la piste activée reste réservée aux modèles qui déclarent la capacité thinking dans `/api/show` ;
  3. ramener le N de la piste activée vers ~330.
- **Puissance acceptée :** un écart de 10 points est détectable sur le score global de chaque piste, de 20 points par usage.
- **Dépôt public :** aucune question privée, aucune réponse brute à une question privée et aucune clé d'API dans un commit ou une PR. Aucune question privée n'est envoyée à un juge cloud. Exclusions de licence dans `pistes-et-questions.md`.
- **Python :**
  - 3.10+ ;
  - versions de dépendances vérifiées sur PyPI ou par une installation réelle ;
  - `disable_telemetry()` avant tout import de Hugging Face, Chroma, CrewAI, Ragas ou `langchain_community` ;
  - toutes les dépendances installées et les données NLTK téléchargées avant la campagne ; M-IFEval réduit aux vérificateurs FR, sans spaCy.

## Non-goals

- Élimination adaptative des modèles en cours de campagne (O'Brien-Fleming, Hoeffding races).
- Campagne sur d'autres machines que tour-rtx3050.
- Précision au-delà du plafond de tokens : le banc ne mesure pas ce que ferait un modèle avec 32K tokens de réflexion.
- Toute modification du banc existant de vitesse et d'énergie.
- Mesure de l'énergie par question.
- Affichage des résultats dans l'app Streamlit.
- Plusieurs tirages par question (K > 1), sauf si le pilote les impose (voir `statistiques.md`).

## Success signal

- Les 20 modèles sont passés en 5 à 6 jours sur la tour, malgré au moins un arrêt et une reprise : les 20 en piste coupée, et ceux capables de raisonnement en piste activée.
- Le rapport final classe les modèles en groupes indiscernables par piste et par usage, avec des intervalles. Il rapporte la corrélation de Spearman avec l'indice AA selon le critère de `statistiques.md`.

## Assumptions

- Répartition indicative des ~800 questions de la piste coupée : raisonnement 130, consignes 130, outils 130, extraction 110, RAG 110, abstention 110, rédaction 80. Elle sera réajustée après le pilote. La piste activée en prend la moitié par strates.
- Le N de puissance se compte en groupes indépendants (passage, gabarit, conversation multi-tours), pas en questions.
- L'estimation de budget repose sur les débits de l'ancien banc, un prompt RAG de 16K en moyenne et des réponses de 350 tokens. Le pilote la remplace par des mesures.
- Pas de mesure d'énergie par question, la RTX 3050 rapportant une puissance N/A : seulement les tokens et les durées d'Ollama.
- Les JSONL bruts restent hors du dépôt, comme `data/`. Sont versionnés : les scores par question indexés par empreinte, les agrégats et le manifeste (liste blanche AD-6).
- La tenue en français de Winnow-E4B et son serveur sur la tour (Windows, 8 Go de VRAM) sont à vérifier au début de la story 7, avec Perplexity Decider hébergé en repli.

## Open Questions

- Quel seuil d'accord entre juge et humain pour retenir un juge, et quel biais Qwen maximal tolérer ? À fixer par Anaël au plus tard à la calibration (story 9).
- Quel serveur pour le juge local : WSL2 avec `winnow-inference`, Winnow-E4B importé dans Ollama comme modèle `decision`, ou Perplexity Decider hébergé ? À trancher au début de la story 7, par mesure sur la tour.
