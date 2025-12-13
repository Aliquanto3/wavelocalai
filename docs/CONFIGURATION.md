# 📝 Guide de Configuration - WaveLocalAI

Ce document explique comment configurer WaveLocalAI pour différents environnements.

## 🚀 Configuration de Base (Requis)

### 1. Variables d'Environnement

WaveLocalAI utilise des variables d'environnement pour la configuration. Deux méthodes :

**Méthode A : Fichier `.env` (Recommandé)**
```bash
# Copier le template
cp .env.example .env

# Éditer avec vos valeurs
nano .env  # ou notepad .env sur Windows
```

**Méthode B : Variables système**
```bash
# Windows (PowerShell)
$env:WAVELOCAL_COUNTRY_ISO="FRA"
$env:OLLAMA_BASE_URL="http://localhost:11434"

# Linux/Mac
export WAVELOCAL_COUNTRY_ISO="FRA"
export OLLAMA_BASE_URL="http://localhost:11434"
```

### 2. Ollama (Prérequis)

L'application nécessite Ollama pour fonctionner :
```bash
# Vérifier qu'Ollama est lancé
curl http://localhost:11434

# Si erreur, lancer Ollama
ollama serve  # Terminal dédié
```

---

## ⚙️ Configuration Avancée

### Green IT (Empreinte Carbone)
```bash
# .env
WAVELOCAL_COUNTRY_ISO=FRA  # Code pays ISO 3166
WAVELOCAL_PUE=1.0          # 1.0 = Local, 1.4 = Datacenter
```

**Codes pays courants :**
- `FRA` : France (58 gCO2/kWh - mix nucléaire)
- `DEU` : Allemagne (338 gCO2/kWh)
- `USA` : États-Unis (417 gCO2/kWh)
- `CHN` : Chine (681 gCO2/kWh)

### RAG (Embeddings)

Par défaut, WaveLocalAI utilise `all-MiniLM-L6-v2` (léger, CPU-friendly).

**Pour changer de modèle :**
```bash
# .env
WAVELOCAL_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-mpnet-base-v2
```

**Modèles recommandés :**
- `all-MiniLM-L6-v2` : Rapide, multilingue léger (80MB)
- `paraphrase-multilingual-mpnet-base-v2` : Meilleure qualité FR/EN (420MB)
- `all-mpnet-base-v2` : Qualité optimale EN uniquement (420MB)

### Mode Hybride (Local + Cloud)

Pour comparer avec des API externes :
```bash
# .env
MISTRAL_API_KEY=sk-proj-xxxxxxx
OPENAI_API_KEY=sk-xxxxxxx
```

⚠️ **Attention :** En mode cloud, les données **quittent votre machine**.

---

## 🔒 Sécurité

### Validation des Chemins (RAG)

Par défaut, le RAG valide strictement les chemins de fichiers.
```bash
# Désactiver (NON RECOMMANDÉ en production)
ENABLE_PATH_VALIDATION=false
```

### Timeout Calculator (Agent)

Protection contre les expressions mathématiques DOS :
```bash
CALCULATOR_TIMEOUT=2  # Secondes (défaut: 2)
```

---

## 🧪 Configuration pour Tests

**Fichier :** `.env.test` (à créer pour pytest)
```bash
WAVELOCAL_DATA_DIR=./tests/data
WAVELOCAL_CHROMA_COLLECTION=test_collection
DEBUG_MODE=true
```

**Usage :**
```bash
# Charger l'env de test
export $(cat .env.test | xargs)

# Lancer les tests
pytest tests/
```

---

## 📊 Variables Disponibles (Référence)

| Variable | Description | Défaut | Obligatoire |
|----------|-------------|--------|-------------|
| `WAVELOCAL_DATA_DIR` | Dossier de stockage | `./data` | Non |
| `WAVELOCAL_LOGS_DIR` | Dossier logs | `./data/logs` | Non |
| `OLLAMA_BASE_URL` | URL Ollama | `http://localhost:11434` | Non |
| `WAVELOCAL_COUNTRY_ISO` | Code pays ISO | `FRA` | Non |
| `WAVELOCAL_PUE` | PUE datacenter | `1.0` | Non |
| `WAVELOCAL_EMBEDDING_MODEL` | Modèle embedding | `all-MiniLM-L6-v2` | Non |
| `MISTRAL_API_KEY` | Clé API Mistral | (vide) | Non |
| `ENABLE_PATH_VALIDATION` | Validation chemins | `true` | Non |
| `CALCULATOR_TIMEOUT` | Timeout calculs | `2` | Non |

---

## 🐛 Dépannage

**Problème : "Les variables d'environnement ne sont pas chargées"**

Vérifiez que `python-dotenv` est installé :
```bash
pip install python-dotenv
```

Et que `config.py` contient :
```python
from dotenv import load_dotenv
load_dotenv()
```

**Problème : "Ollama connection refused"**

1. Vérifiez qu'Ollama tourne : `ollama list`
2. Vérifiez l'URL : `echo $OLLAMA_BASE_URL`
3. Testez la connexion : `curl http://localhost:11434`

---

*Dernière mise à jour : 13/12/2025*
