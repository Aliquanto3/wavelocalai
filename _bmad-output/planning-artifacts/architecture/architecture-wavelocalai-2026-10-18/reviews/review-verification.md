# Revue de vérification — ARCHITECTURE-SPINE wavelocalai v2

Date : 2026-10-18. Angle : chaque décision a-t-elle été vérifiée dans la réalité plutôt qu'affirmée de mémoire ? Méthode : PyPI JSON, installations jetables `uv run --no-project --python 3.11`, lecture du code installé, devguide Python, docs Ollama, issue Ollama #3368, docs Hatch.

## Verdict

La spine est solide : toutes les versions de la table Stack sont exactes et à jour, et les affirmations techniques majeures se vérifient. Restent des écarts réels (signature `llm_impacts`, erreurs non levées d'ecologits, `dev-mode-dirs` et empaquetage, télémétrie FastAPI) et des précisions à ajouter.

## Tableau de vérification

| Élément | Affirmé | Constaté | Statut |
| --- | --- | --- | --- |
| fastapi | 0.143.5 | PyPI 0.143.5 (2026-10-18) | OK |
| uvicorn | 0.54.0 | 0.54.0 (2026-09-25) | OK |
| pydantic | 2.14.1 | 2.14.1 (2026-10-11) | OK |
| ollama (client) | 0.6.3 | 0.6.3 (2026-09-29) | OK |
| sqlite-vec | 0.1.9 | 0.1.9 (2026-03-31), `vec_version` v0.1.9, SQLite 3.53.1 | OK |
| ecologits | 0.11.3 | 0.11.3 (2026-10-14) | OK |
| fastembed | 0.9.0 | 0.9.0 (2026-10-07) | OK |
| `fastapi.sse.EventSourceResponse` natif | existe | Oui : `EventSourceResponse`, `ServerSentEvent` (champs `data, raw_data, event, id, retry, comment`), `KEEPALIVE_COMMENT = b': ping\n\n'`, `_PING_INTERVAL = 15.0` | OK, le maintien toutes les 15 s est natif |
| Python 3.10 en fin de vie | « depuis octobre 2026 » | devguide : EOL 2026-10-01 ; 3.11 : oct. 2027 ; 3.12 : oct. 2028 | OK |
| Ollama sans endpoint de rerank | oui | docs Ollama sans rerank ; issue #3368 toujours ouverte, commentaires de juin à août 2026 « pas supporté » | OK |
| Chargement hors ligne fastembed | cache local | `TextCrossEncoder(name, cache_dir=d, local_files_only=True)` charge hors ligne ; cache vide : `ValueError` | OK avec réserve (F5) |
| sqlite-vec : suppression | question ouverte | Test (1 chunk, `secure_delete=ON`, DELETE, checkpoint, VACUUM) : le vecteur supprimé n'est plus dans le `.db` ni retrouvé par `MATCH`. Notes de version 0.1.7 : DELETE libère la place seulement quand un chunk entier (~1024 vecteurs) est vidé | Question en partie close (F8) |

## Constats

### F1 — Signature de `llm_impacts` mal recopiée (moyenne)

AD-11 écrit `llm_impacts(provider, model, output_tokens, latency_s, zone)`. La signature réelle (0.11.3) est `llm_impacts(provider, model_name, output_token_count, request_latency, electricity_mix_zone=None)`. Par position cela passe ; en arguments nommés cela lève `TypeError`. La zone est un code ISO 3166-1 alpha-3 (`FRA`) ; par défaut, la zone du centre de données du fournisseur, sinon `WOR`. `ecologits.tracers.utils` n'est pas présenté comme API publique stable.
Correction : recopier la vraie signature dans AD-11, appeler par arguments nommés, ajouter un test de contrat (signature + modèle connu comme `anthropic/claude-sonnet-5-5`), épingler `ecologits==0.11.*`.

### F2 — Les erreurs d'ecologits ne sont pas des exceptions (moyenne)

AD-11 dit « toute exception de mesure donne `unmeasurable` ». Or `llm_impacts` ne lève pas pour un modèle ou une zone inconnus : elle retourne un `ImpactsOutput` dont `errors` est non vide (`ModelNotRegisteredError`, `ZoneNotRegisteredError`), valeurs à `None`, avec un avertissement journalisé (constaté avec `groq/x`). Un adaptateur qui ne teste que `except` produirait un CO₂ vide sans `reason`, ce qu'AD-10 interdit. Les valeurs sont aussi parfois des `RangeValue` (min/max), d'autres fois scalaires (Mistral) : cela alimente `range_mg`.
Correction : AD-11 : « exception ou `errors` non vide » ; `reason` tiré de `errors[0].code`.

### F3 — Couverture ecologits : chiffres du journal périmés, table Groq à qualifier (faible)

Constaté : Anthropic 17 modèles (le journal dit 14), Mistral 34 (exact), OpenAI 92, `huggingface_hub` 176, plus `google_genai` et `cohere`. `openai/gpt-oss-120b` existe sous `huggingface_hub` et donne une mesure ; `claude-sonnet-5-5`, `claude-opus-5-5`, `mistral-medium-3.5`, `gpt-5.5` sont reconnus ; Groq n'est pas un fournisseur. Le catalogue bouge à chaque version. Une entrée Groq vers `huggingface_hub` est une approximation (autre matériel, autre centre de données).
Correction : exiger `estimated: true` pour toute entrée de la table de correspondance ; corriger le chiffre dans le journal.

### F4 — `dev-mode-dirs` et empaquetage (moyenne)

Le pyproject actuel place `dev-mode-dirs = ["."]` sous `[tool.hatch.build.targets.wheel]` avec `packages = ["src"]`. La doc Hatch montre l'option dans `[tool.hatch.build]` et dit qu'elle remplace la détection des chemins du wheel pour les installations en mode dev ; elle ne décrit ni la disposition `src` ni plusieurs entrées. Donc `["." , "src"]` n'est pas documenté. De plus, avec `packages = ["src"]`, un wheel non éditable contient `src/wavelocalai/...` : `import wavelocalai` y casse et le script `wavelocalai-v2` aussi.
Correction : ajouter à AD-2 « valable en installation éditable seulement », et une story de vérification avant le premier lot (`import wavelocalai` et `import src.core` après `uv sync`, sous Windows et Linux) ; placer l'option au bon niveau.

### F5 — Reranker hors ligne : mécanisme non nommé (faible)

Constaté : il faut `local_files_only=True` et le même `cache_dir` que pour le téléchargement ; cache absent : `ValueError("Could not load model ... from any source")` après deux lignes `ERROR` de journal. Sous Windows, avertissement sur l'absence de liens symboliques (cache plus gros, sans conséquence fonctionnelle).
Correction : nommer ces deux paramètres dans AD-17, attraper `ValueError` pour afficher « modèle absent, rerank désactivé ».

### F6 — AD-19 : « sans télémétrie OpenTelemetry » mal cadrée (faible)

FastAPI 0.143.5 a une télémétrie OpenTelemetry native : `FastAPI(telemetry={...})` avec `tracing`, `metrics`, `logs`, `operation_spans`, `auto_configure` ; `opentelemetry-api` est une dépendance obligatoire, le SDK et les exporteurs sont en extras. Sans SDK rien n'est exporté ; `auto_configure` est faux sauf `FASTAPI_OTEL_AUTO_CONFIGURE=true`. La règle ne dit pas quelle option employer, et l'option `logs` enregistre les messages d'exception, ce qui irait contre « aucun texte de prompt dans les journaux ».
Correction : `FastAPI(telemetry={"tracing": False, "metrics": False, "logs": False, "operation_spans": False, "auto_configure": False})` ; ajouter `FASTAPI_OTEL_AUTO_CONFIGURE=false` aux opt-outs, avec test.

### F7 — AD-6 : ce que le SSE natif apporte et ce qu'il reste à écrire (faible)

`ServerSentEvent` accepte `id` et `comment`, donc `id: <seq>` sans `event:` est possible ; `data` est toujours sérialisé en JSON, compatible avec l'enveloppe. Restent à écrire : lecture de `Last-Event-ID`, rejeu, réponse `204` (à décider avant d'ouvrir le flux, donc probablement hors du générateur) et fermeture propre à la déconnexion. Je n'ai pas testé le `204` avec `response_class=EventSourceResponse` ni l'annulation côté client : à couvrir par un test `tests/v2/web` dès la première story.

### F8 — sqlite-vec : question ouverte en partie close (faible)

Mon essai ne retrouve plus le vecteur supprimé après DELETE + checkpoint + VACUUM avec `secure_delete=ON`. Les notes de version disent que l'espace ne se libère que lorsque ~1024 vecteurs d'un chunk sont supprimés, et que DELETE est coûteux. Le risque est donc un résidu d'espace, pas de contenu lisible. À tester sur un lot > 1024 vecteurs dans la story RAG. Le projet est en 0.x : épingler.

## Points non vérifiés

- Client `ollama` 0.6.3 en `AsyncClient` (flux, annulation, `eval_count`/`eval_duration`) : non testé, pas d'Ollama lancé.
- Éventuel endpoint de rerank dans Ollama 0.40.6-rc0 (noté en mémoire) : non vérifié dans les notes de version.
- Borne haute 3.13 : reportée à la bascule, cohérent.
- `codecarbon`, `pypdf`, `python-docx`, SDK cloud : non revérifiés (la spine le dit).
