---
title: 'Modèles cloud routés vers le bon fournisseur'
type: 'bugfix'
created: '2026-09-29'
status: 'done'
baseline_commit: '1e4b9cd820fc7ad25a38996fb9f9b7042d128f23'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/AGENTS.md'
warnings: []
deferred:
  - summary: >-
      Page Agents : le garde-fou mémoire (ResourceManager.check_resources) s'applique aussi à un modèle cloud, avec 4 Go estimés par défaut, et peut libérer la mémoire d'Ollama ou bloquer la demande.
    evidence: |-
      solo.py appelle check_resources(selected_tag) avant le moteur ; estimate_model_ram renvoie 4,0 Go pour un tag absent de MODELS_DB. Antérieur à la story 22 (relevé par l'audit d'alignement).
    location: >-
      src/app/tabs/agent/solo.py
    severity: low
---

<intent-contract>

## Intent

**Problem:** Trois défauts de routage, différés par la story 16.
- **Client OpenAI :** `OpenAIProvider._get_client` appelle `AsyncOpenAI`, qui n'est importé que sous `TYPE_CHECKING`. Le premier vrai appel OpenAI lève donc `NameError`.
- **Page Agents :** l'agent seul (`AgentEngine._initialize_llm`) et l'équipe (`CrewFactory._get_native_llm`) ne connaissent que Mistral et Groq. Un modèle OpenAI ou Anthropic listé part vers Ollama, qui ne le connaît pas.
- **Tag `gpt-oss:20b` :** ce tag Ollama est envoyé à OpenAI par `LLMProviderFactory.get_provider`, à cause de son préfixe `gpt-`. Le conseil d'échec (`states._cloud_provider_name`) le présente aussi comme un modèle OpenAI.

**Approach:**
- Une seule règle, dans `provider_factory` : un nom sans variante (sans « : ») préfixé `gpt-` ou `o1-` va à OpenAI, préfixé `claude-` à Anthropic. Un tag Ollama (`nom:variante`, distant compris) n'est jamais concerné.
- La fabrique, l'agent seul, l'équipe et le conseil d'échec appliquent cette règle.
- Le client OpenAI est créé avec la classe importée au runtime.

## Boundaries & Constraints

