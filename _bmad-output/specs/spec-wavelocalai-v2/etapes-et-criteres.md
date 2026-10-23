# Étapes et critères d'acceptation

Plan de la synthèse §4. Une étape se livre en un ou plusieurs lots ; un lot = une PR fusionnée en un à deux jours. Lots front de 03 §5 : lot 0 = étape 1, lot 1 = étapes 2 et 3, lot 2 = étape 4, lot 3 = étape 5, lot 4 = étape 6, lot 5 = étape 7, lot 6 = étape 8. Taille indicative : MVP en 4 à 5 semaines, total 8 à 10 semaines.

## MVP

### Étape 1 : socle (CAP-1 à CAP-4)

Back : FastAPI, `Settings`, SQLite et migrations, `/api/health`, `/api/system/stream`, `/api/models` (`origin`, `kind`), `/api/models/defaults`, modèle run, format d'erreur unique, CI. Front : coquille, routeur, `tokens.css` et son test de dérive, polices, icônes Material, i18n française, client SSE, barre haute, `model-picker`, composants `metric`, `badge` (étiquettes « indicatif », « un seul juge », « estimé », « non mesurable »), `run-status`, protection de l'API locale. Premier lot : mise à jour d'`AGENTS.md` (v1 en correctifs seulement, v2 décrite).

- Installation par `uv sync` seul ; aucun Node, aucun téléchargement à l'exécution ; aucune requête navigateur hors de `127.0.0.1` (E2E).
- Coquille < 300 ms, utilisable Ollama arrêté ; « Ollama ne répond pas » en < 3 s.
- Bascule cloud désactivée à chaque chargement, conservée entre écrans, refus serveur sans `allow_cloud`.
- `model-picker` sans embedding ni reranker, filtrable au clavier, groupé Local/Cloud, pastille MoE.
- Test de dérive des jetons vert ; axe-core sans violation sur la coquille, clair et sombre ; aucun emoji dans `static/`.

### Étape 2 : chat (CAP-5, CAP-6)

Back : port `ChatModel` (4 fournisseurs), métriques D3, carbone par run, table `messages`, export.

- Premier token dès réception ; « Arrêter » < 1 s, partiel gardé.
- Changer d'écran pendant une génération puis revenir : reprise sans perte ni doublon.
- Débit final = `eval_count / eval_duration`, provisoire marqué ; chargement et durée totale à part.
- CO₂ local mesuré et différent selon le modèle ; cloud en estimation ecologits ou « non mesurable » expliqué (ex. modèle Groq sans entrée dans la table de correspondance, AD-11).
- « Effacer » retire le texte du fichier de base (test).

### Étape 3 : Arène (CAP-7)

Back : exécutions multiplexées, file Ollama, juge.

- 3 colonnes en flux ; délai dépassé isolé ; « non évalué » jamais 0.
- Résultat conservé à tout clic, rouvrable par URL ; export CSV et Markdown avec preuve (fiche machine, version d'Ollama, digests, méthode CO₂, juge).
- Verdict local/cloud chiffré : écart de note, coût pour 1 000 requêtes (table de prix datée dans `wavelocalai.toml`), CO₂, données restées sur le poste.
- Flow 1 joué en E2E avec modèles simulés.

### Étape 4 : assistant documentaire (CAP-8, CAP-9)

Back : ingestion en run `ingest`, embeddings Ollama, sqlite-vec, reranker fastembed optionnel, stratégies naïve, HyDE, Self-RAG.

- Zone de dépôt immédiate, progression par fichier, échec avec raison et compteur inchangé.
- Sources avant la réponse, avec document, page et extrait entier ; le score brut n'est plus le seul indicateur.
- Suppression d'un document seul ; « Vider » annonce le nombre d'extraits, « Annuler » ne supprime rien.
- Garde-fou mémoire : question gardée, besoin et mémoire libre chiffrés (vrais avec un modèle déjà chargé), modèle plus petit proposé.
- Flow 2 joué en E2E sur une base de test (jamais `data/`).

## Après le MVP

### Étape 5 : Sobriété et Modèles (CAP-6, CAP-10)

- Métriques en direct sans clic, arrêtées onglet masqué ; historique ; CO₂ de session = somme des réponses mesurées, non-mesurables à part ; bridage thermique signalé (NVML).
- Seuils des défauts `agent` et `rag` (règle provisoire de `contrat-api.md`) calés sur `qb.results/1`.
- Écran `#/modeles` : compatibilité mémoire avant installation, progression chiffrée, décharger, supprimer ; fiche modèle (dense ou MoE, paramètres actifs, quantification, licence, outils et raisonnement vérifiés, via `/api/show`, catalogue, `qb.results/1`) ; « Pourquoi ce débit ? » ; « Sur d'autres postes » (trois postes de référence, dont le PC pro 16 Go sans GPU).

### CAP-13 : références (après l'étape 5)

- `#/arene/references` et carte d'Accueil depuis `qb.results/1`.

### Étape 6 : Agents (CAP-11)

Boucle d'outils, outils repris d'`agent_tools`, email validé (D2, outil décoché par défaut), équipe séquentielle.

- Étapes en direct, dépliables ; aucun email sans validation ; garde-fou mémoire chiffré ; équipe arrêtable, rapport conservé, schéma SVG et trace par agent ; parité v1.

### Étape 7 : Évaluation et Banc d'essai (CAP-12)

- Étapes et scores au fil de l'eau, verdict par affirmation ; juge indisponible = « non évalué » avec raison ; jeu fixe de non-régression.
- Banc : validité du format attendu ; interrupteurs « format imposé » (paramètre `format` d'Ollama) et « réponse concise ».

### Étape 8 : finition et bascule (CAP-14)

- Zéro violation axe-core partout, clair et sombre ; grille RGAA 4.1 ; 200 % de zoom et 320 px CSS sans défilement horizontal ; projection validée sur vidéoprojecteur réel.
- Contrat JSON du banc en lecture seule ; parité listée page par page ; v1 archivée ; captures et GIF du README refaits ; `2.0.0` publiée.

## Hors plan

- Moteur `llama-server` en option (port `ChatModel` compatible OpenAI) : après l'étape 8.
- À transmettre à `slm-quality-bench` (synthèse §7.2) : vitesse par machine, comparateur cloud, usages absents, variantes d'invite, llama.cpp contre Ollama, bande passante mémoire.
