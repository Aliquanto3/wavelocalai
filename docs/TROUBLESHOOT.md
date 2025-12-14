# 🛠️ Guide d'Installation & Troubleshooting

Ce guide détaille l'installation de **WaveLocalAI** sur un poste de travail standard (Windows/Mac/Linux), avec un focus particulier sur les environnements d'entreprise sécurisés (Wavestone).

## 1. Prérequis Système

* **Python 3.10+** installé.
* **Ollama** : Le moteur d'inférence local (Application externe).
    * Télécharger : [https://ollama.com/download](https://ollama.com/download)
    * *Vérification* : Ouvrez un navigateur sur `http://localhost:11434`. Vous devez voir "Ollama is running".
* **(Optionnel)** Git pour le versioning.

---

## 2. Installation Pas-à-Pas (Environnement Restreint)

En entreprise, l'exécution de scripts (`activate.ps1` ou `.bat`) est souvent bloquée par les politiques de sécurité. Nous recommandons la méthode de l'**Invocation Directe**.

### A. Création de l'environnement
Pour ne pas polluer votre Python global :

```bash
# À la racine du projet
python -m venv .venv
```

### B. Installation des dépendances (Méthode Robuste)
Au lieu d'activer l'environnement, nous appelons directement son exécutable Python.

**Sous Windows (PowerShell/CMD) :**
```bash
# 1. Mise à jour de pip
.venv\Scripts\python -m pip install --upgrade pip

# 2. Installation des dépendances
.venv\Scripts\python -m pip install -r requirements.txt
```

**Sous Mac/Linux :**
```bash
.venv/bin/python -m pip install -r requirements.txt
```

### C. Gestion des Modèles
Utilisez le script d'administration pour pré-charger les modèles validés :

```bash
# Windows
.venv\Scripts\python scripts/setup_models.py

# Mac/Linux
.venv/bin/python scripts/setup_models.py
```

### D. Lancement de l'Application
```bash
# Windows
.venv\Scripts\python -m streamlit run src/app/Accueil.py
```

---

## 3. 🚨 Troubleshooting (Résolution des Problèmes)

### 🔴 Problème : "Impossible d'exécuter le script / Access Denied"
* **Symptôme :** Erreur rouge dans PowerShell en tentant de faire `.venv\Scripts\activate`.
* **Cause :** La *Execution Policy* de votre machine interdit les scripts non signés.
* **Solution :** N'essayez pas d'activer l'environnement. Utilisez la méthode décrite ci-dessus en préfixant toutes vos commandes par `.venv\Scripts\python`.

### 🔴 Problème : "ModuleNotFoundError: No module named 'distutils'"
* **Symptôme :** Crash au lancement, mentionnant `GPUtil`.
* **Cause :** Vous utilisez Python 3.12+ où le module `distutils` a été supprimé, mais la librairie de détection GPU (`GPUtil`) en a encore besoin.
* **Solution :**
    1.  Assurez-vous que `setuptools` est installé :
        ```bash
        .venv\Scripts\python -m pip install setuptools
        ```
    2.  Le code de `src/core/green_monitor.py` a été patché pour ignorer cette erreur.

### 🔴 Problème : "ModuleNotFoundError: No module named 'langchain_ollama'"
* **Symptôme :** Crash lors de l'ouverture de l'onglet **04 Agent Lab**.
* **Cause :** Il manque une librairie spécifique aux agents.
* **Solution :** Installez le paquet manquant :
    ```bash
    .venv\Scripts\python -m pip install langchain-ollama
    ```

### 🔴 Problème : "Error 400: Model does not support tools"
* **Symptôme :** Dans l'Agent Lab, l'IA répond par une erreur rouge critique.
* **Cause :** Vous essayez d'utiliser un modèle (ex: Falcon 3, AceMath, Phi-3.5) qui n'a pas été entraîné pour le "Tool Calling". Ollama rejette la requête.
* **Solution :** Utilisez uniquement des modèles marqués ✅ dans la liste (Qwen 2.5, Llama 3, Mistral, Hammer).

### 🔴 Problème : "Failed to connect to Ollama" / "Connection refused"
* **Symptôme :** Message d'erreur répété dans la console ou l'interface lors du téléchargement/chat.
* **Cause :** L'application Ollama n'est pas lancée (la librairie Python ne suffit pas, il faut le logiciel).
* **Solution :**
    1.  Lancez l'application "Ollama" depuis le menu Démarrer.
    2.  Vérifiez que l'icône (tête de lama) est présente dans la zone de notification (près de l'heure).
    3.  Vérifiez que `http://localhost:11434` répond.