**Always:**
- Clients et LLM simulés ou construits hors ligne : aucun appel réseau, aucune clé réelle.
- Clé absente : erreur lisible qui nomme le fournisseur, jamais un repli silencieux sur Ollama.
- Groq, Mistral et Ollama gardent leur routage actuel (Groq par appartenance exacte, d'abord).
- La logique reste dans `src/core`, sans `streamlit`.

**Never:**
- Modifier `src/core/config.py`, `scripts/`, `benchmarks/`, `data/` ou `config/models_catalog.json`.
- Changer la liste des modèles OpenAI ou Anthropic, ou `is_cloud_tag`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Client OpenAI | `OpenAIProvider(api_key="cle")._get_client()`, `openai` installé | Instance du client `openai.AsyncOpenAI`, créée une fois | N/A |
| Agent seul, OpenAI | `gpt-4o-mini`, clé configurée | Modèle LangChain du fournisseur OpenAI (`LLMProvider.get_langchain_model`), jamais `ChatOllama` | Sans clé : `ValueError` qui nomme OpenAI |
| Agent seul, Anthropic | `claude-3-5-haiku-20241022` | Modèle LangChain du fournisseur Anthropic | Sans clé : `ValueError` qui nomme Anthropic |
| Équipe, OpenAI | `gpt-4o` | LLM natif de CrewAI, fournisseur `openai`, modèle `gpt-4o`, clé OpenAI | Sans clé : `ValueError` « Clé API OpenAI manquante. » |
| Équipe, Anthropic | `claude-3-5-sonnet-20241022` | LLM natif, fournisseur `anthropic`, clé Anthropic | Sans clé : `ValueError` « Clé API Anthropic manquante. » |
| Tag Ollama `gpt-` | `gpt-oss:20b`, `gpt-oss:120b-cloud` | Fabrique : fournisseur Ollama ; agent seul : `ChatOllama` ; équipe : `ollama/<tag>` ; conseil d'échec : Ollama | N/A |

</intent-contract>

## Code Map

- `src/core/providers/openai_provider.py:55-63` `_get_client` : `AsyncOpenAI(...)` devient `_AsyncOpenAI(...)`. Le nom n'est défini que sous `TYPE_CHECKING` (l.8-9), la classe runtime est `_AsyncOpenAI` (l.20-26).
- `src/core/providers/provider_factory.py` :
  - `CLOUD_TAG_PREFIXES` (l.19) et `is_cloud_tag` (l.22-46) : le test `":" in tag` précède déjà les préfixes.
  - Ajouter une fonction publique, par exemple `prefixed_cloud_provider(model_tag) -> "openai" | "anthropic" | None`. Elle renvoie None pour un tag vide ou qui contient « : ».
  - `get_provider` (l.113-122) l'emploie à la place de ses deux `startswith`.
- `src/core/agent_engine.py:124-132` `_initialize_llm` : après Groq, un modèle OpenAI ou Anthropic passe par `LLMProvider.get_langchain_model(model_tag, temperature=0.0)`, comme Groq (l.126-127). Sans clé, la fabrique lève déjà un `ValueError` qui nomme le fournisseur (`provider_factory.py:117,122`).
- `src/core/crew_engine.py:73-102` `_get_native_llm` :
  - OpenAI : `LLM(model=f"openai/{tag}", api_key=openai_provider.OPENAI_API_KEY, temperature=…)`.
  - Anthropic : `LLM(model=f"anthropic/{tag}", api_key=anthropic_provider.ANTHROPIC_API_KEY, …)`.
  - Clé vide : `ValueError`, sur le modèle de Groq (l.88-97).
  - Vérifié hors ligne avec CrewAI 1.15.22 : `OpenAICompletion` et `AnthropicCompletion` exposent `.model` sans préfixe, `.api_key` et `.provider`.
- `src/app/states.py:162-176` `_cloud_provider_name` : remplacer les tests `startswith` par la fonction de la fabrique. `gpt-oss:20b` donne alors None, donc le conseil Ollama.
- Tests :
  - `tests/unit/test_llm_provider.py` : routage de la fabrique, `_get_client`, `prefixed_cloud_provider` ;
  - `tests/unit/test_agent_history.py:153-167` : modèle à suivre pour l'agent seul (`object.__new__(AgentEngine)`, `patch` de `get_langchain_model` et `ChatOllama`) ;
  - `tests/unit/test_agent_tools.py:502-524` : modèle à suivre pour l'équipe ;
  - `tests/unit/test_failure_states.py:~355` : table du conseil d'échec.

## Tasks & Acceptance

**Execution:**
- [x] `src/core/providers/openai_provider.py` -- client créé avec `_AsyncOpenAI` -- plus de `NameError`
- [x] `src/core/providers/provider_factory.py` -- `prefixed_cloud_provider`, employé par `get_provider` -- une seule règle, `gpt-oss:20b` reste à Ollama
- [x] `src/core/agent_engine.py`, `src/core/crew_engine.py` -- OpenAI et Anthropic routés vers leur fournisseur, erreur lisible sans clé -- page Agents
- [x] `src/app/states.py` -- conseil d'échec d'après la même règle -- `gpt-oss:20b` local
- [x] `tests/unit/test_llm_provider.py`, `tests/unit/test_agent_history.py`, `tests/unit/test_agent_tools.py`, `tests/unit/test_failure_states.py` -- une ligne de la matrice au moins par test, clients simulés -- non-régression sans réseau
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- retirer les deux entrées de la story 16 traitées ici -- traçabilité

**Acceptance Criteria:**
- Given une clé OpenAI factice et le client `openai.AsyncOpenAI` simulé, when `OpenAIProvider.chat_stream` est appelé, then le client simulé reçoit la requête, sans `NameError`.
- Given la page Agents avec `gpt-4o-mini` choisi et une clé factice, when l'agent seul ou l'équipe est construit, then aucun objet Ollama n'est créé pour ce modèle.

## Spec Change Log

## Review Triage Log

### 2026-09-29 — Review pass
- verdicts: 25 findings — high 0, medium 0, low 21, false 3, maybe-false 1
- findings:
  - `[low]` `[reject]` (edge) tag Ollama sans variante (`gpt-oss`) routé vers OpenAI — les tags viennent de `/api/tags`, toujours avec variante (`:latest`) ; garde plus large pour un cas non rencontré.
  - `[low]` `[reject]` (edge) SDK absent mais clé présente dans l'équipe : ImportError brute — `openai` et `anthropic` sont dans les dépendances figées de l'app.
  - `[low]` `[reject]` (edge) casse ou espaces du tag transmis tels quels à l'équipe — tags issus des listes des fournisseurs, en minuscules exactes ; comparaison insensible à la casse déjà présente avant.
  - `[low]` `[reject]` (edge) même cas pour l'agent seul — même raison.
  - `[low]` `[patch]` (edge) ordre des routes de l'équipe (Mistral d'abord) différent des autres sites — équipe réordonnée : Groq, préfixe, Mistral, Ollama ; test avec `is_api_model` vrai.
  - `[low]` `[patch]` (edge) préfixes dupliqués entre `CLOUD_TAG_PREFIXES` et `_PREFIX_PROVIDERS` — `CLOUD_TAG_PREFIXES` dérivé de la table unique.
  - `[low]` `[patch]` (blind) ordre des routes de l'équipe — même correctif que la ligne edge.
  - `[low]` `[patch]` (blind) préfixes en deux endroits — même correctif.
  - `[low]` `[reject]` (blind) correctif Anthropic hors spec — le corriger reviendrait à éditer la spec ; écart noté au résultat (même `NameError`, une ligne, testé).
  - `[low]` `[patch]` (blind) messages d'erreur sans clé différents, commentaire d'agent_engine trompeur — commentaire corrigé ; le message de la fabrique nomme déjà le fournisseur (règle Always).
  - `[low]` `[reject]` (blind) température refusée par les modèles `o1-` — aucun `o1-*` n'est listé (`AVAILABLE_MODELS`), chemin inatteignable depuis l'interface.
  - `[low]` `[reject]` (blind) routage par préfixe et non par appartenance (`o3-`, `chatgpt-`) — ces noms ne sont pas listés, donc jamais choisis ; règle antérieure.
  - `[low]` `[reject]` (blind) nom en majuscules accepté puis refusé par l'API — même cause que les lignes edge de casse.
  - `[low]` `[reject]` (blind) fixture d'isolation copiée — duplication de test sans effet ; la déplacer dans un conftest est une refonte.
  - `[low]` `[patch]` (blind) température non vérifiée dans le test de l'équipe — assertion ajoutée.
  - `[low]` `[reject]` (blind) tests de l'équipe sans assertion « jamais Ollama » directe — `llm.provider` vaut `openai` ou `anthropic`, ce qui l'établit.
  - `[false]` `[reject]` (blind) tests en erreur d'import dans le venv du benchmark — `tests/unit` exige déjà les dépendances de l'app (crewai, langchain) ; AGENTS.md fait tourner l'app et ses tests dans `.venv-app`.
  - `[low]` `[reject]` (blind) flux Anthropic non testé de bout en bout — la création du client, seul point corrigé, est testée.
  - `[maybe-false]` `[reject]` (blind) aucune vérification manuelle de la page Agents avec une vraie clé — la spec interdit toute clé réelle ; à trancher par une recette avec une clé OpenAI ou Anthropic, que le poste n'a pas.
  - `[low]` `[patch]` (blind) docstring « via LiteLLM » périmée — corrigée.
  - `[false]` `[reject]` (blind) deferred-work ne reçoit que des retraits — les différés de la revue sont ajoutés à la finalisation.
  - `[low]` `[defer]` (intent) garde-fou mémoire appliqué à un modèle cloud sur la page Agents — antérieur, hors de l'intention ; différé.
  - `[false]` `[reject]` (intent) `is_model_loaded` interroge désormais Ollama pour `gpt-oss:20b` — c'est le comportement voulu : le modèle est local.
  - `[low]` `[patch]` (intent) tests de l'équipe qui forcent `is_api_model` à False — test ajouté avec `is_api_model` vrai (ligne edge d'ordre).
  - `[low]` `[reject]` (intent) aucune destination de requête vérifiée — contrainte hors ligne de la spec ; routage établi par le type et les attributs des objets.

