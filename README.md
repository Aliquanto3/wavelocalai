# 🌊 WaveLocalAI Workbench

> **Architecture de Démonstration IA | Local First • Green IT • Privacy**

[![Tests](https://github.com/Aliquanto3/wavelocalai/workflows/Tests%20%26%20Quality/badge.svg)](https://github.com/Aliquanto3/wavelocalai/actions)
[![Coverage](https://codecov.io/gh/Aliquanto3/wavelocalai/branch/main/graph/badge.svg)](https://codecov.io/gh/Aliquanto3/wavelocalai)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

[![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://github.com/Aliquanto3/wavelocalai/graphs/commit-activity)
[![GitHub issues](https://img.shields.io/github/issues/Aliquanto3/wavelocalai)](https://github.com/Aliquanto3/wavelocalai/issues)
[![GitHub stars](https://img.shields.io/github/stars/Aliquanto3/wavelocalai?style=social)](https://github.com/Aliquanto3/wavelocalai/stargazers)

---

## 🎥 Démo Rapide

![WaveLocalAI Demo](docs/assets/demo.gif)

**WaveLocalAI** permet d'explorer la puissance des **Small Language Models (SLM)** en environnement 100% local, avec un focus sur la **confidentialité** et l'**impact environnemental**.

### ✨ Points Clés

- 🔒 **Privacy First** : Vos données ne quittent jamais votre machine
- 🌱 **Green IT** : Mesure de l'empreinte carbone en temps réel (CodeCarbon)
- ⚡ **CPU-Optimized** : Fonctionne sans GPU grâce aux modèles quantizés
- 🧪 **Production-Ready** : 107 tests, 86% de couverture, CI/CD

---

## 🚀 Quickstart (5 minutes)
```bash
# 1. Installer Ollama (requis)
# Télécharger sur https://ollama.com

# 2. Cloner le projet
git clone https://github.com/Aliquanto3/wavelocalai.git
cd wavelocalai

# 3. Créer l'environnement virtuel
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Mac/Linux

# 4. Installer les dépendances
pip install -r requirements.txt

# 5. (Optionnel) Pré-charger des modèles
python scripts/setup_models.py

# 6. Lancer l'application
streamlit run src/app/Accueil.py
```

🎉 **L'interface s'ouvre sur http://localhost:8501**

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [Installation](docs/TROUBLESHOOT.md) | Guide détaillé et résolution d'erreurs |
| [Architecture](docs/ARCHITECTURE.md) | Structure technique du code |
| [Fonctionnalités](docs/FEATURES_GUIDE.md) | Guide utilisateur complet |
| [Configuration](docs/CONFIGURATION.md) | Variables d'environnement |
| [Contributing](CONTRIBUTING.md) | Guide de contribution |

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

### 📚 Module 3 : RAG Knowledge
- Interrogation de documents locaux (PDF/TXT/MD)
- Base vectorielle persistante (ChromaDB)
- Observabilité du pipeline (retrieval, context, génération)

### 🤖 Module 4 : Agent Lab
- Agents autonomes avec outils (calculatrice, recherche, horloge)
- Visualisation du raisonnement (Chain of Thought)
- Architecture LangGraph

---

## 🧪 Tests & Qualité
```bash
# Lancer les tests unitaires
pytest tests/unit/ -v

# Tests avec couverture
pytest tests/ --cov=src.core --cov-report=html

# Linting
ruff check src/ tests/
black --check src/ tests/
```

**Métriques actuelles :**
- ✅ **107 tests** (92 unitaires, 15 intégration)
- ✅ **86.5% de couverture**
- ✅ **0 vulnérabilité** critique

---

## 🤝 Contribution

Les contributions sont les bienvenues ! Consultez [CONTRIBUTING.md](CONTRIBUTING.md) pour :

- 🐛 Signaler un bug
- ✨ Proposer une fonctionnalité
- 🔧 Soumettre une Pull Request

**Code de conduite :** Soyez respectueux et constructif.

---

## 📝 Licence

Ce projet est distribué sous licence **MIT** - voir [LICENSE](LICENSE) pour plus de détails.

---

## 👤 Auteur

**Anaël Yahi**
Consultant IA Senior @ [Wavestone](https://www.wavestone.com/fr/)

- LinkedIn : [Anaël Yahi](https://www.linkedin.com/in/ana%C3%ABl-yahi/)
- GitHub : [@Aliquanto3](https://github.com/Aliquanto3)

---

## ⭐ Support

Si ce projet vous est utile, n'hésitez pas à lui donner une ⭐ sur GitHub !

---

## 📊 Stats

![GitHub stars](https://img.shields.io/github/stars/Aliquanto3/wavelocalai?style=social)
![GitHub forks](https://img.shields.io/github/forks/Aliquanto3/wavelocalai?style=social)
![GitHub watchers](https://img.shields.io/github/watchers/Aliquanto3/wavelocalai?style=social)

---

*Développé avec ❤️ pour la communauté IA & Data de Wavestone*
