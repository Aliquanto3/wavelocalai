---
id: SPEC-fiabilisation-frontend
companions:
  - ../../../AGENTS.md
  - ../../../docs/audits/frontend-2026-09/SYNTHESE.md
  - ../../planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/DESIGN.md
  - ../../planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md
sources: []
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# Fiabilisation et refonte UI/UX du front Streamlit (WaveLocalAI v1)

## Why

C'est une douleur à résoudre, liée à une échéance d'usage. Deux audits (`poste-rtx3060` et `pro-elitebook-x360`) montrent un front qui ment : import RAG factice, CO₂ affiché ×1000, succès affichés sur des échecs. Ce front expose aussi le serveur au réseau, perd des réponses et ne ressemble ni à Wavestone ni à son propos souverain. Les consultants qui le montrent en avant-vente et en formation interne ne peuvent pas s'y fier. Les constats (E1–E3, F1–F17, U1–U20) sont catalogués dans `SYNTHESE.md`, avec leur fichier et leur ligne.

## Capabilities

- **CAP-1** — Installation reproductible, app confinée
  - **intent:** Un environnement créé à neuf lance toutes les pages avec toutes leurs fonctions, sans rien exposer au réseau.
  - **success:**
    - l'installation depuis le fichier de contraintes réussit, puis `import ragas` réussit ;
    - les 5 pages passent `AppTest` ;
    - `tests/unit` et `tests/app` sont verts sans Ollama ni `data/`, et la CI les exécute sur chaque PR vers `master` ;
    - le démarrage n'annonce que `localhost`.
- **CAP-2** — Ingestion RAG réelle
  - **intent:** Un document importé depuis l'interface est indexé et interrogeable.
  - **success:**
    - après l'upload d'un `.md`, le compteur d'extraits augmente ;
    - la question du document de test obtient la bonne réponse, avec sa source ;
    - un échec affiche une erreur, jamais un succès.
- **CAP-3** — Échecs visibles, états vrais
  - **intent:** Aucun échec n'est présenté comme un succès ni comme une trace, et aucun indicateur n'est écrit en dur.
  - **success:**
    - un timeout affiche « Délai dépassé » et l'Arène continue ;
    - une évaluation impossible affiche « non évalué » ;
    - Ollama arrêté fait passer l'accueil à « Indisponible » ;
    - l'accélérateur affiché est détecté, pas supposé.
- **CAP-4** — Chiffres justes
  - **intent:** Le débit et le carbone affichés sont exacts et comparables au benchmark.
  - **success:**
    - le premier message affiche un débit à ±15 % des suivants, avec le chargement affiché à part ;
    - le CO₂ de session s'écarte de moins de 5 % de la ligne du CSV de CodeCarbon ;
    - une session apparaît dans l'historique.
- **CAP-5** — Défauts adaptés à la machine
  - **intent:** Un utilisateur qui ne touche à rien obtient une démo rapide et locale.
  - **success:**
    - aucun modèle présélectionné ne dépasse la mémoire disponible (`measured_loaded_gb`), et un modèle local passe en premier ;
    - le juge par défaut fait au moins ~4B quand un tel modèle tient ; sinon, un avertissement s'affiche ;
    - l'Arène exige 2 modèles.
- **CAP-6** — Interface à la charte, accessible et cohérente
  - **intent:** L'interface ressemble à Wavestone et se lit sans effort.
  - **success:**
    - zéro violation axe `color-contrast` ou `heading-order` imputable au thème de l'app, en clair comme en sombre ;
    - un seul nom par module et par commande ;
    - des formats `fr-FR` ;
    - aucun emoji décoratif ;
    - aucun avertissement de dépréciation au démarrage.
- **CAP-7** — Souveraineté visible, actions sensibles maîtrisées
  - **intent:** L'utilisateur sait ce qui sort de la machine et valide ce qui est irréversible.
  - **success:**
    - local par défaut ;
    - un badge Local ou Cloud sur chaque modèle et chaque réponse ;
    - l'envoi d'email et le vidage de la base documentaire demandent une confirmation.
