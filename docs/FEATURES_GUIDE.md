# 🎮 Guide des Fonctionnalités WaveLocalAI

Voici le détail exhaustif des modules disponibles dans le Workbench **WaveLocalAI**.

---

## 🔋 Module 01 : Socle Hardware & Green IT

Ce module est le tableau de bord de votre audit local. Il permet de vérifier si la machine est prête pour l'IA.

* **Télémétrie Temps Réel :**
    * Affiche l'usage CPU, RAM et VRAM.
    * Détection automatique des GPU NVIDIA et vérification des drivers CUDA.
* **Audit de Configuration :**
    * Détails techniques sur le processeur (Architecture, Cores physiques/logiques) et l'OS.
* **Green Monitor (Impact Carbone) :**
    * Estime l'impact carbone de votre session en temps réel (gCO2eq).
    * **Méthodologie :** Basée sur la librairie **CodeCarbon**.
    * **Calcul :** (TDP Matériel + PUE Datacenter) × Mix Électrique France (ou local).
    * **Mode Low Power :** Si aucun GPU n'est détecté, l'estimation s'adapte automatiquement à une consommation CPU-only.

---

## 🧠 Module 02 : Inférence & Arena

Ce module est le cœur de l'interaction avec les SLM (Small Language Models). Il est divisé en trois onglets pour séparer les usages.

### 💬 Onglet 1 : Chat Interactif (Conversation)
Une interface type "ChatGPT" pour dialoguer librement avec vos modèles.
* **Mémoire Contextuelle :** Le modèle se souvient des échanges précédents de la session.
* **Streaming Fluide :** La réponse s'affiche mot à mot (token par token) pour un ressenti temps réel.
* **Paramètres :**
    * **Température :** Ajustable de 0.0 (Factuel/Code) à 1.0 (Créatif).
    * **Mode Hybride :** Interface préparée pour le basculement entre Local (Ollama) et Cloud (Mistral API).

### 🧪 Onglet 2 : Labo de Tests (Benchmarks)
Un environnement "Stateless" (sans mémoire) pour tester la performance brute sur des tâches précises.
* **Scénarios Prédéfinis :** Bibliothèque de prompts optimisés (Traduction Technique, Extraction JSON, Coding Assistant, Raisonnement).
* **Configuration Avancée :**
    * **System Prompt Éditable :** Permet de modifier radicalement le comportement du modèle (ex: "Tu es un expert JSON strict").
    * **Métriques Techniques :** Affichage post-inférence du débit (Tokens/s), de la latence (s) et du temps de chargement.

### ⚙️ Onglet 3 : Gestionnaire de Modèles (Model Manager)
Une interface d'administration avancée pour gérer votre bibliothèque locale Ollama.
* **Catalogue Enrichi :**
    * Tableau détaillé : Nom, Éditeur, Taille (GB), Paramètres (Totaux/Actifs), Contexte (ex: 32k, 128k).
    * **Smart Names :** Conversion automatique des tags techniques illisibles (ex: `hf.co/...`) en noms clairs.
    * **Liens Documentation :** Accès direct aux fiches modèles (HuggingFace/Mistral) depuis l'interface.
* **Filtres & Recherche :**
    * **Filtre par Langue :** Trouvez instantanément les modèles supportant le Français, le Code, etc.
* **Installation Simplifiée :**
    * **Menu déroulant :** Suggestions curées par Wavestone (Qwen, Mistral, Llama, Gemma, Granite, etc.).
    * **Feedback Visuel :** Barre de progression temps réel lors du téléchargement (Pull).
    * **Saisie Manuelle :** Champ libre pour télécharger n'importe quel modèle du registre Ollama.

---

## 📚 Module 03 : RAG Knowledge (Base Documentaire)

Ce module permet de discuter avec vos propres documents (PDF, TXT) sans que les données ne quittent votre machine.

### 📥 Ingestion & Vectorisation
* **Support Multi-formats :** Upload de fichiers PDF, TXT, MD.
* **Moteur Vectoriel Local :**
    * Utilise **ChromaDB** pour le stockage persistant (les données restent après redémarrage).
    * Utilise le modèle d'embedding **`all-MiniLM-L6-v2`** optimisé pour CPU (rapide et léger).
* **Introspection :** Tableau de bord affichant le nombre exact de "chunks" (morceaux de texte) en base et la liste des fichiers sources indexés.

### 🔎 Recherche & Observabilité
Contrairement aux boîtes noires, ce module montre tout :
* **Step-by-Step Debugging :** Chronométrage précis de chaque étape :
    1.  *Retrieval :* Temps de recherche dans la base vectorielle.
    2.  *Context Assembly :* Temps de préparation du prompt.
    3.  *Génération :* Mesure du **TTFT** (Temps avant le 1er token) et du débit de génération.
* **Transparence des Sources :** Affichage des extraits de texte exacts utilisés par l'IA pour générer sa réponse (lutte contre les hallucinations).

---

## 🤖 Module 04 : Agent Lab (Automation)

Ce module transforme l'IA en agent autonome capable d'agir via des outils, basé sur l'architecture **LangGraph**.

### 🛠️ Outils Disponibles (Tools)
L'agent a accès à des fonctions Python sécurisées :
1.  **🕒 get_current_time :** Accès à l'horloge système (ce que les LLM ne peuvent pas faire seuls).
2.  **🧮 calculator :** Exécution de calculs mathématiques exacts.
3.  **🏢 search_wavestone_internal :** Moteur de recherche simulé (Base de connaissance RH/Projets) avec gestion intelligente des fautes de frappe et accents.

### 🧠 Capacités Cognitives
* **Filtrage Intelligent :** L'interface ne propose que les modèles capables de faire du "Tool Calling" (ex: Qwen 2.5, Mistral) pour éviter les erreurs.
* **Pensée Visible (Chain of Thought) :**
    * Visualisation du raisonnement interne de l'agent (balises `<think>`).
    * Affichage des logs d'exécution : Quel outil est appelé ? Avec quels arguments ? Quel est le résultat ?
* **Mode ReAct :** L'agent suit la boucle *Raisonner -> Agir -> Observer -> Conclure*.

---
*Développé pour Wavestone - Architecture Local First.*