# Revue d'actualité : spine `bench_qualite` (2026-10-10)

**Angle :** chaque décision engagée a-t-elle été vérifiée sur le web, dans le dépôt ou sur l'outil réel, plutôt qu'affirmée de mémoire ? Versions, existence et adéquation des technologies nommées.

**Méthode :** API JSON de PyPI (métadonnées `requires_python`, `requires_dist`, fichiers de roue), API GitHub (releases, tags, contenus à un tag précis), API Hugging Face, documentation Ollama au tag `v0.40.2`, sources de statsmodels aux tags `v0.14.4` et `v0.15.0`, sources de nltk `v3.10.3`, Microsoft Learn, recherche web pour MiMo. `ollama --version` lancé sur la machine. Toutes les requêtes ont été faites le 2026-10-10.

**Verdict d'ensemble :** les versions de la table Stack et les planchers Python sont exacts et ont bien été relevés le jour même. Les API citées (statsmodels, Ollama, Winnow, Anthropic) existent avec les signatures annoncées. Deux décisions ne résistent pas à la confrontation avec la machine cible et le code amont : le serveur Winnow (Windows non pris en charge, 10 Go de VRAM ou plus) et les dépendances de M-IFEval FR (modèles spaCy inutiles pour le FR, téléchargements NLTK à l'import, piège PyPI). Plusieurs changements amont récents ne sont pas pris en compte : passage des SDK à `httpx2`, contraintes d'échantillonnage de Haiku 5.5, `/v1/systemone` natif dans Ollama, `prompt_eval_cached_count`.

