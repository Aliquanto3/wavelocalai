# ROLE
Expert Senior en Python Packaging et Software Architecture. Spécialiste de la distribution d'applications Streamlit/AI pour environnements déconnectés (Air-gapped) et utilisateurs non-techniques.

# TASK: PACKAGING STRATEGY "WAVELOCALAI"
Générer une solution de packaging complète pour transformer une application Streamlit + Ollama en un exécutable autonome (.exe, .app, AppImage) sans dépendance Python locale.

# DATA & CONSTRAINTS
- **Application**: Streamlit + Ollama + LangChain + ChromaDB.
- **Cible**: Consultants/Managers (Zéro CLI, installation < 5min).
- **Standards Qualité**: Approche OOP/Modulaire, compatibilité Mypy (strict) & Ruff, Docstrings Google Format, Tests Pytest (Happy Path & Edge Cases).
- **Gestion Dépendances**: Versions figées (ex: streamlit==1.30.0).

# TECHNICAL CHALLENGES TO RESOLVE
1. Localisation des assets (`streamlit/static`, `runtime`).
2. Point d'entrée via wrapper `multiprocessing` pour éviter les forks infinis sur Windows.
3. Hook PyInstaller pour les imports dynamiques de LangChain/ChromaDB.
4. Gestion des chemins via `sys._MEIPASS` en mode "One-File".

# OUTPUT STRUCTURE (REQUIRED)

## 1. Feasibility Matrix
| Plateforme | Faisabilité | Complexité | Bloquants / Risques |
|------------|-------------|------------|---------------------|

## 2. Implementation Files
Encapsuler chaque fichier dans des quadruples backticks.
- **`run_app.py`**: Script de bootstrap gérant le cycle de vie du serveur Streamlit.
- **`wavelocalai.spec`**: Configuration PyInstaller avancée avec gestion des `datas`, `hidden_imports` et `hooks`.
- **Scripts de Build**: `build_windows.bat`, `build_macos.sh`, `build_linux.sh`.
- **`test_packaging.py`**: Fichier Pytest pour valider la résolution des chemins et la présence des assets.

## 3. User & Dev Documentation
- Prérequis de build (Versions Python, PyInstaller 6.x).
- Guide d'installation "Zero-Config" pour l'utilisateur final.
- Table de Troubleshooting (Erreurs courantes : Protocole Streamlit, DLL manquantes).

## 4. Strategic Alternatives
Proposer une alternative légère si le binaire dépasse 1Go (ex: Portable Python env).

# CONTEXT-LAST INSTRUCTIONS
Analyse d'abord l'arborescence nécessaire pour Streamlit dans un contexte PyInstaller, puis génère le code en respectant la stricte isolation des données utilisateur et l'optimisation des tokens de sortie.
