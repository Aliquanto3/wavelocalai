# 🌊 WaveLocalAI Workbench

> **Architecture de Démonstration IA | Local First • Green IT • Privacy**

**WaveLocalAI** est une application d'audit et de démonstration technique conçue pour illustrer la puissance des **SLM (Small Language Models)** en environnement d'entreprise contraint (Offline, CPU-only, Confidentialité stricte).

![Status](https://img.shields.io/badge/Status-Beta-blue) ![Python](https://img.shields.io/badge/Python-3.10%2B-green) ![License](https://img.shields.io/badge/License-Wavestone_Internal-orange)

## 🎯 Objectifs
* **Privacy by Design :** Aucune donnée ne sort de la machine (sauf appel API explicite en mode Hybride).
* **Green IT :** Mesure de l'impact carbone en temps réel (via CodeCarbon) et usage de modèles quantizés.
* **Modulaire :** Architecture scalable pour tester RAG, Agents et Inférence.

## 🚀 Quickstart (Démarrage Rapide)

**Prérequis :** [Ollama](https://ollama.com) doit être installé et lancé.

```bash
# 1. Cloner et aller dans le dossier
git clone https://github.com/votre-repo/wavelocalai.git
cd wavelocalai

# 2. Créer l'environnement virtuel (Windows)
python -m venv .venv
.venv\Scripts\activate   # ou .venv\Scripts\python si restreint

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. (Optionnel) Pré-charger les modèles recommandés
python scripts/setup_models.py

# 5. Lancer le Workbench
streamlit run src/app/Accueil.py
```

## 📚 Documentation
Pour aller plus loin, consultez le dossier `/docs` :

* 🛠️ **[Installation & Troubleshooting](docs/INSTALL_TROUBLESHOOT.md)** : Guide détaillé et résolution des erreurs courantes.
* 🏗️ **[Architecture Technique](docs/ARCHITECTURE.md)** : Comprendre la structure du code (Frontend/Backend) pour contribuer.
* 🎮 **[Guide des Fonctionnalités](docs/FEATURES_GUIDE.md)** : Détail des modules (Socle Hardware, Arena, etc.).

## ⚙️ Administration

Pour gérer votre installation, le dossier [`scripts/`](scripts/README.md) contient des utilitaires d'automatisation.

| Script | Description |
| :--- | :--- |
| **`setup_models.py`** | Installe en masse les modèles requis (`--dry-run` disponible). |
| **`audit_and_update.py`** | Benchmark technique (RAM/CO2) et mise à jour automatique de la configuration. |

> 📖 **Documentation détaillée :** Voir le [README des scripts](scripts/README.md) pour les instructions d'utilisation et les arguments.

## ⚖️ Licence & Citation

Ce projet est distribué sous licence **MIT**.  
C'est une licence permissive : vous êtes libre d'utiliser, modifier et redistribuer ce code, tant que vous créditez l'auteur original.

Voir le fichier [LICENSE](LICENSE) pour plus de détails.

### Comment citer ce projet ?

Si vous utilisez WaveLocalAI dans vos travaux, articles ou outils, merci de me créditer ainsi :

> **Auteur :** [Anaël Yahi](https://www.linkedin.com/in/ana%C3%ABl-yahi/) (Wavestone)  
> **Source :** [Lien vers ton repo GitHub ici]

---
*Développé pour [Wavestone](https://www.wavestone.com/fr/) - Communauté IA & Data.*