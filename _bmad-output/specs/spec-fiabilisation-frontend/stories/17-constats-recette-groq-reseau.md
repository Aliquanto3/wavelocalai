---
title: 'Constats de la recette du 29/09 : modèles Groq accessibles, aucun appel réseau superflu'
type: 'bugfix'
created: '2026-09-29'
status: 'done'
baseline_commit: 'dac91dd90554fa427b507a297551e7880c40a7d9'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/specs/spec-fiabilisation-frontend/stories/16-fournisseur-cloud-groq.md'
  - '{project-root}/_bmad-output/specs/spec-fiabilisation-frontend/stories/12-souverainete-telemetries-co2-cloud.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** La recette dans Chrome du 29/09 (cahier de recette, C1, C5 en échec et R2) a relevé trois écarts : l'app propose `llama-3.3-70b-versatile` et `llama-3.1-8b-instant` alors que la clé Groq de l'utilisateur n'y a pas accès (404 `model_not_found`, `/models` en liste 11 dont les deux GPT-OSS) ; l'app lancée hors tests contacte pypi.org (vérification de version de CrewAI) et huggingface.co (vérification du modèle d'embedding `all-MiniLM-L6-v2`, pourtant déjà dans le cache Hugging Face).

**Approach:** Trois corrections d'une même story, demandée ainsi par l'utilisateur (29/09) :
1. `GroqProvider` ne propose que les modèles de sa liste fixe que `/models` renvoie pour la clé. L'appel n'a lieu que quand les modèles cloud sont listés (cloud autorisé et clé configurée) ; son résultat est gardé en mémoire. Si `/models` échoue (réseau, clé refusée, délai), la liste fixe complète est proposée, et l'erreur de l'inférence reste lisible comme aujourd'hui.
2. `CREWAI_DISABLE_VERSION_CHECK=true` rejoint `TELEMETRY_OPT_OUTS` (même règle : une valeur déjà définie l'emporte).
3. Le modèle d'embedding, et le reranker par le même chemin, se chargent d'abord sans réseau (`local_files_only=True`) ; seulement s'il n'est ni dans `data/models` ni dans le cache Hugging Face, le chargement actuel (téléchargement) prend le relais.

## Boundaries & Constraints

**Always:** Le routage d'un tag vers Groq reste l'appartenance exacte à `GROQ_MODELS` (un tag inaccessible choisi quand même donne l'erreur lisible actuelle). Appel `/models` borné par un délai court (5 s) et jamais relancé à chaque rerun de Streamlit : succès gardé pour la vie du provider, échec gardé 10 minutes. Tous les tests sans réseau : client `/models` simulé dans chaque test qui liste des modèles Groq avec une clé factice ; chargement Hugging Face simulé.

**Never:** Appeler `/models` quand le cloud est désactivé ou sans clé. Proposer un modèle Groq absent de la liste fixe (aperçu, transcription) même si `/models` le renvoie. Positionner `HF_HUB_OFFLINE` ou `TRANSFORMERS_OFFLINE` globalement (bloquerait le premier téléchargement légitime). Modifier `scripts/benchmark_slm.py`, `src/core/config.py`, `data/`, `config/models_catalog.json`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Clé à accès partiel | `/models` renvoie les 2 GPT-OSS + d'autres ids | 2 modèles Groq proposés (GPT-OSS 120B, 20B) | N/A |
| `/models` en échec | exception réseau, 401 ou délai | 4 modèles de la liste fixe | Avertissement journalisé, pas d'erreur à l'écran |
| Rerun | deuxième listage dans les 10 min | Aucun nouvel appel `/models` | N/A |
| Cloud désactivé | clé définie, bascule inactive | Aucun modèle Groq, aucun appel `/models` | N/A |
| Embedding en cache | `all-MiniLM-L6-v2` dans le cache HF, pas dans `data/models` | Chargé avec `local_files_only=True`, aucune connexion | N/A |
| Embedding absent | ni local ni en cache | Second chargement, réseau autorisé (comportement actuel) | OSError du premier essai absorbée |
| Version CrewAI | `CREWAI_DISABLE_VERSION_CHECK` non défini | Vaut `true` après `disable_telemetry()` | Valeur déjà définie conservée |

</frozen-after-approval>

## Code Map

- `src/core/providers/groq_provider.py` -- `GroqProvider.list_models` (hérite d'`OpenAIProvider.list_models`, itère `AVAILABLE_MODELS`) : filtrer par les ids de `/models`. Nouvelle méthode `_fetch_model_ids()` (client synchrone `openai.OpenAI(api_key, base_url=GROQ_BASE_URL, timeout=5)`, `models.list()`, comme `health_check`), point de simulation des tests. Cache : ids + horodatage (`time.monotonic`). `is_groq_model` et `GROQ_MODELS` inchangés.
- `src/core/providers/provider_factory.py:164-193` -- `list_all_models` saute déjà les providers non locaux sans `include_cloud` : c'est la garantie « aucun appel si cloud désactivé ». Ne pas changer.
- `src/core/telemetry.py` `TELEMETRY_OPT_OUTS` -- ajouter la variable (lue par `crewai/events/utils/console_formatter.py:74`, valeurs `true`/`1`).
- `src/core/rag/models_factory.py` -- `get_embedding_model` (`HuggingFaceEmbeddings`, `model_kwargs` transmis à `SentenceTransformer`) et `get_reranker_model` (`CrossEncoder`) : premier essai avec `local_files_only=True` (vérifié sur ce poste : `SentenceTransformer('all-MiniLM-L6-v2', local_files_only=True)` se charge depuis `HF_HOME` sans connexion ; un modèle absent lève `OSError`), repli sur l'appel actuel. Garder `trust_remote_code=True`.
- Tests existants à adapter (sinon ils appelleraient le vrai `/models` avec une clé factice) : `tests/unit/test_llm_provider.py:318-370` (`GROQ_TAGS`, listage avec `cle-factice`), `tests/app/test_sovereignty.py:368-410` (fixture `groq_listing`). `tests/unit/test_telemetry.py` (liste des opt-outs). Tests RAG existants de `models_factory` s'il y en a (`grep RAGModelsFactory tests`).

## Tasks & Acceptance

**Execution:**
- [x] `src/core/providers/groq_provider.py` -- `_fetch_model_ids` borné, cache succès/échec, `list_models` filtré avec repli sur la liste fixe -- C1, C5
- [x] `src/core/telemetry.py` -- `CREWAI_DISABLE_VERSION_CHECK: "true"` avec commentaire (pypi.org) -- R2
- [x] `src/core/rag/models_factory.py` -- chargement hors ligne d'abord, repli réseau, pour l'embedding et le reranker -- R2
- [x] `tests/unit/test_llm_provider.py`, `tests/app/test_sovereignty.py` -- simuler `_fetch_model_ids` dans les tests existants ; nouveaux cas de la matrice (accès partiel, échec → liste fixe, cache sans second appel, cloud désactivé → `_fetch_model_ids` jamais appelé) -- non-régression sans réseau
- [x] `tests/unit/test_telemetry.py` -- la nouvelle variable est posée et une valeur existante conservée -- R2
- [x] `tests/unit/test_rag_models_factory.py` (nouveau, ou fichier RAG existant) -- `HuggingFaceEmbeddings`/`CrossEncoder` simulés : premier appel avec `local_files_only=True` ; `OSError` → second appel sans ce drapeau ; modèle local de `data/models` chargé par son chemin -- R2

**Acceptance Criteria:**
- Given la clé de l'utilisateur (accès aux seuls GPT-OSS) et le cloud autorisé, when on ouvre la liste des modèles, then seuls GPT-OSS 120B et GPT-OSS 20B apparaissent « · Cloud ».
- Given l'app lancée hors tests avec `all-MiniLM-L6-v2` en cache, when on ouvre l'Assistant documentaire puis la page Agents, then aucune connexion ne part vers huggingface.co ni pypi.org.

## Implementation Notes

- `GroqProvider._fetch_model_ids` (client `openai.OpenAI` synchrone, `timeout=5`) ; `_accessible_model_ids` garde les ids en mémoire (succès : vie du provider ; échec : 10 min via `time.monotonic`, avertissement journalisé). `list_models` filtre la liste fixe par ces ids, ou la propose en entier si `/models` échoue ; sans clé, `super().list_models()` est vide et `/models` n'est pas appelé.
- `src/core/rag/models_factory.py` : `_load_offline_first` appelle le chargeur avec `local_files_only=True`, puis sans ce drapeau sur `OSError` seulement ; même chemin pour l'embedding et le reranker (`trust_remote_code=True` gardé). Aucune variable `HF_HUB_OFFLINE` globale.
- Tests : fixture autouse de `TestGroqProvider` et fixture `groq_listing` simulent `_fetch_model_ids` ; nouveaux cas (accès partiel, échec réseau/délai/401 → liste fixe, cache succès, cache échec 10 min puis nouvel essai, cloud désactivé et sans clé → aucun appel, tag inaccessible toujours routé vers Groq, délai de 5 s) ; nouveau `tests/unit/test_rag_models_factory.py`.
- Vérifié : `.venv-app\Scripts\python -m pytest tests/unit tests/app` 866 réussis ; `uvx ruff check` et `uvx black --check` propres sur les fichiers touchés. Chargement réel de `all-MiniLM-L6-v2` depuis le cache avec `HF_ENDPOINT` pointé sur un port fermé : chargé sans repli.
- Non vérifié ici : recette dans Chrome (C1, C5 avec la vraie clé, R2 avec garde réseau ou pare-feu).

## Spec Change Log

## Review Triage Log

Revue du 29/09 : Blind Hunter (11), Edge Case Hunter (6), Verification Gap (1 écart + 1 autre). Doublons regroupés par cause.

- `/models` : `max_retries` par défaut (2) du SDK, blocage d'un rerun d'environ 15-20 s au lieu de 5 s ; client synchrone jamais fermé (blind ×2, edge ×2, verification-gap) — medium, patch : `max_retries=0`, client en gestionnaire de contexte, test.
- Contrat `local_files_only` / `OSError` des vraies bibliothèques jamais testé, tout est simulé (verification-gap) — medium, patch : test de contrat sur un dépôt inexistant, sans réseau.
- Aucun modèle de la liste fixe accessible : Groq disparaît sans trace (blind, edge) — low, patch : avertissement journalisé. Liste vide conforme à l'intention.
- Succès gardé à vie, sans rafraîchissement (blind, edge) — low, rejeté : décision de la spec (succès gardé pour la vie du provider).
- Clé refusée (401) : liste fixe complète proposée (blind) — low, rejeté : repli décidé dans l'intention ; l'erreur d'inférence reste lisible.
- Deux sessions Streamlit simultanées : deux appels `/models` (blind, edge) — low, rejeté : rare, correctif = verrou.
- Dossier local de `data/models` cassé rechargé une seconde fois, journal inexact (blind, edge) — low, rejeté : cas rare, correctif = branche supplémentaire.
- Exception autre qu'`OSError` (`TypeError` si `CrossEncoder` n'accepte pas `local_files_only`) (blind) — maybe-false, rejeté : le test de contrat ajouté échouerait ; paramètre présent dans sentence-transformers 6.1 installé.
- Cache partiel sans `modules.json`, pooling par défaut (blind) — false : `snapshot` HF complet dans le cache de ce poste, et le chargement réseau lirait les mêmes fichiers.
- Fichier de story non suivi dans le diff (blind) — false : il sera ajouté au commit.
- Critère « aucune connexion vers pypi.org » sans test d'ordre `disable_telemetry` / import de CrewAI (blind) — low, rejeté : ordre déjà testé par la story 12 (`test_telemetry.py`), vérification manuelle R2.
- Test 401 construit à partir d'une chaîne sentinelle, clé absente du journal non vérifiée (blind) — low, rejeté : lisible, le journal n'inclut que le message d'exception du SDK.

## Verification

**Commands:**
- `.venv-app\Scripts\python -m pytest tests/unit tests/app -q` -- expected: tout réussit, hors les 4 échecs connus de `tests/unit` listés dans AGENTS.md s'ils se produisent
- `uvx ruff check` et `uvx black --check` sur les fichiers touchés -- expected: propres

**Manual checks (if no CLI):**
- Recette de l'utilisateur : C1 et C5 (liste Groq réduite aux GPT-OSS), R2 (aucune requête serveur vers huggingface.co ni pypi.org, par exemple avec la garde réseau e2e ou un pare-feu).
