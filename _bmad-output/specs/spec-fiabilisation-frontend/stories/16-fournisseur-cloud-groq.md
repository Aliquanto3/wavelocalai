---
title: 'Fournisseur cloud Groq'
type: 'feature'
created: '2026-09-27'
status: 'done'
baseline_commit: '24b07aed474c5663d10249aa4fb77eb85eaeff7f'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/specs/spec-fiabilisation-frontend/stories/15-juge-modele-defaut-benchmark-poste.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Les modèles cloud de l'app passent par Mistral, OpenAI ou Anthropic. L'utilisateur constate que Groq, gratuit, fonctionne mieux que Mistral en ce moment ; sans lui, utiliser le cloud (juge cloud de la story 15 compris) demande une clé payante ou un service moins fiable.

**Approach:** Ajouter un fournisseur Groq sur le modèle d'`OpenAIProvider` (API compatible OpenAI, URL `https://api.groq.com/openai/v1`, clé `GROQ_API_KEY`), sans nouvelle dépendance. Il n'est actif que si la clé est configurée, et ses modèles n'apparaissent que si le cloud est autorisé, avec le badge Cloud. Modèles proposés : les modèles de chat en production chez Groq, vérifiés le 27/09 dans la documentation publique (`openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`) ; ni aperçu (preview), ni transcription. Ordre des juges cloud : `openai/gpt-oss-120b` juste après GPT-4o et avant Mistral Large, `llama-3.3-70b-versatile` après les autres grands modèles cloud.

Demande de l'utilisateur (27/09), exception assumée à la règle « v1 = UI/UX » d'AGENTS.md.

## Boundaries & Constraints

**Always:** Routage d'un tag vers Groq par appartenance exacte à la liste de ses modèles (un tag Ollama comme `llama3.2:3b` reste local). Clé neutralisée dans les tests : `GROQ_API_KEY` vide dans `APP_ENV` de `tests/e2e/conftest.py` et dans le banc AppTest. Une erreur de Groq (quota 429, clé invalide) s'affiche comme les autres erreurs d'inférence, lisible, jamais comme un token. `.env.example` documente la clé. CO₂ d'une réponse Groq : inconnu (« — ») tant que le catalogue n'a pas ses paramètres actifs, comme pour OpenAI et Anthropic.

**Never:** Appeler l'API Groq dans un test. Ajouter `groq` ou `langchain-groq` aux dépendances. Proposer un modèle Groq quand le cloud est désactivé. Modifier `data/` ou `config/models_catalog.json`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Clé et cloud autorisé | `GROQ_API_KEY` définie, bascule cloud active | 4 modèles Groq listés « · Cloud » | N/A |
| Sans clé | `GROQ_API_KEY` absente | Aucun modèle Groq, aucun appel | N/A |
| Cloud désactivé | clé définie, bascule inactive | Aucun modèle Groq | N/A |
| Tag local homonyme | `llama3.2:3b` | Routé vers Ollama | N/A |
| Quota dépassé | 429 de Groq | Erreur lisible dans le tour, question conservée | Pas de trace brute |
| Juge par défaut | Groq seul fournisseur cloud, cloud autorisé | Juge = `openai/gpt-oss-120b` | N/A |

</frozen-after-approval>

## Code Map

- `src/core/providers/openai_provider.py` -- modèle à suivre : client `AsyncOpenAI` paresseux, `chat_stream` (métriques estimées), `get_langchain_model` (`ChatOpenAI`, accepte `base_url`), `AVAILABLE_MODELS`, `is_available`.
- `src/core/providers/groq_provider.py` (nouveau) -- `GroqProvider`, nom `groq`, `is_local = False`, URL de base et clé propres.
- `src/core/providers/provider_factory.py:64-132` -- enregistrement si la clé est configurée (comme OpenAI et Anthropic) ; `get_provider` : branche Groq par appartenance exacte, avant le repli Ollama.
- `src/core/model_defaults.py` -- ordre de préférence des juges cloud introduit par la story 15 : y insérer les modèles Groq.
- `src/app/ui.py` `is_cloud_model` / `is_cloud_tag` -- origine d'un tag hors sélecteur : un modèle Groq doit être reconnu cloud, pas « Origine inconnue ».
- `tests/e2e/conftest.py:68` `APP_ENV`, `tests/app/conftest.py` -- neutraliser `GROQ_API_KEY`.
- `.env.example:58-68` -- section des clés cloud.
- Tests : `tests/unit/test_llm_provider.py` (routage, liste, indisponible sans clé), `tests/app/test_sovereignty.py` (badge, cloud désactivé), `tests/unit/test_model_defaults.py` (ordre des juges).

## Tasks & Acceptance

**Execution:**
- [x] `src/core/providers/groq_provider.py` -- fournisseur Groq compatible OpenAI -- nouveau fournisseur cloud
- [x] `src/core/providers/provider_factory.py` -- enregistrement conditionnel et routage exact -- disponibilité
- [x] `src/core/model_defaults.py`, `src/app/ui.py` -- ordre des juges cloud, origine cloud des tags Groq -- cohérence avec la story 15 et les badges
- [x] `tests/e2e/conftest.py`, `tests/app/conftest.py`, `.env.example` -- clé neutralisée en test, documentée -- aucun appel réel
- [x] `tests/unit/test_llm_provider.py`, `tests/unit/test_model_defaults.py`, `tests/app/test_sovereignty.py` -- matrice ci-dessus, client simulé -- non-régression

