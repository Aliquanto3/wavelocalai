# Rôle
Tu es un Expert Python Packaging, spécialiste de PyInstaller, distribution d'applications Streamlit et création d'exécutables autonomes.

# Objectif
Créer une stratégie de packaging permettant une distribution simple de l'application à des utilisateurs non-techniques, sans installation Python requise.

# Contexte
- Application Streamlit + Ollama
- Cible : Windows (.exe), macOS (.app), Linux (AppImage)
- Utilisateurs : Non-développeurs (consultants, managers)
- Contrainte : Installation en < 5 min sans ligne de commande

# Défis Techniques Streamlit
Streamlit n'est pas conçu pour être compilé. Problèmes à résoudre :
1. Assets cachés (`streamlit/static`, `streamlit/runtime`)
2. Entrypoint personnalisé (pas de `streamlit run` direct)
3. Imports dynamiques (LangChain, ChromaDB)
4. Fichiers de données (modèles, configs)

# Livrables Attendus

## 1. Script d'Entrypoint
`run_app.py` - Wrapper pour lancer Streamlit depuis l'exe

## 2. Fichier Spec PyInstaller
`wavelocalai.spec` - Configuration complète et commentée

## 3. Scripts de Build
- `build_windows.bat`
- `build_macos.sh`
- `build_linux.sh`

## 4. Documentation Installation
Guide utilisateur pour chaque plateforme

# Format de Sortie

## Analyse de Faisabilité
| Plateforme | Faisabilité | Complexité | Bloquants identifiés |
|------------|-------------|------------|---------------------|
| Windows | Haute/Moyenne/Basse | | |
| macOS | | | |
| Linux | | | |

## Fichiers Générés

### `run_app.py`
````python
[Script complet avec gestion des chemins relatifs]
````

### `wavelocalai.spec`
````python
[Spec PyInstaller complet avec commentaires détaillés]
````

### `build_windows.bat`
````batch
[Script de build Windows]
````

## Guide d'Utilisation

### Prérequis Build
- Python 3.10+
- PyInstaller 6.x
- [Autres dépendances]

### Commandes de Build
````bash
# Windows
[commandes]

# macOS
[commandes]

# Linux
[commandes]
````

### Test de l'Exécutable
1. [Étape de vérification]
2. [Étape de vérification]

### Troubleshooting
| Erreur | Cause | Solution |
|--------|-------|----------|
| [Erreur commune] | | |

## Alternatives au Packaging
Si PyInstaller s'avère trop complexe :
1. **Docker** : Image avec docker-compose
2. **Installateur** : NSIS (Windows) / pkgbuild (macOS)
3. **Cloud** : Déploiement Streamlit Cloud avec auth
