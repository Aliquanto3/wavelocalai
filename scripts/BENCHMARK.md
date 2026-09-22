# 📊 WaveLocalAI - Documentation du Benchmark SLM

## Table des matières

1. [Pourquoi ce benchmark ?](#pourquoi-ce-benchmark-)
2. [Installation et prérequis](#installation-et-prérequis)
3. [Utilisation](#utilisation)
4. [Méthodologie des tests](#méthodologie-des-tests)
5. [Détail des métriques mesurées](#détail-des-métriques-mesurées)
6. [Analyse des outputs](#analyse-des-outputs)
7. [Avantages et limites](#avantages-et-limites)
8. [Annexes](#annexes)

---

## Pourquoi ce benchmark ?

### Contexte

L'adoption des Small Language Models (SLM) auto-hébergés pose des défis spécifiques que les benchmarks académiques traditionnels ne couvrent pas. Ce benchmark se concentre sur **l'opérationnel** et la **frugalité**.

| Besoin opérationnel | Benchmark académique | Notre benchmark |
|---------------------|---------------------|-----------------|
| Expérience utilisateur (UX) ? | ❌ Non mesuré | ✅ **UX Rating** (Latence perçue) |
| Efficience réelle (Qualité/Coût) ?| ❌ Non mesuré | ✅ **Efficiency Grade** (Raisonnement vs CO₂) |
| Conformité juridique ? | ❌ Souvent ignoré | ✅ **Détection de Licence** |
| Le modèle tiendra-t-il en RAM ? | ❌ Non mesuré | ✅ Mesure par palier avec détection de SWAP |
| Robustesse du contexte ? | ⚠️ "Lost-in-the-middle" ignoré | ✅ Test Needle multi-positions (10%, 50%, 90%) |

---

## Installation et prérequis

### Dépendances

```bash
# Système
curl -fsSL [https://ollama.com/install.sh](https://ollama.com/install.sh) | sh
ollama serve

# Python
pip install ollama codecarbon psutil python-dotenv mistralai
```

### Configuration (.env)

```env
# CodeCarbon - Code ISO du pays (Impacte le calcul CO2 selon le mix électrique)
WAVELOCAL_COUNTRY_ISO=FRA
# PUE du datacenter/bureau (Efficacité énergétique du bâtiment)
WAVELOCAL_PUE=1.1
# API Mistral (optionnel)
MISTRAL_API_KEY=your_key_here
```

---

## Utilisation

```bash
# Benchmark complet (tous les modèles locaux)
python benchmark_slm.py

# Tester des modèles spécifiques
python benchmark_slm.py -m qwen2.5:0.5b llama3.2:1b

# Mode "Mise à jour incrémentale" (ne re-teste pas ce qui est fait)
python benchmark_slm.py --skip-tested

# Mode Verbeux (Voir les prompts et réponses complètes pour debug)
python benchmark_slm.py -v

# Activer le raisonnement des modèles "thinking" (désactivé par défaut)
python benchmark_slm.py --thinking on
```

### Le mode raisonnement (`--thinking`)

Par défaut le benchmark envoie `think=False` aux modèles qui déclarent la capacité
`thinking`. C'est volontaire :

- **Équité** : comparer un modèle qui réfléchit 2 000 tokens avant de répondre à un
  modèle qui répond directement ne mesure pas la même chose.
- **Durée** : sans plafond, un seul test fonctionnel peut durer plusieurs minutes.
  Les tests fonctionnels sont en plus limités à `FUNCTIONAL_MAX_TOKENS` (1024).

Utilisez `--thinking on` pour mesurer le potentiel maximal d'un modèle de raisonnement,
en sachant que la comparaison avec les autres n'est alors plus directe.

Les modèles qui écrivent malgré tout leur raisonnement dans la réponse (balises
`<think>`) sont nettoyés avant notation : sinon ils échouent mécaniquement tous les
contrôles de format.

---

## Méthodologie des tests

### 1. Test de montée en contexte
**Protocole** : Envoi de prompts de taille croissante (2K → 128K). À chaque palier, le
prompt de mesure occupe environ la moitié de la fenêtre, afin que la vitesse de lecture
soit mesurée sur un volume réaliste et non sur un coût fixe.
**Détection Swap** : mesurée sur la croissance réelle du fichier d'échange
(`psutil.swap_memory()`) pendant l'inférence. Au-delà de `SWAP_DELTA_THRESHOLD_GB`
(0,5 GB), le modèle pagine sur disque et la montée en contexte s'arrête.

⚠️ **Deux pièges corrigés, tous deux propres aux machines à GPU :**

1. **L'empreinte mesurée est RAM + VRAM.** Les poids vivent en VRAM et la RAM des
   processus Ollama reste proche de zéro : la mesurer seule produisait un faux
   « SWAP détecté » dès le deuxième palier, et le benchmark s'arrêtait à 4K.
2. **Une baisse d'empreinte n'est pas un swap.** Quand le contexte grandit, Ollama
   déplace des couches vers le CPU : la VRAM occupée diminue alors légitimement.
   Ce report est désormais journalisé (`↪️ Report CPU probable`, avec le
   `gpu_offload_pct`) sans interrompre le test.

### 2. Test Needle-in-Haystack (Robustesse)
**Objectif** : Vérifier que le modèle n'oublie pas d'informations selon leur position dans le contexte.
**Protocole** : Insertion d'un "code secret" à **10% (début)**, **50% (milieu)**, et **90% (fin)** du contexte. Le modèle doit réussir les 3 pour valider le niveau.

### 3. Tests Fonctionnels
- **Multilingue** : Test de compréhension et génération avec tolérance aux synonymes (11 langues).
- **Tool Calling** : suite de 4 cas, moyennés (voir ci-dessous).
- **JSON** : 2 schémas, un plat et un imbriqué (objet + tableau + `enum`), validés récursivement.
- **Abstention** : 2 questions sans réponse possible (entité fictive, événement futur).
  Le modèle doit répondre `UNKNOWN` au lieu d'inventer.

#### Suite Tool Calling (4 cas, 1 point chacun)

| Cas | Ce qu'il vérifie |
|-----|------------------|
| `simple_call` | Appelle l'outil et extrait le bon paramètre. |
| `choose_among_tools` | Choisit le bon outil parmi trois (météo, somme, email). |
| `no_call_needed` | **N'appelle pas** d'outil quand la question n'en nécessite pas. |
| `enum_parameter` | Remplit deux paramètres dont un `enum` (`celsius`/`fahrenheit`). |

Le cas `no_call_needed` est discriminant : plusieurs petits modèles appellent un outil
à tort. À l'inverse, certains modèles appellent correctement l'outil dans un cas et
hallucinent la réponse dans un autre — d'où la moyenne plutôt qu'un booléen.

### 4. Tests de raisonnement (14 items, 4 catégories)

`logic`, `arithmetic`, `pattern` et `trap`. Les pièges (`trap`) sont les plus
discriminants : coût de la balle (1,10 €), comparaison 9.11 vs 9.9, nombre de « r »
dans *strawberry*.

La validation dépend du type de réponse attendu : `number` compare le **dernier**
nombre cité (tolère « 17 + 28 = 45 »), `word` exige le mot isolé (évite que « nobody »
valide « no »), `compact` ignore les espaces.

### 5. Tests de suivi d'instructions (8 contraintes strictes)

Nombre exact de mots, préfixe exact, un seul mot en minuscules, CSV de 5 nombres pairs
en ordre décroissant, deux phrases sans markdown, etc. Aucune tolérance : la contrainte
est respectée ou non.

---

## Détail des métriques mesurées

Le benchmark génère trois types de métriques : décisionnelles, techniques et fonctionnelles.

### 1. Métriques Décisionnelles (Stratégique)

Ces métriques synthétiques permettent une prise de décision rapide (Go/No-Go).

| Clé JSON | Métrique | Description & Seuils |
|----------|----------|----------------------|
| `ux_rating` | **Note UX** | Qualifie la fluidité basée sur le TTFT (Time To First Token).<br>⚡ **Instantané** : < 300ms<br>🚀 **Rapide** : < 800ms<br>🐢 **Acceptable** : < 1500ms<br>🐌 **Lent** : > 1500ms |
| `efficiency_grade` | **Efficience** | Ratio entre l'intelligence (Score Raisonnement) et le coût carbone.<br>🟢 **Excellent** : Modèle intelligent et très léger.<br>🟡 **Bon** : Bon compromis.<br>🔴 **Faible** : Trop énergivore pour ses capacités. |
| `detected_license` | **Licence** | Détection automatique via métadonnées Ollama (ex: `Apache 2.0`, `MIT`, `CC-BY-NC`). Permet de valider l'usage commercial. |

### 2. Métriques de Performance & Green IT

| Clé JSON | Métrique | Unité | Description |
|----------|----------|-------|-------------|
| `avg_tokens_per_second` | Vitesse de génération | tok/s | Calculée sur `eval_duration` d'Ollama : **génération pure**, hors chargement et hors lecture du prompt. >30 = temps réel fluide. |
| `prefill_tokens_per_second` | Vitesse de lecture | tok/s | Traitement du prompt (`prompt_eval_duration`). Déterminante en RAG et sur contexte long. |
| `prefill_prompt_tokens` | Taille du prompt | tokens | Prompt calibré à ~50 % du contexte testé (`PREFILL_FILL_RATIO`), pour que la vitesse ci-dessus soit interprétable. |
| `avg_ttft_ms` | Latence ressentie | ms | Premier token sur un **prompt court, modèle déjà chaud** : ce que vit l'utilisateur en conversation. Alimente `ux_rating`. |
| `ttft_full_prompt_ms` | Latence prompt long | ms | Premier token après lecture du prompt calibré, chargement déduit. Représentatif d'un RAG. |
| `load_time_ms` | Chargement | ms | Temps de mise en mémoire du modèle. |
| `gpu_offload_pct` | Placement | % | Part du modèle réellement en VRAM (`ollama ps`). En dessous de 100 %, la vitesse chute fortement. |
| `model_memory_at_max_ctx_gb` | Mémoire | GB | Empreinte RAM + VRAM au contexte maximum validé. |
| `avg_co2_per_1k_tokens` | Empreinte | gCO₂ | Grammes de CO₂ émis pour générer 1000 tokens (environ 750 mots). |
| `ram_usage_at_max_ctx_gb` | Mémoire RAM | GB | RAM des processus Ollama (proche de 0 si tout est en VRAM). |

> Historique : les tok/s incluaient auparavant le temps de chargement, puisque le
> modèle est déchargé avant chaque palier. Un modèle rapide mais lourd à charger
> était donc pénalisé deux fois. Le prompt de mesure faisait par ailleurs une
> quinzaine de tokens : la « vitesse de lecture » ne mesurait qu'un coût fixe
> (386 tok/s affichés contre 2 082 réels pour Qwen 3.5 4B).

### 3. Métriques de Qualité (Scores 0-1)

| Clé JSON | Métrique | Description |
|----------|----------|-------------|
| `quality_scores.reasoning_avg` | Raisonnement | % de réussite sur 14 tests (logique, arithmétique, motifs, pièges). |
| `quality_scores.reasoning_by_category` | Détail | Score par catégorie : `logic`, `arithmetic`, `pattern`, `trap`. |
| `quality_scores.instruction_following_avg` | Suivi | % de réussite sur 8 contraintes de format strictes. |
| `quality_scores.abstention_avg` | Prudence | % de réussite : répondre `UNKNOWN` au lieu d'inventer. |
| `tool_capability.success_rate` | Tools | Moyenne des 4 cas de la suite (0 à 1). |
| `json_capability.schema_compliance_rate` | JSON | Part des 2 schémas parfaitement respectés. |

---

## Analyse des outputs

### Structure du JSON (`models.json`)

Le fichier `models.json` est la source de vérité. Voici un exemple complet d'un modèle benchmarké :

```json
"Qwen 2.5 0.5B Instruct": {
    "ollama_tag": "qwen2.5:0.5b",
    "type": "local",
    "benchmark_stats": {
        "date": "2025-12-15",

        // --- Dimensionnement ---
        "max_validated_ctx": 32768,           // Fenêtre de contexte maximale fiable
        "ram_usage_at_max_ctx_gb": 0.827,     // RAM des processus Ollama (GB)
        "model_memory_at_max_ctx_gb": 0.93,   // Empreinte totale RAM + VRAM (GB)
        "gpu_vram_usage_gb": 0.93,            // VRAM utilisée (si GPU dédié)
        "gpu_offload_pct": 100,               // 100 = modèle entièrement sur GPU

        // --- Performance & UX ---
        "avg_tokens_per_second": 252.1,       // Génération pure (hors chargement)
        "prefill_tokens_per_second": 2081.7,  // Lecture du prompt
        "prefill_prompt_tokens": 2267,        // Taille du prompt de mesure
        "avg_ttft_ms": 113,                   // Prompt court, modèle chaud
        "ttft_full_prompt_ms": 1110,          // Après lecture du prompt calibré
        "load_time_ms": 3400,
        "ux_rating": "⚡ Instantané",

        // --- RSE & Conformité ---
        "detected_license": "Apache 2.0",     // Usage commercial OK
        "efficiency_grade": "🟢 Excellent",   // Très peu de CO2 pour un bon raisonnement
        "total_co2_emissions_kg": 7.88e-05,
        "avg_co2_per_1k_tokens": 5.3e-05,

        // --- Capacités Fonctionnelles ---
        "tool_capability": {
            "function_detection": true,
            "parameter_extraction": true,
            "success_rate": 1.0
        },
        "json_capability": {
            "valid_json_rate": 1.0,
            "schema_compliance_rate": 1.0
        },
        "needle_in_haystack": {               // Test de mémorisation par palier
            "ctx_4k": true,
            "ctx_8k": true,
            "ctx_16k": true,
            "ctx_32k": false                  // Échec à 32k (Lost in the middle ?)
        },
        "quality_scores": {
            "reasoning_avg": 0.21,            // 21% sur les 14 tests
            "reasoning_by_category": {"logic": 0.33, "arithmetic": 0.2, "pattern": 0.33, "trap": 0.0},
            "instruction_following_avg": 0.25,
            "abstention_avg": 0.0,            // invente au lieu de dire UNKNOWN
            "response_variance_avg": 0.0
        }
    }
}
```

### Indicateurs clés à surveiller

#### Matrice de Décision UX (Basée sur TTFT)
| Grade | Latence (ms) | Ressenti Utilisateur |
|-------|--------------|----------------------|
| ⚡ Instantané | < 300 | Comme une UI native. Idéal pour auto-complétion. |
| 🚀 Rapide | 300 - 800 | Très fluide. Idéal pour chat conversationnel. |
| 🐢 Acceptable | 800 - 1500 | Léger délai de réflexion perceptible. |
| 🐌 Lent | > 1500 | L'utilisateur risque de penser que ça a planté. |

#### Matrice Efficience (Raisonnement / CO₂)
Ce score aide à choisir le modèle le plus "Smart & Green".
- **Calcul** : `(Score Raisonnement * 100) / (Grammes CO₂ par 1k tokens)`
- **Interprétation** : Un modèle 70B aura un bon raisonnement mais un CO₂ énorme -> Score efficience faible. Un modèle 3B bien optimisé aura un score excellent.

---

## Avantages et limites

### ✅ Avantages
1. **Reproductibilité** : Prompts fixes, température 0 pour tests fonctionnels.
2. **Vision Holistique** : Combine Technique (RAM), Métier (JSON/Tools) et RSE (CO₂).
3. **Opérationnel** : Les métriques décisionnelles (UX, Licence) permettent un choix rapide.

### ⚠️ Limites
- **CodeCarbon CPU-only** : Sur certaines configurations, seul le CPU est mesuré par défaut.
- **Détection Licence** : Basée sur les métadonnées déclaratives du fichier GGUF/Modelfile. Peut être vide.
- **Biais Linguistique** : Les tests de raisonnement sont majoritairement en anglais pour standardiser le score.
- **Taille de l'échantillon** : 14 + 8 + 4 + 2 + 2 items. Un écart de quelques points
  entre deux modèles n'est pas significatif ; seuls les écarts nets le sont.
- **Contamination** : les pièges classiques (bat and ball, 9.11 vs 9.9, « r » dans
  strawberry) figurent dans les jeux d'entraînement récents. Ils discriminent les
  générations anciennes, moins les modèles 2026.
- **Un seul run par défaut** (`--runs 1`) : à température 0, mais certains backends
  restent non déterministes (routage MoE, batching). Augmentez `--runs` pour un
  verdict serré.
- **Mesures perturbées par la charge machine** : lancez le benchmark au repos. Un
  téléchargement ou une autre application GPU fausse les tok/s.

---

## Annexes

### Contribuer / Ajouter un modèle
Pour ajouter un modèle au benchmark, ajoutez son entrée dans `models.json` avec son tag Ollama, puis lancez :
```bash
python benchmark_slm.py -m votre-modele:tag
```

*Documentation v2.1 - WaveLocalAI Team*
