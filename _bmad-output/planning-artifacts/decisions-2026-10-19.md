# Décisions d'Anaël du 2026-10-19 (fin du MVP, avant les Epics 5 à 8)

Reporté au contrat le 2026-10-19 (PR à venir) ; ce fichier reste la trace des décisions.

Prises sur recommandation de l'orchestrateur du run autonome, après la préversion 2.0.0a4. Elles **priment** sur les documents de contrat qu'elles amendent, jusqu'à leur report dans ces documents (tâche « Report au contrat » ci-dessous). Les stories des Epics 5 à 8 les appliquent ; ce qui touche du code déjà livré passe dans la story 8.1.

## AD-6 amendé : appels de l'Accueil

L'Accueil lit le store rempli par le flux système, **plus au plus un appel de lecture par carte, lancé après le repère `shell-ready`** (AD-15), jamais en boucle. Cas actuels : carte « Démo recommandée » (`GET /api/models`, `GET /api/models/defaults?purpose=arena`, story 3.6) et carte « Documents » (`GET /api/rag/documents`, story 4.9). Aucun champ `rag` n'est ajouté au flux système. Garde-fous : `tests/v2/unit/test_shell_static.py` et `tests/v2/e2e/test_shell.py`.

## Écarts du §7(d) de `sprint-change-proposal-2026-10-19.md`

| N° | Décision | Où |
|---|---|---|
| 1 | Le message de `timeout` cite le délai (« Délai dépassé (120 s) »), partout (Arène, Banc, chat) | 8.1 pour l'existant |
| 2 | Texte de `cloud_not_allowed` : celui d'`errors.py` | acté |
| 3 | Icône de l'Arène : `swords` (code et maquette) ; DESIGN.md corrigé. La carte Références a sa propre icône, jamais partagée | report au contrat |
| 4 | Chronomètre de l'Arène au format « 0:42 » (UX-DR20) | 8.1 si l'existant diffère |
| 5 | « Un seul juge » : toujours affiché avec les notes (maquette) | 8.1 si l'existant diffère |
| 6 | Étiquette « le plus petit des trois » : abandonnée | acté |
| 7 | Adresse réécrite à la fin d'un run (`history.replaceState` vers `…/<run_id>`), pour l'Arène comme pour l'Équipe | 8.1 (Arène), 6.6 (Équipe) |
| 8 | Résultat effacé rouvert : « Résultat introuvable » avec sa phrase qui dit l'effacement (comportement livré en 3.6) | acté |
| 9 | Carte Mode de l'Accueil sans compteur d'appels cloud | acté |
| 10 | Banc : champ `structured_output` du registre (le front sait qu'un modèle ne peut pas imposer de format) ; boutons « Relancer le test » et « Modifier le test » | 7.4 |
| 11 | Références : sans « Autres modèles mesurés », ni lien, ni légende des marques | 5.8 |
| 12 | Discussion : avertissement cloud « les extraits de vos documents lui sont envoyés » (AD-9) ; pas d'export ; marqueur [n] non vérifié en texte brut ; `retrieval_step` publié en fin d'étape | 8.1 (avertissement) |
| 13 | Base documentaire : Supprimer et Vider désactivés pendant un import, avec leur raison (au lieu du 409 affiché) ; le 409 reste côté serveur | 8.1 |
| 14 | Évaluation : 4 modèles évalués au plus ; pas de colonne « Global » ; liste des évaluations et bancs passés | 7.3, 7.4 |
| 15 | Agents : `h1` « Agent seul » et « Équipe d'agents » (maquette) | 6.4, 6.6 |
| 16 | Sobriété : « Remettre le compteur à zéro » désactivé quand la session est vide ; version d'Ollama en légende de la santé du système | 5.1, 5.2 |
| 17 | Modèles : `wl-model-picker` filtré sur l'éligibilité de l'usage ; bouton « Fiche du modèle » à côté du sélecteur | 5.4, 5.6 |
| 18 | Noms de champs d'événements : ratifiés tels que livrés (`citations`, champs de `retrieval_step`, `ingest_progress`) ; les suivants fixés par leur story serveur et consignés dans `contrat-api.md` | report au contrat |

## Ajouts d'API ratifiés tels quels

Déjà consignés dans `_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md` par leurs stories : 4.1 (`ingest_progress.file`, `ingest_file_done`), 4.3 (`embedding_change_needs_clear`, `base_count_stale`, `base_in_use`, `vector_index_lost`, `vector_tables_unreachable`, `GET /api/rag/settings` enrichi), 4.4 (`sources`, `retrieval_step`, `metrics.retrieval_s`, `rag_base_empty`, `chunk_not_found`, réglages `rag.*`), 4.8 (`ram_guard` 503 et son `detail`, `memory.available_gb`, `required_gb`), 4.6 (`strategy`, `top_k`, `citations`, étapes de `retrieval_step`), 4.7 (`reranker`, champs de reclassement), 3.1 à 3.6 (`question`, `lane_status.error`, `judge`, `invalid_output`, `verdict`, `run_not_found`, `arena_busy`, `config`, `erased`), 2.1 et 2.3 (`generation_interrupted`, `energy_wh`).

## Points ouverts du run ratifiés

- pydantic 2.12.x jusqu'à la bascule (8.4) ; spine §Stack à corriger.
- AD-15 : cache de 5 s pour les routes de lecture, 1 s pour la sonde du flux système.
- AD-8 : champ optionnel de prefill en fin de `ChatResult`.
- CO₂ cloud : mix électrique du centre de données du fournisseur (`electricity_mix_zone=None`).

## Ajouts à la story 8.1 (dette)

- Self-RAG avec un petit modèle : avertissement « vérification peu fiable » quand la stratégie vérifiée est choisie avec un modèle de moins de ~3 B paramètres actifs (comme le juge de l'Arène).
- Copies `.db.bak-N` : une seule copie, supprimée après la migration suivante réussie ; un effacement (AD-13) purge aussi le texte de la copie ou la supprime ; test.
- Écarts n° 1, 4, 5, 7, 12, 13 ci-dessus sur le code livré.
- `components/wl-model-picker.js` (666 lignes) : sous 600 lignes (ou dans la 5.0).
- Sprite Material Symbols Rounded officiel (accord d'Anaël ; fichier fourni par Anaël, aucun téléchargement par un agent).

## Report au contrat

Avant la story 5.1, une passe `bmad-spec` (Opus) reporte ces décisions dans ARCHITECTURE-SPINE.md (AD-6, AD-8, AD-15, §Stack), `contrat-api.md`, EXPERIENCE.md, DESIGN.md et epics.md (critères des stories 5.x à 8.1 cités ci-dessus).

## Autres

- Prix cloud (PR #81) : Groq à 0 pour ses quatre modèles (plan gratuit de l'API) ; `mistral-large-latest` = `mistral-large-2512`, vérifié par l'API.
- `mesures-couts/` (sorties locales de `/agent-cost-kit:mesurer-couts`) ignoré par git.
- Ollama : disponible au run la plupart du temps, pauses ponctuelles sur demande.
