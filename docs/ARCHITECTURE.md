# 🏗️ Architecture Technique

WaveLocalAI suit une architecture modulaire **"Domain-Driven Design" (DDD) allégée**, séparant strictement l'interface (Frontend) de la logique métier (Core).

## Arborescence

```text
wavelocalai/
├── data/                    # Persistance locale (Ignoré par Git)
│   ├── chroma/              # Base vectorielle (RAG)
│   ├── logs/                # Logs CodeCarbon & App
│   └── sql/                 # Base SQLite (Sessions)
├── scripts/                 # Scripts d'administration (setup_models.py)
└── src/
    ├── app/                 # COUCHE PRÉSENTATION (Streamlit)
    │   ├── Accueil.py          # Point d'entrée
    │   └── pages/           # Modules fonctionnels (Navigation auto)
    │       ├── 01_Socle_Hardware.py
    │       ├── 02_Inference_Arena.py
    │       └── ...
    └── core/                # COUCHE MÉTIER (Backend Logic)
        ├── config.py        # Config centralisée (Chemins, Constantes)
        ├── models_db.py     # Base de données statique des modèles (Metadata)
        ├── llm_provider.py  # Wrapper autour d'Ollama (Abstraction)
        └── green_monitor.py # Wrapper autour de CodeCarbon
```

## Composants Clés

### 1. Le Backend (`src/core`)
C'est le cerveau de l'application. Il ne contient **aucun code d'interface graphique**.
* **`llm_provider.py`** : Façade qui gère la communication avec Ollama. Utilise des générateurs (`yield`) pour le streaming des réponses et des téléchargements.
* **`models_db.py`** : "Single Source of Truth" pour les modèles. Contient le mapping entre les noms conviviaux ("Qwen 2.5 1.5B") et les tags techniques ("qwen2.5:1.5b").
* **`green_monitor.py`** : Service Singleton qui gère le tracking CO2. Il est rendu robuste pour ne pas faire crasher l'app si le hardware n'est pas détecté.

### 2. Le Frontend (`src/app`)
Utilise **Streamlit** en mode Multi-Page.
* Chaque fichier dans `pages/` devient automatiquement un onglet dans la barre latérale.
* Le Frontend "consomme" les services du Core. Il ne doit pas contenir de logique métier complexe.

## Ajouter une fonctionnalité

1.  **Backend :** Créer la logique dans `src/core/` (ex: `rag_engine.py`).
2.  **Interface :** Créer une nouvelle page dans `src/app/pages/` (ex: `03_RAG_Knowledge.py`).
3.  **Dépendances :** Mettre à jour `requirements.txt` si nécessaire.