- **CAP-8** — Rien ne se perd
  - **intent:** Ce que l'utilisateur a saisi, choisi ou obtenu survit aux reruns.
  - **success:**
    - la réponse de l'agent et le modèle choisi survivent à un changement d'architecture ;
    - une question bloquée par le garde-fou RAM reste visible, avec le besoin expliqué ;
    - le reranker choisi change l'ordre des sources, ou n'est plus proposé.

## Constraints

- **Benchmark :**
  - Ne jamais modifier `scripts/benchmark_slm.py` ni `benchmarks/`.
  - Ce que le benchmark importe de `src/core/` (dont `config.py`) ne change que si une capacité l'exige.
  - Ne jamais toucher l'environnement Python du benchmark (`.venv`) : l'app se teste dans `.venv-app`.
- **Tests :**
  - Les tests unitaires et `AppTest` tournent sans Ollama, sans clé d'API, sans réseau et sans téléchargement de modèle, avec des providers simulés.
  - Les parcours navigateur sont marqués `e2e` et exclus par défaut.
  - Corriger un test, c'est corriger sa cible, ses données ou son marqueur, jamais affaiblir ni sauter son assertion.
- **Données :** ne jamais écrire dans la collection Chroma réelle (`data/chroma`) ni vider `data/` ; les tests utilisent un répertoire temporaire.
- **Choix déjà arrêtés :**
  - local par défaut ;
  - email décoché, avec confirmation humaine ;
  - débit = `eval_count / eval_duration` d'Ollama, avec chargement et durée totale à part ;
  - serveur sur `localhost` ;
  - versions figées dans un fichier de contraintes et vérifiées par une installation réelle (aucune de mémoire) ;
  - tests en pytest.
- **Streamlit :** figer une version dont la documentation confirme le support des réglages de thème de `DESIGN.md`.
- **Thème et polices :**
  - thème par `.streamlit/config.toml` et composants natifs ;
  - aucun framework CSS, aucun CSS injecté pour les couleurs ;
  - polices servies localement ;
  - aucun fichier Aptos versionné, aucun CDN.
- **Contraste des couleurs natives :** une violation de contraste due à une couleur native de Streamlit sans clé de thème (légendes, `st.badge`) est mesurée et listée au rapport de nuit, pas corrigée par CSS.
- **Langue :** textes d'interface en français, identifiants en anglais ; lexique et formats d'`EXPERIENCE.md`.
- **Lint :** ruff, black et isort restent non bloquants dans cette série, car les 18 remarques ruff et les 6 fichiers à reformater par black touchent des fichiers importés par le benchmark.

## Non-goals

- Nouveaux formats d'import.
- Nouvelles fonctionnalités d'agent.
- Refonte de l'architecture des pages.
- Page « Résultats de benchmark », compatibilité mémoire dans la gestion des modèles, export de session : candidates d'une série suivante.
- Spike F15 sur les 112 W de CodeCarbon, qui demande le portable réel.
- Toute modification de la v2.
- Remise en forme globale du code (lint).

## Success signal

- Un consultant lance la démo sur un poste vierge, en local, sans rien régler.
- L'Arène montre en direct qu'un petit modèle local suffit, avec des chiffres justes et le badge Local visible.
- Aucun écran n'affiche un succès qui n'a pas eu lieu.

## Assumptions

- Les hypothèses UX et les libellés proposés d'`EXPERIENCE.md` s'appliquent sans validation préalable. Ils sont validés visuellement au matin (D4).
- La VM cloud n'a ni Ollama ni `data/` : tout test qui en dépend est réparé ou marqué `integration`, avec la raison au rapport de nuit.

## Open Questions

- Badge « 0.0 GB » sous les réponses du chat RAG : est-ce une valeur fausse ou une métrique inutile ?
- Garde-fou RAM : tient-il compte d'un modèle déjà chargé dans Ollama ? Il a laissé passer un modèle de 2B avec 1,7 Go libres, puis l'a bloqué avec 2,8 Go.
- 771 mg de CO₂ pour Qwen 3.5 0.8B dans l'Arène, contre ~100 mg pour les autres modèles : un raisonnement long est probable, mais ce n'est pas vérifié.
