# Guide de Contribution & Workflow Git

Ce document explique comment gérer le projet, le publier et le mettre à jour en utilisant Visual Studio Code (VS Code).

## Prérequis
- VS Code installé.
- Git installé sur la machine.
- Extension "GitLens" ou support Git natif de VS Code activé.

## 1. Publier le projet sur GitHub (Première fois)
Si le projet est local et n'est pas encore sur GitHub :

1.  **Créer le repo sur GitHub** : Aller sur GitHub, créer un nouveau repository vide (sans README, sans .gitignore car on les a déjà). Copier l'URL (ex: `https://github.com/ton-user/ton-projet.git`).
2.  **Initialiser dans VS Code** :
    - Ouvrir la palette de commande (`Ctrl+Shift+P` ou `Cmd+Shift+P`).
    - Taper `Git: Initialize Repository` et sélectionner le dossier du projet.
3.  **Lier au Remote** :
    - Ouvrir la palette de commande > `Git: Add Remote`.
    - Entrer l'URL copiée à l'étape 1.
    - Nommer le remote `origin`.
4.  **Premier Commit & Push** :
    - Aller dans l'onglet "Source Control" (icône de graphe à gauche).
    - Mettre un message (ex: "Initial commit").
    - Cliquer sur "Commit".
    - Cliquer sur "Publish Branch" (ou Push).

## 2. Workflow Quotidien : Mettre à jour le projet
À chaque fois que tu ajoutes une feature (ex: "Ajout onglet benchmark") :

1.  **Vérifier les changements** : Dans l'onglet "Source Control" de VS Code, tu verras la liste des fichiers modifiés (`M`) ou nouveaux (`U`).
2.  **Stager les changements** : Clique sur le `+` à côté des fichiers que tu veux valider (ou sur le `+` global au survol de "Changes" pour tout prendre).
3.  **Commiter** : Écris un message clair dans la zone de texte (ex: "Feat: ajout du script de benchmark"). Clique sur le bouton "Commit".
4.  **Synchroniser (Push)** : Clique sur le bouton "Sync Changes" (les flèches circulaires) qui apparaît après le commit. Cela envoie ton code sur GitHub.

## 3. Récupérer le projet sur une autre machine
1.  Ouvrir VS Code.
2.  Palette de commande > `Git: Clone`.
3.  Coller l'URL du repo GitHub.

## 🛠️ Développement & Audit

Ce projet inclut ses propres outils d'auto-évaluation basés sur les LLM.
Si vous souhaitez contribuer ou auditer le code, consultez le dossier **[`llm_review/`](llm_review/README.md)** pour générer un contexte de code à jour et utiliser nos prompts de validation.

## ✅ Tests & Qualité

Ce projet inclut une suite de tests unitaires pour valider la robustesse du cœur logique (`src/core`), indépendamment de l'interface graphique.

### Prérequis
Si ce n'est pas déjà fait, installez les outils de test :
```bash
# Windows
.venv\Scripts\python -m pip install pytest pytest-mock

# Mac/Linux
.venv/bin/python -m pip install pytest pytest-mock
```

### Lancer les tests
Pour exécuter l'ensemble de la suite de tests :
```bash
# Windows
.venv\Scripts\python -m pytest tests/

# Mac/Linux
.venv/bin/python -m pytest tests/
```