### 🟡 Problème : Noms de modèles "moches" ou incorrects
* **Symptôme :** Affichage de tags techniques (ex: `hf.co/mradermacher/Hammer2.1...`) au lieu de "Hammer 2.1".
* **Cause :** Le modèle a été installé manuellement et son tag ne correspond pas à `models_db.py`.
* **Solution :**
    1.  Tapez `ollama list` dans un terminal.
    2.  Copiez le `NAME` exact.
    3.  Ajoutez une entrée dans `src/core/models_db.py` avec ce tag précis dans le champ `ollama_tag`.

### 🟡 Problème : "Ma base documentaire est toujours là après redémarrage"
* **Contexte :** Module RAG (03).
* **Explication :** C'est le comportement normal. La base vectorielle (**ChromaDB**) est persistante sur le disque (dossier `data/chroma/`) pour éviter de devoir ré-indexer vos documents à chaque fois.
* **Solution :** Pour effacer la mémoire documentaire, utilisez le bouton rouge **"🗑️ PURGER LA BASE"** dans la barre latérale du module RAG.

### 🟡 Problème : "N/A (CPU Only)" dans le dashboard Hardware
* **Cause :** Pas de carte graphique NVIDIA dédiée, ou drivers CUDA absents.
* **Impact :** Aucun. L'application est conçue pour tourner sur CPU ("Local First"). L'inférence sera juste un peu plus lente.

### 🟡 "L'agent ne trouve pas l'information à cause des accents"
* **Symptôme :** Vous cherchez "Anaël" et l'agent échoue car le modèle a transformé le mot en "Anaçel" ou "Anael".
* **Solution :** Le moteur de recherche interne inclut désormais une normalisation automatique. Si le problème persiste, reformulez votre requête avec des mots-clés simples sans articles.


### 📉 Audit & Benchmark (Script `audit_and_update.py`)
**1. "La RAM mesurée diminue quand le contexte augmente (Swap Detecté)"**
* **Symptôme :** Le rapport indique une RAM de 0.4GB pour un contexte de 32k tokens, alors qu'elle était de 4GB pour 16k tokens.
* **Cause :** Votre machine a saturé sa mémoire physique (RAM). Le système d'exploitation a déplacé la mémoire du modèle sur le disque dur (**Swapping**).
* **Conséquence :** Le script détecte cette anomalie, arrête le test pour ce modèle et ne conserve que le "Max Valid Context" (le dernier avant le swap) pour garantir des métriques de performance fiables.

**2. "Mon nouveau modèle ajouté dans JSON n'est pas détecté"**
* **Symptôme :** Vous avez ajouté un bloc dans `models.json`, mais `setup_models.py` ne l'installe pas et le script d'audit le saute.
* **Cause :** Il manque probablement la clé `"type": "local"` dans votre configuration JSON. Les scripts filtrent les modèles pour ignorer ceux basés sur des API Cloud.
* **Solution :** Ajoutez `"type": "local"` dans l'objet JSON du modèle.

**3. "Logs : ⚠️ Bavard (Max output atteint)"**
* **Explication :** Ce n'est pas une erreur. Cela signifie que le modèle a généré une réponse plus longue que la limite de sécurité (512 tokens) imposée par le benchmark. Le test est considéré comme **VALIDE** (la RAM et la vitesse ont bien été mesurées), le script a simplement coupé la parole au modèle pour passer à la suite.

## 4. 🔧 Problèmes Git & Pre-commit Hooks

