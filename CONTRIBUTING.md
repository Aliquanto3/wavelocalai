# 🤝 Guide de Contribution & Workflow

Ce document détaille les standards de qualité, le workflow Git et les outils nécessaires pour contribuer au projet **WaveLocalAI**.

## 🛠️ 1. Prérequis & Installation

Avant de commencer, assurez-vous d'avoir :
- **VS Code** installé (avec l'extension "GitLens" recommandée).
- **Git** installé et configuré.
- **Python** (avec l'environnement virtuel activé).

### Récupérer le projet (Clone)
Pour récupérer le projet sur une nouvelle machine :
1. Ouvrir la palette de commande VS Code (`Ctrl+Shift+P` ou `Cmd+Shift+P`).
2. Taper `Git: Clone` et coller l'URL du repository.

---

## ✅ 2. Standards de Qualité & Tests

Nous maintenons un niveau de qualité strict grâce à des tests unitaires et des hooks de pré-validation.

### Tests Unitaires
Validez la robustesse du cœur logique (`src/core`) avant de proposer des changements.

**Prérequis :**
```bash
# Windows
.venv\Scripts\python -m pip install pytest pytest-mock

# Mac/Linux
.venv/bin/python -m pip install pytest pytest-mock
```

**Lancer les tests :**
```bash
# Exécution standard
.venv\Scripts\python -m pytest tests/

# Rapport complet avec couverture
.venv\Scripts\python -m pytest tests/ -v --cov=src.core --cov-report=term-missing
```

### Outils de "Pre-commit"
Le projet utilise des hooks qui se lancent automatiquement à chaque commit :
* **Ruff** : Linter et formateur Python (vérifie le style).
* **Detect-secrets** : Empêche le commit accidentel de clés API ou mots de passe.
* **Fixers** : Nettoyage automatique des espaces en fin de ligne et des sauts de ligne.

---

## 🔄 3. Workflow de Contribution (Quotidien)

Voici la boucle de développement standard à suivre pour chaque fonctionnalité.

### Étape A : Vérifier l'état
Regardez quels fichiers ont été modifiés.
* **VS Code :** Onglet "Source Control".
* **Terminal :** `git status`

### Étape B : Ajouter les fichiers (Stage)
Préparez les fichiers à inclure dans le commit.
* **VS Code :** Cliquez sur le `+` à côté des fichiers.
* **Terminal :**
    ```bash
    git add src/mon_fichier.py  # Fichier spécifique
    git add .                   # Tout ajouter
    ```

### Étape C : Créer le Commit (Validation)
C'est ici que les **vérifications automatiques** se lancent.
* **VS Code :** Entrez un message clair (ex: "Feat: ajout benchmark") et cliquez sur "Commit".
* **Terminal :**
    ```bash
    git commit -m "Type: Description courte de la modification"
    ```

### Étape D : Envoyer (Push) et ouvrir une PR
On ne pousse jamais sur `master`. Travaillez sur une branche préfixée (`fix/`, `feat/`, `docs/`, `chore/`, `bench/`, `audit/`), puis ouvrez une PR, fusionnée par *merge commit* (jamais de *squash*).
* **VS Code :** Créez la branche, cliquez sur "Publish Branch", puis ouvrez la PR sur GitHub.
* **Terminal :**
    ```bash
    git switch -c fix/ma-correction
    git push -u origin fix/ma-correction
    gh pr create
    ```

---

## 🆘 4. Troubleshooting (Hooks & Erreurs)

Si votre commit est rejeté lors de l'Étape C, c'est généralement un hook qui a détecté un problème.

### Cas 1 : "Files were modified by this hook" (Nettoyage auto)
* **Symptôme :** Le commit échoue mais indique "Fixed" ou "Modified" (souvent pour `trailing-whitespace` ou `end-of-file-fixer`).
* **Solution :** Le hook a fait le travail pour vous ! Il suffit d'ajouter les modifications et de recommencer :
    ```bash
    git add .
    git commit -m "Votre message"
    ```

### Cas 2 : Erreur `detect-secrets` (Baseline manquante ou illisible)
* **Symptôme :** Erreur indiquant que le fichier de référence est introuvable ou impossible à lire.
* **Solution :** Générez le fichier `.secrets.baseline` à la racine.

    * **Sur Mac/Linux (Standard) :**
      ```bash
      detect-secrets scan > .secrets.baseline
      ```

    * **Sur Windows (PowerShell) :**
      Le fichier doit être en UTF-8 **sans BOM** : sous Windows PowerShell 5.1, `Out-File -Encoding utf8` ajoute un BOM qui casse detect-secrets. Utilisez le chemin complet si la commande n'est pas reconnue :
      ```powershell
      $content = .venv\Scripts\detect-secrets.exe scan | Out-String
      [System.IO.File]::WriteAllText("$(Get-Location)\.secrets.baseline", $content, [System.Text.UTF8Encoding]::new($false))
      ```

### Cas 3 : Erreur de style (Ruff)
* **Symptôme :** Le terminal affiche une erreur type `SIM102` ou `F401`.
* **Solution :** Ruff essaie souvent de corriger automatiquement. Sinon, lisez l'erreur et ajustez le code manuellement (ex: simplifier des `if` imbriqués).

### Cas 4 : Blocage critique (Bypass d'urgence)
Si un hook bloque à tort (faux positif) ou pour un correctif urgent :
```bash
git commit -m "Message urgent" --no-verify
```
> ⚠️ **Note :** À utiliser avec parcimonie. Ne jamais utiliser `--no-verify` si vous avez touché à des fichiers de configuration sensibles.

---

## 🏗️ 5. Outils Avancés & Initialisation

### Audit via LLM
Ce projet contient ses propres outils d'audit. Consultez le dossier **[`llm_review/`](llm_review/README_LLM_Review.md)** pour utiliser nos prompts de validation.

### Publier un projet local sur GitHub (Première fois)
Si vous partez de zéro :
1.  Créer un repo vide sur GitHub et copier l'URL.
2.  Dans VS Code : `Git: Initialize Repository`.
3.  Ajouter le remote : `Git: Add Remote` > Coller l'URL > Nommer `origin`.
4.  Faire le premier commit et cliquer sur "Publish Branch".
