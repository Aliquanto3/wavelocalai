# 🌊 WaveLocalAI

**Workbench de démonstration d'IA locale et responsable**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.32+-red.svg)](https://streamlit.io/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-118%20passed-brightgreen.svg)](#)
[![Coverage](https://img.shields.io/badge/coverage-86.5%25-brightgreen.svg)](#)

> 💡 *Démonstration interactive des Small Language Models (SLM) pour Wavestone : Performance, Green IT et Souveraineté des Données.*

---

## 🎯 Vision & Objectifs

WaveLocalAI est un **proof of concept** conçu pour :

1. **🔒 Souveraineté des Données** : Tout reste sur votre machine (0 appel API par défaut)
2. **🌱 Green IT** : Mesure de l'impact carbone temps réel (CodeCarbon)
3. **📊 Comparabilité** : Benchmarks objectifs entre modèles locaux et cloud
4. **🤖 Autonomie** : Agents IA avec outils (calculatrice, recherche, génération de documents)

---

## ⚡ Quick Start

### Prérequis

- **Python 3.10+**
- **Ollama** : [Télécharger ici](https://ollama.com/download)
- *Optionnel :* Clé API Mistral pour comparaison Cloud

### Installation (5 min)

L'application s'installe dans son propre environnement, `.venv-app`, distinct du `.venv` réservé au banc de benchmark sur certaines machines. Les versions exactes sont figées dans `constraints.txt` : toujours installer avec `-c constraints.txt`.

```bash
# 1. Cloner le projet
git clone https://github.com/Aliquanto3/wavelocalai.git
cd wavelocalai

# 2. Créer l'environnement virtuel de l'application
python -m venv .venv-app

# 3. Installer les dépendances aux versions figées (Windows)
.venv-app\Scripts\python -m pip install -r requirements.txt -c constraints.txt

# Mac/Linux
.venv-app/bin/python -m pip install -r requirements.txt -c constraints.txt

# 4. Configurer (optionnel)
cp .env.example .env
# Éditer .env pour ajouter MISTRAL_API_KEY si souhaité

# 5. Télécharger un modèle local
ollama pull qwen2.5:1.5b

# 6. Lancer l'application, depuis la racine du dépôt (Windows)
.venv-app\Scripts\python -m streamlit run src/app/Accueil.py

# Mac/Linux
.venv-app/bin/python -m streamlit run src/app/Accueil.py
```

L'interface s'ouvre sur http://localhost:8501. Par défaut, le serveur n'écoute que sur la machine locale (`.streamlit/config.toml`, `server.address = "localhost"`) : aucune URL réseau n'est annoncée et la télémétrie Streamlit est coupée. Lancer depuis la racine du dépôt : Streamlit ne lit `.streamlit/config.toml` que dans le répertoire courant, sinon le fichier n'est pas lu et le serveur écoute sur le réseau.

**Ouvrir l'application sur le réseau** (démonstration depuis un autre poste) est un choix explicite, à faire au lancement uniquement, sur un réseau de confiance :

```bash
# Windows
.venv-app\Scripts\python -m streamlit run src/app/Accueil.py --server.address 0.0.0.0

# Mac/Linux
.venv-app/bin/python -m streamlit run src/app/Accueil.py --server.address 0.0.0.0
```

Streamlit annonce alors aussi une « Network URL » : l'application et les documents indexés deviennent accessibles aux autres machines du réseau.

**Mettre à jour une dépendance** : modifier `requirements.txt`, puis régénérer `constraints.txt` avec la commande inscrite en tête du fichier (`uv pip compile requirements.txt --universal --python-version 3.10 -o constraints.txt`) et vérifier par une installation réelle.

**Tests** : `python -m pytest tests/unit tests/app` tourne sans Ollama, clé d'API ni réseau. `tests/integration` exige Ollama et `qwen2.5:1.5b` ; les tests marqués `e2e` sont exclus par défaut (`-m e2e` pour les lancer).

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [Installation](docs/TROUBLESHOOT.md) | Guide détaillé et résolution d'erreurs |
| [Architecture](docs/ARCHITECTURE.md) | Structure technique du code |
| [Fonctionnalités](docs/FEATURES_GUIDE.md) | Guide utilisateur complet |
| [Configuration](docs/CONFIGURATION.md) | Variables d'environnement |
| [Contributing](CONTRIBUTING.md) | Guide de contribution |
| [Agent Tools](docs/AGENT_TOOLS.md) | **NOUVEAU** - Documentation des 9 outils agents |

---

## 🎯 Fonctionnalités

### 📋 Module 1 : Socle Hardware & Green IT
- Audit matériel (CPU, RAM, GPU)
- Monitoring carbone temps réel
- Dashboard de télémétrie

### 🧠 Module 2 : Inférence & Arena
- **Chat Libre** : Conversation avec mémoire contextuelle
- **Labo de Tests** : Benchmarks techniques (tokens/s, latence)
- **Model Manager** : Téléchargement et gestion des modèles Ollama
- **Support API Mistral** : Comparaison Local vs Cloud

### 📚 Module 3 : RAG Knowledge
- **Architecture Avancée** : Supporte Naive, HyDE et Self-RAG.
- **EvalOps Intégré** : Benchmark automatique "LLM-as-a-Judge" (Scores Fidélité/Pertinence).
- **Green RAG** : Mesure de l'impact CO2/RAM par requête.
- **Multi-Modèles** : Choix dynamique des Embeddings et Rerankers (Local SOTA).

### 🤖 Module 4 : Agent Lab ⭐ **NOUVEAU**
**Architecture rénovée avec support complet des modèles API**

#### **Mode Solo (Agent Autonome)**
- **9 outils disponibles** (anciennement 3) :
  - 🕒 **Time** : Heure système
  - 🧮 **Calculator** : Calculs mathématiques sécurisés
  - 🏢 **Wavestone Search** : Recherche interne simulée
  - 📧 **Email Sender** : Envoi d'emails via SMTP
  - 📊 **CSV Analyzer** : Analyse de données (Pandas)
  - 📝 **Document Generator** : Création de fichiers DOCX
  - 📈 **Chart Generator** : Génération de graphiques PNG
  - 📄 **Markdown Report** : Rapports structurés MD
  - 💻 **System Monitor** : Métriques CPU/RAM/Disque

- **Sélection dynamique d'outils** : Activez uniquement les outils nécessaires
- **Bibliothèque de 15+ prompts prédéfinis** organisés par catégorie
- **Support modèles API** : Mistral Large, Devstral, Ministral
- **Visualisation du raisonnement** : Chain of Thought visible

#### **Mode Crew (Multi-Agents)**
- **Workflows prédéfinis** : 8+ scénarios d'équipes optimisées
- **Composition flexible** : Jusqu'à N agents avec rôles, objectifs et backstories
- **Sélection d'outils par agent** : Chaque agent a ses propres outils
- **Mix Local/API** : Combinez modèles locaux et cloud dans une même équipe
- **Collaboration avancée** : Délégation et communication inter-agents
- **Logs nettoyés** : Historique complet avec codes ANSI supprimés

**Exemples de workflows Crew :**
- 📊 Étude concurrentielle (3 agents : Chercheur, Analyste, Rédacteur)
- 🔬 Pipeline d'analyse de données complète
- 📈 Rapport exécutif automatisé (4 agents)
- 🎯 Benchmark FinOps/GreenOps comparatif

---

## 🧪 Tests & Qualité

```bash
# Tests unitaires et rendu des pages (sans Ollama, clé d'API ni réseau)
python -m pytest tests/unit tests/app

# Avec couverture
python -m pytest tests/unit tests/app --cov=src.core --cov-report=html

# Tests d'intégration (exigent Ollama et qwen2.5:1.5b)
python -m pytest tests/integration -m integration

# Linting
ruff check src/ tests/
black --check src/ tests/
```

**Métriques actuelles :**
- ✅ **118 tests** (100 unitaires, 18 intégration)
- ✅ **86.5% de couverture**
- ✅ **0 vulnérabilité** critique

**Nouveaux tests :**
- Tests unitaires pour les 9 outils agents
- Tests d'intégration Agent Solo/Crew
- Tests de détection de modèles API vs Local
- Validation des workflows prédéfinis

---

## 🆕 Nouveautés Principales (Décembre 2024)

### 🔧 Architecture Modulaire des Outils
- **Module `model_detector.py`** : Source unique de vérité pour détecter API vs Local
- **Module `agent_tools.py`** : 9 outils avec métadonnées complètes
- **Pattern standardisé** : Fonction pure + wrapper LangChain + métadonnées UI

### 🎨 Refonte Complète des Interfaces
- **Solo** : Sélection d'outils + bibliothèque de prompts + guide intégré
- **Crew** : Workflows prédéfinis + multiselect outils par agent + logs améliorés
- **Cohérence visuelle** : Émojis 🏠 Local / 🌐 API dans tous les logs

### 🌐 Support API Unifié
- **Mistral Large 3** (675B paramètres, 41B actifs)
- **Devstral 2** (123B - Coding & Agents)
- **Ministral 3** (14B/8B/3B - Edge-friendly)
- **Mistral Small 3.2** (24B - General purpose)
- Détection automatique via `data/models.json`

### 📊 Gestion des Fichiers Générés
- Tous les fichiers créés par les outils → `outputs/`
- Nomenclature standardisée : `{type}_{timestamp}.{ext}`
- Support des images dans le chat (affichage direct des PNG/JPG)

---

## 🔧 Configuration Avancée

### Variables d'Environnement (.env)

```bash
# === Clés API (Optionnel) ===
MISTRAL_API_KEY=sk-proj-xxxxx  # Pour modèles Mistral API

# === SMTP pour Email Tool (Optionnel) ===
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=votre-email@gmail.com
SMTP_PASSWORD=votre-app-password

# === Green IT ===
WAVELOCAL_COUNTRY_ISO=FRA  # FRA, DEU, USA...
WAVELOCAL_PUE=1.0          # 1.0=Local, 1.4=Datacenter

# === RAG ===
WAVELOCAL_EMBEDDING_MODEL=all-MiniLM-L6-v2

# === Chemins ===
WAVELOCAL_DATA_DIR=./data
WAVELOCAL_LOGS_DIR=./data/logs
```

### Ajout d'un Nouveau Modèle

Éditer `data/models.json` :

```json
{
    "Mon Nouveau Modèle": {
        "ollama_tag": "mon-modele:latest",
        "type": "local",  // ou "api"
        "editor": "MonIA",
        "size_gb": "5.2 GB",
        "params_tot": "7B",
        "ctx": 8192,
        "capabilities": ["chat", "tools"],
        "role": "assistant_generalist",
        "desc": "Description du modèle"
    }
}
```

**C'est tout !** Le modèle sera automatiquement :
- Détecté comme Local ou API
- Affiché dans les sélecteurs
- Utilisable dans Solo et Crew

---

## 📖 Guide d'Utilisation Rapide

### 1. Chat Simple (Module 2)
```
1. Sélectionner "Inférence & Arena" dans la sidebar
2. Onglet "Chat Interactif"
3. Choisir un modèle (ex: Qwen 2.5 1.5B)
4. Poser une question
```

### 2. Agent avec Outils (Module 4 - Solo)
```
1. Sélectionner "Agent Lab" → Mode Solo
2. Choisir un modèle (ex: Qwen 2.5 3B)
3. Sélectionner les outils (ex: calculator, generate_chart)
4. Charger un prompt prédéfini OU écrire le vôtre
5. Exemple : "Crée un graphique avec les ventes [100, 150, 200]"
```

### 3. Équipe Multi-Agents (Module 4 - Crew)
```
1. Sélectionner "Agent Lab" → Mode Crew
2. Charger un workflow prédéfini (ex: "Pipeline analyse CSV")
3. Ajuster les modèles et outils si nécessaire
4. Lancer la mission
5. Observer la collaboration dans les logs
```

### 4. RAG sur Documents (Module 3)
```
1. Sélectionner "RAG Knowledge"
2. Uploader un PDF/TXT
3. Attendre l'ingestion (quelques secondes)
4. Poser des questions sur le contenu
5. Les sources exactes sont affichées
```

---

## 🤝 Contribution

Les contributions sont les bienvenues ! Consultez [CONTRIBUTING.md](CONTRIBUTING.md) pour :

- 🐛 Signaler un bug
- ✨ Proposer une fonctionnalité
- 🔧 Soumettre une Pull Request

**Processus :**
1. Fork le projet
2. Créer une branche (`git checkout -b feature/AmazingFeature`)
3. Commit les changements (`git commit -m 'Add AmazingFeature'`)
4. Push vers la branche (`git push origin feature/AmazingFeature`)
5. Ouvrir une Pull Request

**Code de conduite :** Soyez respectueux et constructif.

---

## 🗺️ Roadmap

### ✅ Complété (Décembre 2025)
- [x] Support complet des modèles Mistral API
- [x] 9 outils agents (Email, CSV, DOCX, Charts, etc.)
- [x] Workflows multi-agents prédéfinis
- [x] Sélection d'outils dynamique par agent
- [x] Détection unifiée API vs Local
- [x] Logs Crew nettoyés (codes ANSI)
- [x] Affichage des images dans le chat

### 🚀 Court Terme (Q1 2026)
- [ ] Support d'autres providers API (OpenAI, Anthropic)
- [ ] Évaluation automatique des réponses (LLM-as-a-Judge)
- [ ] Export des conversations en PDF/DOCX
- [ ] Mode comparaison side-by-side (Arena)
- [ ] Skills personnalisables (upload de SKILL.md)

### 🛠 Moyen Terme (Q2 2026)
- [ ] Dockerisation complète
- [ ] API REST pour intégration externe
- [ ] Dashboard administrateur (gestion users)
- [ ] Support des modèles multimodaux (Vision)

### 🔮 Long Terme (2026+)
- [ ] Mode "LLM Council" (vote entre modèles)
- [ ] Auto-tuning des prompts système
- [ ] Marketplace de workflows Crew

---

## 📝 Licence

Ce projet est distribué sous licence **MIT** - voir [LICENSE](LICENSE) pour plus de détails.

---

## 👤 Auteur

**Anaël Yahi**
Consultant en Transformation Numérique @ [Wavestone](https://www.wavestone.com/fr/)
Spécialité : IA Générative

- LinkedIn : [Anaël Yahi](https://www.linkedin.com/in/ana%C3%ABl-yahi/)
- GitHub : [@Aliquanto3](https://github.com/Aliquanto3)

---

## 🙏 Remerciements

- **Wavestone** pour le soutien au projet
- **Alibaba (Qwen Team)** et **IBM (Granite)** pour leurs modèles SLM exceptionnels
- **Mistral AI** pour leur API performante
- **Ollama** pour le runtime local
- **LangChain & LangGraph** pour les abstractions agents
- **CrewAI** pour l'orchestration multi-agents

---

## ⭐ Support

Si ce projet vous est utile, n'hésitez pas à :
- ⭐ Lui donner une étoile sur GitHub
- 🐛 Signaler des bugs ou proposer des améliorations
- 📢 Le partager avec vos collègues intéressés par l'IA locale

---

## 📊 Stats

![GitHub stars](https://img.shields.io/github/stars/Aliquanto3/wavelocalai?style=social)
![GitHub forks](https://img.shields.io/github/forks/Aliquanto3/wavelocalai?style=social)
![GitHub watchers](https://img.shields.io/github/watchers/Aliquanto3/wavelocalai?style=social)

---

## 📸 Captures d'Écran

### Agent Solo avec Génération de Graphique
```
[Image montrant : sélection d'outils, prompt, exécution, graphique affiché]
```

### Crew Multi-Agents en Action
```
[Image montrant : 3 agents collaborant, logs de délégation, résultat final]
```

### Comparaison Local vs API
```
[Image montrant : métriques côte à côte Qwen vs Mistral Large]
```

---

*Développé avec ❤️ pour la communauté IA & Data de Wavestone*

**Version :** 2.0.0 (Décembre 2024)
**Dernière mise à jour :** 15/12/2024