### 🔴 Problème : "Unable to read baseline" (detect-secrets)
* **Symptôme :** Le hook `detect-secrets` échoue avec `error: Unable to read baseline` répété plusieurs fois.
* **Cause 1 — BOM UTF-8 :** Le fichier `.secrets.baseline` contient un caractère invisible (BOM) ajouté par certains éditeurs Windows, rendant le JSON invalide.
* **Solution :**
    ```powershell
    # Réécrire le fichier sans BOM
    $content = Get-Content .secrets.baseline -Raw
    [System.IO.File]::WriteAllText("$(Get-Location)\.secrets.baseline", $content, [System.Text.UTF8Encoding]::new($false))
    git add .secrets.baseline
    ```

* **Cause 2 — Version incompatible :** Le baseline a été généré avec une version plus récente de `detect-secrets` que celle utilisée par pre-commit.
* **Symptôme additionnel :** Message `No such 'GitLabTokenDetector' plugin to initialize`.
* **Solution :**
    ```powershell
    # Mettre à jour pre-commit et ses hooks
    pre-commit clean
    pre-commit autoupdate
    pre-commit install
    git add .pre-commit-config.yaml
    ```

---

### 🔴 Problème : isort et ruff modifient les fichiers en boucle
* **Symptôme :** Chaque `git commit` échoue car isort puis ruff modifient le même fichier indéfiniment. Même après `git add .`, le cycle recommence.
* **Cause :** Conflit de configuration entre isort et ruff qui ont des règles de tri d'imports légèrement différentes. Chacun "corrige" ce que l'autre a fait.
* **Solution :** Désactiver le tri d'imports dans ruff (puisque isort s'en charge). Dans `pyproject.toml` :
    ```toml
    [tool.ruff.lint]
    ignore = ["I"]  # "I" = règles isort dans ruff
    ```
* **Alternative :** Supprimer isort et laisser ruff gérer les imports (ruff est plus rapide). Commenter la section isort dans `.pre-commit-config.yaml`.

---

### 🔴 Problème : "Line too long" (E501) bloque le commit
* **Symptôme :** ruff échoue avec plusieurs erreurs `E501 Line too long (XXX > 100)`.
* **Cause :** Des lignes de code dépassent la limite configurée (100 caractères par défaut).
* **Solutions :**
    1. **Ignorer temporairement** (pour débloquer) :
        ```toml
        # Dans pyproject.toml
        [tool.ruff.lint]
        ignore = ["I", "E501"]
        ```
    2. **Corriger manuellement** les lignes concernées en les découpant.
    3. **Augmenter la limite** si 100 est trop restrictif :
        ```toml
        [tool.ruff]
        line-length = 120
        ```

---

### 🟡 Problème : Warnings "legacy alias" et "deprecated settings"
* **Symptôme :** Avertissements ruff mentionnant `The top-level linter settings are deprecated`.
* **Cause :** La syntaxe de configuration ruff a évolué. Les anciennes clés (`select`, `ignore`, `per-file-ignores`) doivent être sous `[tool.ruff.lint]`.
* **Impact :** Aucun bloquant, mais à corriger pour éviter les warnings.
* **Solution :** Migrer la configuration dans `pyproject.toml` :
    ```toml
    # ❌ Ancienne syntaxe (dépréciée)
    [tool.ruff]
    select = ["E", "F"]
    ignore = ["E501"]

    # ✅ Nouvelle syntaxe
    [tool.ruff.lint]
    select = ["E", "F"]
    ignore = ["E501"]
    ```

---

### 🟡 Astuce : Forcer un commit en cas d'urgence
Si les hooks bloquent et que vous devez absolument commit :
```powershell
# Bypass TOUS les hooks (à utiliser avec précaution)
git commit -m "Mon message" --no-verify

# Bypass UN SEUL hook spécifique
$env:SKIP="detect-secrets"; git commit -m "Mon message"
```
⚠️ **Attention :** Pensez à corriger les problèmes sous-jacents avant le prochain commit.

---

### 🟢 Workflow recommandé après échec des hooks
Quand les hooks modifient des fichiers automatiquement :
```powershell
# 1. Les hooks ont modifié des fichiers → les re-stager
git add .

# 2. Relancer le commit (même message)
git commit -m "Mon message"

# 3. Si ça échoue encore, répéter jusqu'à stabilisation
#    (généralement 2-3 itérations max)
```
