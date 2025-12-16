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
```

---

## Méthodologie des tests

### 1. Test de montée en contexte
**Protocole** : Envoi de prompts de taille croissante (2K → 128K).
**Détection Swap** : Si la RAM utilisée diminue soudainement (`< 80%` du palier précédent), cela indique que l'OS a déchargé le modèle sur le disque (Swap). Le test s'arrête pour garantir la fiabilité.

### 2. Test Needle-in-Haystack (Robustesse)
**Objectif** : Vérifier que le modèle n'oublie pas d'informations selon leur position dans le contexte.
**Protocole** : Insertion d'un "code secret" à **10% (début)**, **50% (milieu)**, et **90% (fin)** du contexte. Le modèle doit réussir les 3 pour valider le niveau.

### 3. Tests Fonctionnels
- **Multilingue** : Test de compréhension et génération avec tolérance aux synonymes (11 langues).
- **Tool Calling** : Validation stricte des paramètres extraits (ex: ville "Paris" bien détectée).
- **JSON** : Validation de la conformité au schéma (clés requises, types de données).

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
| `avg_tokens_per_second` | Vitesse | tok/s | Vitesse de lecture/génération. >30 est considéré temps réel fluide. |
| `avg_ttft_ms` | Latence | ms | Temps d'attente avant l'affichage du premier caractère. |
| `avg_co2_per_1k_tokens` | Empreinte | gCO₂ | Grammes de CO₂ émis pour générer 1000 tokens (environ 750 mots). |
| `ram_usage_at_max_ctx_gb` | Mémoire | GB | RAM réelle occupée par le modèle chargé au contexte maximum validé. |

### 3. Métriques de Qualité (Scores 0-1)

| Clé JSON | Métrique | Description |
|----------|----------|-------------|
| `quality_scores.reasoning_avg` | Raisonnement | % de réussite sur 5 tests de logique (syllogismes, maths simples). |
| `quality_scores.instruction_following_avg` | Suivi | % de réussite sur le respect de consignes de formatage strictes. |
| `tool_capability.success_rate` | Tools | 1.0 si le modèle détecte la fonction ET extrait les bons paramètres. |
| `json_capability.schema_compliance_rate` | JSON | 1.0 si le JSON généré respecte parfaitement le schéma imposé. |

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
        "ram_usage_at_max_ctx_gb": 0.827,     // RAM requise (GB)
        "gpu_vram_usage_gb": 0,               // VRAM utilisée (si GPU dédié)

        // --- Performance & UX ---
        "avg_tokens_per_second": 36.08,
        "avg_ttft_ms": 1384,
        "ux_rating": "🐢 Acceptable",         // <1500ms

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
            "reasoning_avg": 0.8,             // 80% de réussite aux tests logiques
            "instruction_following_avg": 0.5,
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

---

## Annexes

### Contribuer / Ajouter un modèle
Pour ajouter un modèle au benchmark, ajoutez son entrée dans `models.json` avec son tag Ollama, puis lancez :
```bash
python benchmark_slm.py -m votre-modele:tag
```

*Documentation v2.1 - WaveLocalAI Team*
