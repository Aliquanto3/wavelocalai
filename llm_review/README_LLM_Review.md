# 📦 LLM Audit Export Tool

Script Python pour préparer les exports de code source destinés aux audits par LLM (Claude, GPT, etc.).

## 🎯 Objectif

Ce script analyse votre projet Python et génère des fichiers d'export optimisés pour chaque phase d'audit LLM, permettant une analyse systématique et reproductible.

## 🚀 Installation

```bash
# Copier le script dans votre projet
cp prepare_review.py votre_projet/scripts/prepare_review.py

# Aucune dépendance externe requise (Python 3.10+ standard library)
```

## 📋 Utilisation

### Commandes principales

```bash
# Afficher les phases disponibles
.venv\Scripts\python llm_review/prepare_review.py --list-phases
```
```bash
# Afficher les statistiques du projet
.venv\Scripts\python llm_review/prepare_review.py --stats
```
```bash
# Exporter toutes les phases
.venv\Scripts\python llm_review/prepare_review.py
```
```bash
# Exporter une phase spécifique
.venv\Scripts\python llm_review/prepare_review.py --phase 1
```

### Options

| Option | Court | Description |
|--------|-------|-------------|
| `--phase N` | `-p N` | Exporter uniquement la phase N (1-5) |
| `--list-phases` | `-l` | Afficher la liste des phases |
| `--stats` | `-s` | Afficher les statistiques du projet |
| `--root PATH` | `-r PATH` | Spécifier la racine du projet |
| `--output PATH` | `-o PATH` | Spécifier le dossier de sortie |

## 📊 Phases d'Audit

### Phase 1: Architecture & Modularité
- **Focus** : Structure, séparation des responsabilités, patterns de conception
- **Fichiers** : `src/core/`, `src/app/`, fichiers de configuration
- **Prompts associés** : Architecture, Cohérence interne

### Phase 2: Qualité du Code
- **Focus** : Refactoring, duplication, conventions PEP8, typage
- **Fichiers** : Tout le code source Python
- **Prompts associés** : Qualité code, Tests

### Phase 3: Sécurité & Performance
- **Focus** : Vulnérabilités, injections, optimisations mémoire
- **Fichiers** : Code + configuration
- **Prompts associés** : Sécurité, Performance

### Phase 4: UX & Documentation
- **Focus** : Interface utilisateur, documentation technique
- **Fichiers** : `src/app/`, `docs/`
- **Prompts associés** : UX/UI, Documentation

### Phase 5: DevOps & Industrialisation
- **Focus** : CI/CD, packaging, gestion des dépendances
- **Fichiers** : Fichiers de configuration uniquement
- **Prompts associés** : DevOps, Packaging

## 📁 Structure des Exports

```
exports/
├── 00_STRUCTURE.txt           # Arborescence du projet
├── 00_STATS.txt               # Statistiques globales
├── PHASE_1_ARCHITECTURE.txt   # Export phase 1
├── PHASE_2_QUALITE_CODE.txt   # Export phase 2
├── PHASE_3_SECURITE.txt       # Export phase 3
├── PHASE_4_UX_DOCUMENTATION.txt
├── PHASE_5_DEVOPS.txt
├── ALL_CODE.txt               # Tout le code source
├── ALL_DOCUMENTATION.txt      # Toute la documentation
├── ALL_TESTS.txt              # Tous les tests
└── ALL_CONFIG.txt             # Tous les fichiers de config
```

## 📝 Format des Fichiers Exportés

Chaque fichier d'export contient :

1. **Header contextuel** : Phase, description, prompts à utiliser
2. **Statistiques** : Nombre de fichiers, lignes, taille estimée
3. **Index des fichiers** : Tableau récapitulatif avec métadonnées
4. **Arborescence** : Structure du projet
5. **Code source** : Contenu des fichiers avec métadonnées (classes, fonctions)

## 🔧 Configuration

### Modifier la racine du projet

Si le script est placé dans `project/scripts/` :
```python
ROOT_DIR = Path(__file__).parent.parent  # Remonte de 2 niveaux
```

Si le script est à la racine `project/` :
```python
ROOT_DIR = Path(__file__).parent  # Remonte de 1 niveau
```

### Personnaliser les dossiers ignorés

```python
IGNORE_DIRS = {
    ".git", "__pycache__", "venv",
    # Ajouter vos dossiers personnalisés
    "mon_dossier_a_ignorer",
}
```

### Personnaliser les catégories

Modifier la fonction `categorize_file()` pour adapter la logique de classification à votre structure de projet.

## 💡 Workflow Recommandé

1. **Analyse initiale**
   ```bash
   .venv\Scripts\python llm_review/prepare_review.py --stats
   ```
   Vérifier la taille du projet et les catégories détectées.

2. **Export phase 1**
   ```bash
   .venv\Scripts\python llm_review/prepare_review.py --phase 1
   ```
   Commencer par l'audit d'architecture.

3. **Audit LLM**
   - Ouvrir `exports/PHASE_1_ARCHITECTURE_&_MODULARITÉ.txt`
   - Copier le contenu dans Claude
   - Utiliser le prompt d'audit d'architecture

4. **Itérer**
   Répéter pour les phases 2 à 5.

## ⚠️ Limitations

- **Taille des exports** : Pour les projets > 20 000 lignes, les exports peuvent dépasser les limites de contexte des LLM. Utiliser les exports par phase.
- **Fichiers binaires** : Automatiquement ignorés (images, modèles ML, etc.)
- **Encodage** : UTF-8 assumé, les fichiers avec encodage différent peuvent avoir des caractères mal interprétés.

## 🔍 Exemple de Sortie

```
📊 PROJECT STATISTICS
==================================================

📅 Generated: 2025-01-15 10:30:00
📁 Root: /home/user/project

## Global Metrics
- Total files: 45
- Total lines: 12,500
- Total size: 450.00 KB

## Files by Category
- app: 12 files (3,500 lines)
- core: 8 files (4,200 lines)
- config: 5 files (200 lines)
- docs: 10 files (2,100 lines)
- tests: 10 files (2,500 lines)

## Top 20 Imported Modules
- streamlit: 25 imports
- langchain: 18 imports
- pathlib: 15 imports
...
```

## 📄 Licence

MIT License - Libre d'utilisation et de modification.