## Verification

**Commands:**
- `.venv-app\Scripts\python -m pytest tests/unit tests/app -q` -- expected: tout réussit, hors les 4 échecs connus d'AGENTS.md s'ils se produisent
- `uvx ruff check` et `uvx black --check` sur les fichiers touchés -- expected: propres

## Auto Run Result

Status: done

**Résumé.**
- Une seule règle, `prefixed_cloud_provider`, dans `provider_factory` : un nom sans variante préfixé `gpt-` ou `o1-` va à OpenAI, `claude-` à Anthropic.
- La fabrique, l'agent seul, l'équipe et le conseil d'échec l'appliquent, dans le même ordre : Groq, préfixe, Mistral, Ollama.
- `gpt-oss:20b` reste à Ollama.
- Le client OpenAI est créé avec la classe importée au runtime. Écart assumé : le client Anthropic avait le même `NameError` et reçoit le même correctif d'une ligne, testé.

**Fichiers.**
- `src/core/providers/openai_provider.py`, `src/core/providers/anthropic_provider.py` : client créé avec `_AsyncOpenAI` et `_AsyncAnthropic`.
- `src/core/providers/provider_factory.py` : `prefixed_cloud_provider`, table unique des préfixes, `get_provider`.
- `src/core/agent_engine.py` : OpenAI et Anthropic via `LLMProvider.get_langchain_model`.
- `src/core/crew_engine.py` : LLM natifs OpenAI et Anthropic de CrewAI, erreur lisible sans clé, ordre des routes aligné.
- `src/app/states.py` : conseil d'échec d'après la même règle.
- Tests : `tests/unit/test_llm_provider.py`, `test_agent_history.py`, `test_agent_tools.py`, `test_failure_states.py`.
- `_bmad-output/implementation-artifacts/deferred-work.md` : deux entrées de la story 16 retirées, une entrée ajoutée.

**Revue.** 25 constats :
- 8 lignes corrigées, en 5 correctifs, tous low ;
- 1 différé : garde-fou mémoire appliqué à un modèle cloud ;
- 16 rejetés, dont 3 false, pour les raisons notées au journal.

Revue de suivi non recommandée : aucun constat high ou medium n'a été corrigé.

**Vérification.**
- `.venv-app\Scripts\python -m pytest tests/unit tests/app -q` : 976 réussis.
- ruff et black propres.

**Risques résiduels.** Aucun appel réel à OpenAI ni à Anthropic : faute de clé, tout passe par des clients simulés ou construits hors ligne.