Légende des verdicts : **confirmé**, **dépassé** (vrai autrefois ou incomplet face à l'état actuel), **non vérifié**.

---

## 1. Table Stack : versions et planchers Python

| # | Affirmation du spine | Preuve | Verdict | Correctif |
|---|---|---|---|---|
| 1.1 | httpx ≥ 0.28.1 | PyPI : 0.28.1 est la dernière version, publiée le 2024-12-06, `requires_python >=3.8` ([pypi.org/pypi/httpx/json](https://pypi.org/pypi/httpx/json)). | **confirmé** pour la version, **dépassé** pour le choix (voir F-3) | Voir F-3. |
| 1.2 | numpy ≥ 2.2 (2.2.6 dernière compatible 3.10 ; 2.5.4 exige 3.12) | 2.2.6 : `>=3.10` ; 2.3.0 : `>=3.11` ; 2.5.4 publiée le 2026-10-10T20:02, `>=3.12` ([pypi.org/pypi/numpy/json](https://pypi.org/pypi/numpy/json)). | **confirmé** | Aucun. |
| 1.3 | scipy ≥ 1.15 (1.15.3 dernière compatible 3.10 ; 1.18.1 exige 3.12) | 1.15.3 : `>=3.10` ; 1.16.0 : `>=3.11` ; 1.18.1 (2026-08-21) : `>=3.12` ([pypi.org/pypi/scipy/json](https://pypi.org/pypi/scipy/json)). | **confirmé** | Aucun. |
| 1.4 | statsmodels ≥ 0.14.4 (dernière : 0.15.0) | 0.15.0 (2026-08-27) : `>=3.10`, ajoute la dépendance `formulaic>=1.1.0` ; 0.14.4 : `>=3.9` ; la branche 0.14 continue jusqu'à 0.14.6 ([pypi.org/pypi/statsmodels/json](https://pypi.org/pypi/statsmodels/json)). | **confirmé** | Facultatif : relever le plancher à 0.14.6, ou à 0.15.0 puisqu'elle accepte 3.10. Noter que `formulaic` entre dans le venv. |
| 1.5 | jsonschema ≥ 4.26.0 | Dernière, 2026-01-07, `>=3.10`. | **confirmé** | Aucun. |
| 1.6 | pyyaml ≥ 6.0.3 | Dernière, 2025-09-25. | **confirmé** | Aucun. |
| 1.7 | absl-py 2.5.1, langdetect 1.0.9, nltk 3.10.3, immutabledict 4.3.1, emoji 2.16.0, syllapy 0.8.0 | Toutes sont les dernières versions sur PyPI (absl-py publiée le 2026-10-09 ; langdetect date de 2021, sans `requires_python`). | **confirmé** | Aucun. |
| 1.8 | spacy 3.8.16 | Dernière, 2026-08-24, `<3.15,>=3.9`. Roues Windows cp314 présentes pour spacy, thinc 8.3.13 et blis 1.3.3. | **confirmé** | Voir F-2 : spaCy n'est sans doute pas nécessaire. |
| 1.9 | anthropic ≥ 1.13.0 | Dernière, 2026-10-09, `>=3.10`, dépend de `httpx2<3,>=2.0.0` (pas de `httpx`). | **confirmé** | Voir F-3 et F-4. |
| 1.10 | openai ≥ 3.28.0 | Dernière, 2026-10-09, `>=3.10`, dépend de `httpx2<3,>=2.12.0`. | **confirmé** | Voir F-3. |
| 1.11 | huggingface-hub ≥ 2.2.0 | Dernière, 2026-10-08, `>=3.10.0`, dépend de `httpx2`. | **confirmé** | Aucun. |
| 1.12 | pytest ≥ 9.1.1 | Dernière, 2026-06-19, `>=3.10`. | **confirmé** | Aucun. |
| 1.13 | Ollama 0.40.2 | Dernière release GitHub, 2026-10-08 ([github.com/ollama/ollama/releases/tag/v0.40.2](https://github.com/ollama/ollama/releases/tag/v0.40.2)). `ollama --version` sur la machine : `0.40.2`. | **confirmé** | Voir F-7 (mise à jour automatique). |
| 1.14 | Python ≥ 3.10, venv dédié | Tous les paquets acceptent 3.10. **Réalité machine :** le lanceur `py -0p` ne connaît que Python 3.14 ; `.venv` tourne en 3.14.6. Le venv `.venv-qualite` sera donc en 3.14 et les planchers 3.10 ne seront jamais exercés sur cette machine. | **confirmé**, avec une réserve | Écrire dans le spine que `.venv-qualite` est créé en 3.14 sur tour-rtx3050 et que `spacy <3.15` est le premier plafond qui cassera à une montée de Python. |
| 1.15 | `.venv-qualite` « ignoré par git » | `.gitignore` liste `.venv/` et `.venv-app/`, pas `.venv-qualite/` (le motif `.venv/` ne le couvre pas). | **dépassé** (affirmé, pas encore vrai) | Ajouter `.venv-qualite/` au `.gitignore` dans la story 1. |

## 2. statsmodels (AD-16)

| # | Affirmation | Preuve | Verdict | Correctif |
|---|---|---|---|---|
| 2.1 | `proportion_confint(method="wilson")` | v0.15.0 : `def proportion_confint(count, nobs, alpha: float = 0.05, method="normal", alternative: str = "two-sided")`, avec `"wilson"` parmi les méthodes ([statsmodels/stats/proportion.py@v0.15.0](https://github.com/statsmodels/statsmodels/blob/v0.15.0/statsmodels/stats/proportion.py)). v0.14.4 : même fonction sans `alternative`. | **confirmé** | La valeur par défaut est `"normal"` : imposer `method="wilson"` explicitement (le spine le fait déjà). |
| 2.2 | `mcnemar(exact=True)` | `statsmodels.stats.contingency_tables.mcnemar(table, exact=True, correction=True)` en 0.14.4 et en 0.15.0. Aucune dépréciation (seul `cochrans_q(return_object=)` est déprécié en 0.15). | **confirmé** | Importer depuis `statsmodels.stats.contingency_tables`, pas l'ancien `statsmodels.sandbox.stats.runs`. |
| 2.3 | `multipletests(method="holm")`, valeur par défaut `'hs'` | v0.15.0 : `def multipletests(pvals, alpha=0.05, method="hs", ...)` ; `"hs"` = Holm-Šidák, `"holm"` = Holm-Bonferroni ([statsmodels/stats/multitest.py@v0.15.0](https://github.com/statsmodels/statsmodels/blob/v0.15.0/statsmodels/stats/multitest.py)). Même chose en 0.14.4. | **confirmé** | Garder `method="holm"` explicite ; un test unitaire qui échoue si l'appel omet `method` serait utile. |

## 3. Ollama 0.40.2 (AD-6, AD-7, AD-8, AD-12, AD-13)

Sources : [docs/api.md@v0.40.2](https://github.com/ollama/ollama/blob/v0.40.2/docs/api.md), [docs/openapi.yaml@v0.40.2](https://github.com/ollama/ollama/blob/v0.40.2/docs/openapi.yaml), [docs/capabilities/thinking.mdx@v0.40.2](https://github.com/ollama/ollama/blob/v0.40.2/docs/capabilities/thinking.mdx).

| # | Affirmation | Preuve | Verdict | Correctif |
|---|---|---|---|---|
| 3.1 | `/api/chat` renvoie `done_reason`, `eval_count`, `prompt_eval_count`, `total_duration`, `load_duration`, `prompt_eval_duration`, `eval_duration`, et `message.thinking` en streaming | Tous présents dans le schéma de réponse (OpenAPI l.120-200, 320-400) ; « Partial thinking text when `think` is enabled ». | **confirmé** | Aucun. |
| 3.2 | `tokens.prompt` = somme de `prompt_eval_count` | Le schéma porte aussi **`prompt_eval_cached_count`** (« Number of prompt tokens read from the cache »), et `prompt_eval_duration` ne couvre que les tokens **non** cachés. | **dépassé** (incomplet) | Ajouter `tokens.prompt_cache` (somme de `prompt_eval_cached_count`) à `bq.generation/1` : dans les conversations multi-tours, le cache fausse toute comparaison de `prompt_eval_duration` entre modèles. |
| 3.3 | `think` accepte un booléen ou une chaîne, et une chaîne doit figurer parmi les valeurs listées | OpenAPI `ThinkValue` : `boolean`, `string` ou `null` ; `/api/show` renvoie `thinking: {values, default}`. thinking.mdx : « Unsupported names use the model default. » | **confirmé** ; la vérification exacte d'AD-8 est **nécessaire**, car Ollama retombe sans erreur sur la valeur par défaut | Lire `thinking.values` (et non seulement `capabilities`) dans `/api/show` ; un modèle avec `values: [false]` n'a pas de piste activée. |
| 3.4 | `/api/show` renvoie `capabilities` ; un modèle `decision` existe | `ShowResponse.capabilities: array<string>` ; la création accepte `capabilities` à ajouter, « e.g. `decision` for compatible decision models ». | **confirmé** | Aucun. |
| 3.5 | `/api/ps`, `/api/tags` (digest), `/api/version` existent ; `keep_alive: 0` décharge | Les trois routes sont documentées ; `/api/ps` renvoie aussi `context_length` ; `done_reason: "unload"` est documenté pour `keep_alive: 0`. | **confirmé** | Utiliser `/api/ps.context_length` pour vérifier la chauffe d'AD-13. |
| 3.6 | Digest au format `"sha256:…"` (exemple du manifeste) | L'exemple de `/api/tags` et de `/api/ps` montre un digest hexadécimal **sans** préfixe `sha256:`. | **non vérifié** (le format réel n'est pas certain) | Stocker le digest tel que renvoyé, sans le normaliser, et corriger l'exemple d'AD-7. |
| 3.7 | Tokens de réflexion non séparables ; `eval_count` couvre réflexion et réponse | Aucun champ séparé dans l'OpenAPI. L'issue [#17843](https://github.com/ollama/ollama/issues/17843) (ouverte) le confirme dans le code (`EvalCount` copié avant le découpage thinking/content). L'issue [#14957](https://github.com/ollama/ollama/issues/14957) (fermée le 2026-09-15) : avec `format` et `think`, l'inférence se fait **en deux passes** et les tokens de réflexion étaient comptés en `prompt_eval` ; corrigé depuis. | **confirmé** | Mentionner dans AD-6 que `format` + `think` déclenche deux passes (à couvrir par la revérification du 2026-11-01, avec #18774). |
| 3.8 | Issue #18774 (`format` avec `think`) | Existe : « Gemma4: JSON schema format is not enforced when think:true answers directly without reasoning », ouverte le 2026-10-03 ([#18774](https://github.com/ollama/ollama/issues/18774)). | **confirmé** | Aucun. |
| 3.9 | Ollama recharge le modèle quand `num_ctx` change (AD-13) | Ni la FAQ ni context-length.mdx à v0.40.2 ne le disent. | **non vérifié** | Le vérifier au pilote (`/api/ps.context_length` et `load_duration` > 0 sur la première requête d'un nouveau palier). L'ordonnancement d'AD-13 reste sûr dans tous les cas. |
| 3.10 | Différé : `OLLAMA_NUM_PARALLEL=1` impossible à vérifier | FAQ v0.40.2 : « `OLLAMA_NUM_PARALLEL` … default 1 ». | **dépassé** (le problème est plus simple qu'annoncé) | Il suffit de vérifier que la variable n'est pas définie (environnement utilisateur et système Windows), ou qu'elle vaut 1. |
| 3.11 | Ollama « figé » pour la campagne | FAQ v0.40.2 : « Ollama on macOS and Windows will automatically download updates », appliquées au redémarrage. | **dépassé** (le gel n'est pas acquis par défaut) | Voir F-7. |

## 4. Juge local Winnow (AD-15)

| # | Affirmation | Preuve | Verdict | Correctif |
|---|---|---|---|---|
| 4.1 | `EldanRing/Winnow-E4B` existe, publié le 2026-09-24, Apache-2.0, GGUF Q8_0 8,01 Go et BF16 15,05 Go | API HF : `createdAt 2026-09-24T12:18:28Z`, `lastModified 2026-10-06`, `license:apache-2.0`, base `google/gemma-4-E4B-it`, fichiers `gguf/Winnow-E4B-Q8_0.gguf` (8,01 Go) et `-BF16.gguf` (15,05 Go) ([huggingface.co/EldanRing/Winnow-E4B](https://huggingface.co/EldanRing/Winnow-E4B)). | **confirmé** | Aucun. |
| 4.2 | Serveur `EldanRing/winnow-inference`, MIT, poussé le 2026-10-06, dérivé de llama.cpp | API GitHub : créé le 2026-09-21, `pushed_at 2026-10-06T19:06:31Z`, MIT, description « Local typed decisions, chat and vision with Winnow-12B and llama.cpp » ([github.com/EldanRing/winnow-inference](https://github.com/EldanRing/winnow-inference)). | **confirmé** | Aucun. |
| 4.3 | `/v1/systemone` avec des questions `noul`, verdict = probabilité ≥ 0,5 | [docs/API.md](https://github.com/EldanRing/winnow-inference/blob/main/docs/API.md) : `POST /v1/systemone`, `{"type":"noul","noul":p_true}`, 1 à 256 questions par requête, enveloppe `{model, answers, usage}`. Probabilités normalisées sur les seules étiquettes candidates, température 1 par défaut, « not a calibrated correctness guarantee ». Écoute sur `127.0.0.1:8091` ; clé facultative (`WINNOW_API_KEY`). | **confirmé** | Consigner dans `bloquant.juge` la température et le port. Grouper les critères d'une même réponse dans une seule requête (jusqu'à 256 questions) au lieu d'un appel par critère. |
| 4.4 | Le serveur tourne sur la machine cible (Windows, RTX 3050 8 Go) | [docs/INSTALL.md](https://github.com/EldanRing/winnow-inference/blob/main/docs/INSTALL.md) : « The supported serving paths are Linux/NVIDIA CUDA and macOS/Apple Silicon Metal. … **Windows, CPU-only serving, and multi-GPU sharding are not validated release profiles.** » API.md : « CPU-only and multi-GPU model sharding are not release profiles. » Carte HF : texte 8K → pic 8,56 Gio, « **10 GB+ VRAM** ». | **dépassé** : la décision bute sur la plateforme, pas seulement sur la VRAM | Voir F-1. |
| 4.5 | Repli Perplexity Decider v1.1 hébergé | `perplexity-ai/pplx-decider-v1.1-27b` existe sur HF (créé le 2026-10-05). | **confirmé** (existence seulement ; l'hébergement et le prix n'ont pas été vérifiés) | Garder en Différé. |

## 5. Juges cloud (AD-14, AD-15)

| # | Affirmation | Preuve | Verdict | Correctif |
|---|---|---|---|---|
| 5.1 | Message Batches dans le SDK `anthropic` | `src/anthropic/resources/messages/batches.py` à v1.13.0 ([anthropic-sdk-python@v1.13.0](https://github.com/anthropics/anthropic-sdk-python/tree/v1.13.0/src/anthropic/resources/messages)) ; `client.messages.batches.create/retrieve/results`, sans bêta, −50 %, résultats dans un ordre quelconque (à indexer par `custom_id`). | **confirmé** | Indexer les résultats par `custom_id` = clé de jugement. |
| 5.2 | `claude-haiku-5-5` est un identifiant valide | Présent dans `types/model_param.py` à v1.13.0 ; référence API du 2026-10-06 : Haiku 5.5 actuel, 0,10 $ / 0,50 $ par M (prompts ≤ 100K), 1M de contexte. | **confirmé** | Aucun. |
| 5.3 | (implicite) Haiku 5.5 peut jouer un juge déterministe | Référence API : sur Haiku 5.5, `temperature`/`top_p`/`top_k` à une valeur autre que la valeur par défaut → **400** ; réflexion adaptative **active par défaut**, effort par défaut `medium`, désactivable seulement à effort ≤ `high` ; préremplissage de l'assistant → 400. | **dépassé** (non traité par le spine) | Voir F-4. |
| 5.4 | MiMo-V2.6-Pro par le SDK `openai` sur un point d'accès compatible [ASSUMPTION] | Doc officielle Xiaomi ([mimo.mi.com, première requête](https://mimo.mi.com/docs/zh-CN/quick-start/summary/first-api-call)) : OpenAI-compatible `https://api.xiaomimimo.com/v1`, Anthropic-compatible `https://api.xiaomimimo.com/anthropic`, modèle `mimo-v2.6-pro` dans tous les exemples, **Batch API** OpenAI-compatible (`https://batch-api-cn.xiaomimimo.com/v1`, URL dédiée à prendre dans la console). Les noms V2.5 sont redirigés vers V2.6 à partir du 2026-10-21. Prix 0,435 $ / 0,87 $ par M confirmé par OpenRouter et Deep Infra ([computeprices.com](https://computeprices.com/providers/openrouter/models/mimo-v2-6-pro), [llmgateway.io](https://llmgateway.io/models/mimo-v2.6-pro)). | **confirmé** ; l'hypothèse peut être levée | Retirer le point du Différé : base URL `https://api.xiaomimimo.com/v1`, modèle `mimo-v2.6-pro`. Envisager son Batch API (reprise par `lots.jsonl` identique à Haiku). Option : l'endpoint compatible Anthropic permettrait de supprimer la dépendance `openai`. |

## 6. Veille (AD-12)

| # | Affirmation | Preuve | Verdict | Correctif |
|---|---|---|---|---|
| 6.1 | `SetThreadExecutionState(ES_CONTINUOUS \| ES_SYSTEM_REQUIRED \| ES_DISPLAY_REQUIRED)` au lancement, `ES_CONTINUOUS` seul pour rétablir | [Microsoft Learn](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate) : `ES_CONTINUOUS` 0x80000000 « remain in effect until the next call that uses ES_CONTINUOUS and one of the other state flags is cleared » ; `ES_SYSTEM_REQUIRED` 0x1, `ES_DISPLAY_REQUIRED` 0x2 ; l'exemple officiel rétablit avec `SetThreadExecutionState(ES_CONTINUOUS)`. | **confirmé** | Aucun. |
| 6.2 | (implicite) L'état vaut pour le processus | Le paramètre décrit « the **thread's** execution requirements ». La fonction « cannot be used to prevent the user from putting the computer to sleep » (capot, bouton) et n'empêche pas l'économiseur d'écran. | **confirmé**, avec des limites à écrire | Appeler depuis le thread principal qui vit toute la campagne, jamais depuis un thread auxiliaire. Ajouter aux consignes de lancement de garder le capot ouvert et le bouton d'alimentation intact. |

## 7. Correcteurs empruntés : IFBench et M-IFEval FR

| # | Affirmation | Preuve | Verdict | Correctif |
|---|---|---|---|---|
| 7.1 | Dépendances IFBench : absl-py, langdetect, nltk, immutabledict, emoji, syllapy | `pyproject.toml` de [allenai/IFBench](https://github.com/allenai/IFBench) (v0.2.0, poussé le 2026-09-09) : `absl-py, langdetect, nltk, immutabledict, emoji, syllapy>=0.8.0` plus `httpx, tqdm, pydantic>=2, pydantic-settings` (utiles seulement aux scripts de génération). `requirements.txt` cite aussi `spacy`, mais aucun module de `ifbench/` ne l'importe. | **confirmé** pour les correcteurs | Ne copier que `ifbench/instructions*.py`, `classic_instructions.py` et `instructions_util.py`. |
| 7.2 | (implicite) Les correcteurs tournent hors ligne une fois les dépendances installées | `ifbench/instructions_util.py` télécharge à l'exécution `punkt`, `punkt_tab`, `stopwords` et `averaged_perceptron_tagger_eng` s'ils manquent (`nltk.download`) ; `instructions.py` appelle `nltk.word_tokenize` et `nltk.pos_tag`. | **dépassé** (oubli) | Voir F-5. |
| 7.3 | M-IFEval FR exige les modèles spaCy `es_core_news_sm` et `xx_sent_ud_sm` | [lightblue-tech/M-IFEval](https://github.com/lightblue-tech/M-IFEval) : `spacy.load("es_core_news_sm")` dans `instruction_utils/es_instructions_util.py`, `spacy.load("xx_sent_ud_sm")` dans `instructions/es_instructions.py`. **Les fichiers FR n'importent pas spaCy.** Le besoin vient de `instructions_registry.py`, qui importe `en`, `ja`, `es` et `fr` ; le japonais exige aussi `janome` et `ja_sentence_segmenter`, absents du Stack. | **dépassé** (dépendance héritée d'un import global, pas du FR) | Voir F-2. |
| 7.4 | Modèles spaCy « assortis » à 3.8.16 | Les releases GitHub `es_core_news_sm-3.8.0` et `xx_sent_ud_sm-3.8.0` existent (2024-09-30, roues `py3-none-any`) ; `compatibility.json` les donne pour spaCy 3.8. **Piège :** sur PyPI, `es-core-news-sm` est une ancienne publication 3.1.0 qui exige `spacy<3.2.0`, et `xx-sent-ud-sm` n'existe pas. | **confirmé** sur GitHub ; risque d'installation | Si spaCy reste : épingler les URL des roues GitHub 3.8.0 dans `requirements.txt`, ne jamais écrire `es_core_news_sm` nu. |
| 7.5 | (implicite) Le code M-IFEval FR tourne avec nltk 3.10.3 | `fr_instructions_util.py` appelle `nltk.download('punkt_tab')` **à l'import** (sans condition) et `nltk.data.load("nltk:tokenizers/punkt/french.pickle")`. nltk 3.10.3 redirige ce `.pickle` vers `PunktTokenizer("french")` sans pickle ([nltk/data.py@v3.10.3](https://github.com/nltk/nltk/blob/v3.10.3/nltk/data.py), `switch_punkt`), qui lit `punkt_tab`. M-IFEval épingle `nltk==3.9.1` et `spacy==3.7.5`. | **confirmé** (fonctionne), sous réserve d'un test | Supprimer le téléchargement à l'import dans la copie et le signaler dans `PROVENANCE.md` ; ajouter un test de non-régression des vérificateurs FR sous nltk 3.10.3, puisque l'amont a été validé sous 3.9.1. |

## 8. Code existant (AD-1, AD-14)

| # | Affirmation | Preuve | Verdict | Correctif |
|---|---|---|---|---|
| 8.1 | `from src.core.telemetry import disable_telemetry` existe | `src/core/telemetry.py:50` `def disable_telemetry(dotenv_path=None)`, qui pose `HF_HUB_DISABLE_TELEMETRY` et `DO_NOT_TRACK`. | **confirmé** | Aucun. |
| 8.2 | Le test AST de télémétrie couvre `scripts/bench_qualite/` « sans modification » (memlog) | `tests/unit/test_telemetry.py` découvre bien `scripts/**/*.py`, mais `test_every_telemetry_importer_is_listed` échoue tant que le module n'est pas ajouté à la liste figée `TELEMETRY_IMPORTERS`. `datasets` ne figure pas dans `TELEMETRY_ROOTS`, mais il importe `huggingface_hub` par transitivité. | **dépassé** | La story 2 doit ajouter `scripts/bench_qualite/questions/import_publics/<module>.py: ("huggingface_hub", …)` à `TELEMETRY_IMPORTERS`, c'est-à-dire modifier `tests/unit`. |
| 8.3 | `data/bench_qualite/` déjà ignoré | `.gitignore:69` `data/`. | **confirmé** | Aucun. |

---

## Constats principaux et correctifs

### F-1 : Winnow-E4B n'a pas de chemin de service validé sur la machine cible (bloquant pour la story 7)

Le serveur `winnow-inference` ne prend en charge que Linux/CUDA et macOS/Metal ; Windows et le service sur CPU seul « ne sont pas des profils validés ». Le profil texte 8K demande « 10 GB+ VRAM » (pic de 8,56 Gio), alors que tour-rtx3050 tourne sous Windows avec 8 Go. Le Différé ne traite que la VRAM et suppose un déport partiel sur CPU, que l'amont n'a pas validé.

**Correctif :**
1. Requalifier ce point dans le Différé comme un risque **bloquant** : plateforme et VRAM.
2. Écrire AD-15 contre le **contrat** `/v1/systemone` plutôt que contre un serveur. Ollama 0.40.2 expose nativement `/v1/systemone` avec les mêmes questions `noul` depuis v0.35.0 (OpenAPI l.1156 ; modèles `decision` : tev1 4B, nimble 9B, clef-flash 9B, [ollama.com/search?c=decision](https://ollama.com/search?c=decision)). Ce serait un juge local Windows sans second serveur. AD-15 interdit déjà de juger pendant la génération, et AD-8 exclut les modèles `decision` de la génération.
3. Options à mesurer à la story 7 : WSL2 avec CUDA pour winnow-inference, un import de Winnow-E4B dans Ollama avec la capacité `decision` (non vérifié), ou Perplexity Decider hébergé.

### F-2 : les dépendances de M-IFEval FR sont surestimées et incomplètes

Les modèles spaCy ne servent qu'aux vérificateurs **espagnols**. Ils ne sont requis que parce que `instructions_registry.py` importe les quatre langues, ce qui ferait aussi entrer `janome` et `ja_sentence_segmenter`, absents du Stack. Sur PyPI, `es-core-news-sm` est une ancienne publication 3.1.0 incompatible avec spaCy 3.8.

**Correctif :** ne copier que `fr_instructions.py`, `fr_instructions_util.py` et un registre réduit au FR. Retirer `spacy`, `es_core_news_sm` et `xx_sent_ud_sm` du Stack, de la SPEC (« modèles spaCy de M-IFEval compris ») et de la liste des téléchargements préalables. Si l'espagnol doit être conservé, épingler les roues GitHub 3.8.0.

### F-3 : `httpx` 0.28.1 n'évolue plus, et l'écosystème est passé à `httpx2`

httpx n'a pas publié de version depuis le 2024-12-06. anthropic 1.x, openai 3.x et huggingface-hub 2.x dépendent désormais de `httpx2` (Pydantic, 2.13.1 du 2026-09-23, « continuation » de HTTPX, avec `MockTransport`). Le venv contiendra les deux piles. La référence de l'API précise que le SDK `anthropic` rejette les objets venant du paquet `httpx`.

**Correctif :** trancher explicitement dans AD-8. Soit garder `httpx` pour le seul client Ollama, ce qui fonctionne et reste stable, en notant qu'il n'est plus maintenu et qu'il ne faut jamais passer un objet `httpx` aux SDK cloud. Soit écrire le client Ollama sur `httpx2` (même API, `httpx2.MockTransport`) pour n'avoir qu'une pile.

### F-4 : Haiku 5.5 ne peut pas être échantillonné à température 0

Sur Haiku 5.5, une valeur non par défaut de `temperature`, `top_p` ou `top_k` renvoie une erreur 400. La réflexion adaptative est active par défaut avec un effort `medium`, et le préremplissage renvoie aussi 400. Le spine ne dit rien des paramètres de requête du juge cloud.

**Correctif :** dans `bloquant.juge`, consigner pour Haiku l'`effort` (par exemple `low`) et le réglage de réflexion, plutôt qu'une température. Obtenir un verdict booléen par sortie structurée (`output_config.format`) plutôt que par préremplissage. Admettre dans la calibration (CAP-6) que le juge cloud n'est pas déterministe et mesurer sa stabilité par un rejeu.

### F-5 : les données NLTK sont téléchargées à l'exécution

IFBench (`punkt`, `punkt_tab`, `stopwords`, `averaged_perceptron_tagger_eng`) et M-IFEval FR (`punkt_tab`, à l'import) appellent `nltk.download`. La liste des téléchargements préalables à la campagne ne mentionne pas NLTK.

**Correctif :** ajouter les données NLTK aux téléchargements préalables, les ranger sous `BENCH_QUALITE_DATA/nltk_data` (variable `NLTK_DATA`), neutraliser `nltk.download` dans les copies (documenté dans `PROVENANCE.md`), et ajouter un test qui importe les correcteurs sans réseau.

### Autres correctifs (secondaires)

- **F-6 :** ajouter `tokens.prompt_cache` (`prompt_eval_cached_count`) à `bq.generation/1` (3.2).
- **F-7 :** sous Windows, Ollama télécharge ses mises à jour seul et les applique au redémarrage, ce qui ferait arrêter la campagne par AD-7. Couper la mise à jour automatique avant la campagne (ou ne jamais cliquer « Restart to update ») et l'écrire dans les consignes de lancement.
- **F-8 :** `OLLAMA_NUM_PARALLEL` vaut 1 par défaut dans 0.40.2. Le point du Différé se réduit à vérifier que la variable est absente (3.10).
- **F-9 :** stocker le digest de `/api/tags` tel qu'il est renvoyé (l'exemple de la doc n'a pas de préfixe `sha256:`) (3.6).
- **F-10 :** lever l'hypothèse MiMo : `https://api.xiaomimimo.com/v1`, `mimo-v2.6-pro`, Batch API disponible (5.4).
- **F-11 :** ajouter `.venv-qualite/` au `.gitignore` et `import_publics` à `TELEMETRY_IMPORTERS` (1.15, 8.2).
- **F-12 :** vérifier au pilote le rechargement sur changement de `num_ctx`, faute de documentation (3.9).
