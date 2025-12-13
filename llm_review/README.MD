# 🕵️‍♂️ LLM Review & Automation Tools

Ce dossier contient l'outillage nécessaire pour **auditer, documenter et optimiser** le projet WaveLocalAI en utilisant... l'IA elle-même.

Il incarne notre philosophie : *"Utiliser l'IA pour construire l'IA"* (AI for AI).

## 📂 Structure du dossier

* **`prepare_review.py`** : Script Python qui scanne tout le projet pour consolider le code.
    * **Nouveauté :** Il lit automatiquement votre fichier `.gitignore` pour exclure les secrets, les logs, les bases de données et les modèles.
    * Il ne scanne que les extensions pertinentes (`.py`, `.md`, `.json`, etc.).
* **`REVIEW_ME.txt`** : Le fichier généré par le script. C'est ce fichier que vous devez envoyer à votre LLM.
* **`prompts/`** : Dossier contenant les instructions (Prompts) optimisées pour chaque tâche.

## 🔄 Ordre d'Exécution Recommandé

Pour une révision complète du projet, nous recommandons d'exécuter les prompts dans cet ordre logique (Assainir > Vérifier > Documenter > Industrialiser) :

1.  **Assainissement du Code :**
    * `prompt_audit.txt` (Analyse critique)
    * `prompt_refactoring.txt` (Nettoyage et optimisation)
    * `prompt_consistency_audit.txt` (Vérification des liens Front/Back)

2.  **Expérience Utilisateur :**
    * `prompt_ux_review.txt` (Amélioration de l'interface)

3.  **Documentation Interne & Tests :**
    * `prompt_docstrings.txt` (Documentation du code)
    * `prompt_tests.txt` (Génération des tests unitaires)

4.  **Documentation Publique :**
    * `prompt_doc_utilisateur.txt` (Aide intégrée)
    * `prompt_readme.txt` (Vitrine GitHub)

5.  **Industrialisation (Ops) :**
    * `prompts/ops/prompt_quality_lock.txt`
    * `prompts/ops/prompt_ci_github.txt`
    * `prompts/ops/prompt_packaging_exe.txt`

## 🚀 Workflow (Mode d'emploi)

Pour lancer une review ou générer de la doc, suivez ces 3 étapes :

### 1. Générer le contexte à jour
À la racine du projet, lancez :

```bash
# Windows
.venv\Scripts\python llm_review/prepare_review.py

# Mac/Linux
.venv/bin/python llm_review/prepare_review.py
```

*Cela va mettre à jour le fichier `llm_review/REVIEW_ME.txt` avec votre dernier code.*

### 2. Choisir votre Prompt
Ouvrez le fichier correspondant à votre besoin dans le dossier `prompts/` et copiez son contenu.

### 3. Prompter le LLM
Dans votre interface IA préférée (ChatGPT, Claude, etc.) :
1.  Collez le contenu du **Prompt**.
2.  Sautez deux lignes.
3.  Collez le contenu de **`REVIEW_ME.txt`** (ou ajoutez le en pièce jointe).

---
**⚠️ Note de Sécurité :** Le script `prepare_review.py` filtre les dossiers sensibles (`.env`, `__pycache__`). Cependant, vérifiez toujours que `REVIEW_ME.txt` ne contient pas de clés API ou de mots de passe avant de l'envoyer à un LLM Cloud.