**Acceptance Criteria:**
- Given une clé Groq et le cloud autorisé, when on ouvre la Discussion, then les modèles Groq sont proposés avec le badge Cloud après tous les modèles locaux.
- Given le cloud désactivé, when on ouvre n'importe quelle page, then aucun modèle Groq n'est proposé et aucune requête ne part vers api.groq.com.

## Implementation Notes

- `GroqProvider` hérite d'`OpenAIProvider` (SDK `openai`, `base_url` Groq pour `AsyncOpenAI`, `ChatOpenAI` et `health_check`) ; `GROQ_MODELS` et `is_groq_model` (appartenance exacte) servent au routage de la factory (avant les préfixes OpenAI), à `is_cloud_tag` et au nom du fournisseur dans les erreurs.
- Hors Code Map : `src/app/states.py` (`_cloud_provider_name` renvoie « Groq » ; conseil d'échec cloud élargi au quota : « vérifiez la connexion, la clé d'API et son quota ») et `src/core/providers/__init__.py` (export). `tests/app/conftest.py` repart aussi d'une factory neuve, sans provider Groq déjà enregistré.
- CO₂ « — » sans changement de code : les modèles Groq sont absents du catalogue, `params` vaut « ? » comme pour OpenAI.
- Constaté, hors périmètre : `get_provider("gpt-oss:20b")` part vers OpenAI par le préfixe `gpt-` (tag Ollama local mal routé) ; `OpenAIProvider._get_client` appelle `AsyncOpenAI`, importé seulement sous `TYPE_CHECKING` (NameError au premier appel réel), contourné dans `GroqProvider`.
- Vérifié : `pytest tests/unit tests/app` 841 réussis ; `ruff check` et `black --check` propres sur les fichiers touchés.

- Après revue (27/09) : juge Ragas Groq enveloppé avec `bypass_n=True` (Groq refuse `n` ≠ 1) ; agent seul routé vers le LangChain du fournisseur et équipe d'agents vers le fournisseur OpenAI natif de CrewAI (`custom_openai`, préfixe `openai/` doublé pour garder le tag exact) ; journal d'erreur au nom du fournisseur ; les quatre clés cloud neutralisées dans le banc AppTest.
- Vérifié sur poste-rtx3060, vraie clé Groq dans `.env` : `pytest tests/unit tests/app` 847 réussis ; `pytest tests/e2e -m e2e` 34 réussis, seul `axe[Agent_Lab-dark]` en échec (écart accepté, story 14) ; garde réseau e2e sans aucune connexion sortante.
- Le sous-agent a lancé ruff et black via `uvx` (cache d'uv, hors `.venv-app`) pour vérifier le formatage.

## Review Triage Log

Revue du 27/09 : Blind Hunter (11), Edge Case Hunter (4), Verification Gap (1 écart + 2 autres). Doublons regroupés par cause.

- Juge Ragas Groq : `n=3` refusé par Groq (« If N is supplied, it must be equal to 1 », docs Groq) — medium, patch : `LangchainLLMWrapper(bypass_n=True)` pour un juge Groq, test.
- Agent seul et équipe d'agents envoient un modèle Groq à Ollama (blind, edge ×2, verification-gap) — medium, patch : routage Groq dans `agent_engine` (LangChain du fournisseur) et `crew_engine` (fournisseur OpenAI natif de CrewAI, `custom_openai`), tests.
- Erreur Groq journalisée deux fois, d'abord « OpenAI Error » (blind) — low, patch.
- Banc AppTest : seule la clé Groq neutralisée, les clés du .env réenregistrées par la factory neuve (blind) — medium, patch.
- `OpenAIProvider._get_client` et `NameError` (blind) — medium, defer : antérieur.
- Modèles OpenAI et Anthropic des agents, `gpt-oss:20b` routé vers OpenAI (verification-gap, implémentation) — medium, defer : antérieur.
- Débit gpt-oss surestimé par les jetons de raisonnement (blind) — maybe-false, defer (medium si confirmé).
- CO₂ d'une réponse Groq calculé en local dans l'Arène, le Banc d'essai et les Documents (verification-gap, edge) — medium, carried : même cause que l'élément différé de la story 12 (formule choisie par le type du catalogue).
- Pas de test du « — » de CO₂ dans la Discussion (blind) — low, rejeté : chemin couvert par `test_chat_carbon_uses_catalog_entry_not_selector_label` (cloud hors catalogue).
- Message propre au quota 429 (blind) — low, rejeté : le conseil cite désormais le quota.
- Paramètres « ? » alors que publics (blind) — low, rejeté : décision de la spec (CO₂ inconnu).
- Liste des modèles recopiée dans les tests et `.env.example` (blind) — low, rejeté.
- Rang de `gpt-oss:120b-cloud` (Ollama) différent de `openai/gpt-oss-120b` (blind) — low, rejeté : tag distant non installé ici.
- Nouvelles tentatives du SDK sur un 429 (edge) — low, rejeté : bornées par le délai d'inférence de l'app.

## Verification

**Commands:**
- `.venv-app\Scripts\python -m pytest tests/unit tests/app -q` -- expected: tout réussit

**Manual checks (if no CLI):**
- Avec `GROQ_API_KEY` dans `.env` et le cloud autorisé : Discussion avec `openai/gpt-oss-120b`, réponse et badge Cloud ; Arène : juge par défaut Groq (test manuel de l'utilisateur, seul appel réel).
