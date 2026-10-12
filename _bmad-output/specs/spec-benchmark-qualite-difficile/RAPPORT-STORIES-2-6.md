# Rapport d'orchestration : stories 2 à 6 du banc de qualité difficile

Run du 2026-10-11 (18:50) au 2026-10-12 (06:15), sur la tour et la branche `feat/quality-bench-suite`, créée depuis `feat/quality-bench-socle` (8c42d53). Rien n'a été poussé.

## Base de tests

Commande : `.venv-quality\Scripts\python -m pytest tests/quality_bench -q`.

Avant la story 2 : **212 tests verts** (2 avertissements de configuration pytest, déjà présents), en 8 s.

## Mode utilisé

**Mode A.** Chaque story a tourné dans un sous-agent general-purpose qui a invoqué `bmad-build-auto`. Le test d'imbrication a répondu OK.

## Stories

| Story | Statut | Commit | Tests après la story | Durée | Revue de suivi recommandée |
|---|---|---|---|---|---|
| 2. Schéma de question, import des jeux publics, téléchargements | done | `0d58ef0` | 320 verts (312 + 8 télémétrie) | ~38 min | non |
| 3. Générateurs à graine, questions privées, construction du jeu | done | `e033e3f` | 509 verts (501 + 8) | ~55 min | non |
| 4. Correcteurs déterministes, envs d'outils, phase grade | done | `e7e8d63` | 766 verts (758 + 8) | ~73 min | **oui** (5 medium corrigées, non relues) |
| 5. Génération sur les deux pistes | done | `bbbe3f9` | 893 verts (885 + 8) | ~33 min | **oui** (2 medium corrigées, non relues) |
| 6. Statistiques et rapport | done | `06f5432` | 1 059 verts (1 051 + 8) | ~40 min de travail effectif | **oui** (7 medium corrigées, non relues) |

Notes sur le tableau :

- « + 8 » renvoie à `tests/unit/test_telemetry.py -k "every_telemetry_importer or precedes_library_import"`.
- Après chaque story, l'orchestrateur a relancé les tests lui-même ; aucune story n'a fait régresser un test vert. Il a aussi réinstallé `requirements.txt` dans `.venv-quality` après les stories 2, 4 et 6, qui le modifient.
- La story 6 a été interrompue de nuit par une expiration de connexion, puis reprise par le même sous-agent après `/login`. Rien n'était commité au moment de la coupure, et le commit final date de 06:12.

## Choix faits seul

- **Texte d'appel de chaque sous-agent.** J'ai ajouté à l'`invoke_dev_with` un rappel des permis et des interdits de la session, que l'`invoke_dev_with` ne porte pas. J'y ai précisé aussi que la tour n'a pas de venv d'app : seuls `tests/quality_bench` et le filtre télémétrie peuvent y tourner, et rien ne s'installe hors de `.venv-quality`.
- **Story 3.** La pause de relecture a été tenue par l'orchestrateur, pas par le sous-agent. Le sous-agent n'a ni figé ni commité le jeu `set-v1`, choix qui revient à lui : on relance `build-set` après relecture.
- **Story 4.** Je lui ai transmis les points reportés par les stories 2 et 3 qui la concernaient : les flottants BFCL, les identifiants M-IFEval FR, `tools-fr`. Je l'ai autorisée à récupérer le code public copié sous `grading/vendored/`.
- **Stories 5 et 6.** J'ai interdit toute génération réelle contre Ollama, puisque les mesures se font à la story 8. Pour la story 6, j'ai aussi interdit de récupérer en ligne l'indice AA.
- **Revues de suivi.** Les stories 4, 5 et 6 ont fini `done` avec `followup_review_recommended: true`. Le protocole de boucle ne prévoyait pas de revue supplémentaire, donc je n'en ai pas lancé : elles sont listées plus bas.
- **Story 6 interrompue.** Je l'ai reprise par le même sous-agent, dont le contexte était intact, au lieu d'arrêter la boucle. L'arbre non vide était le travail en cours de cette même story, pas le reste d'une autre.
- **Pauses.** Après la consigne du 2026-10-11 au soir, les stories 4 à 6 ont tourné sans pause. Elles n'avaient de toute façon pas de checkpoint.

## Entrées ajoutées à `_bmad-output/implementation-artifacts/deferred-work.md`

**Story 2**

- La règle de contexte d'AD-5 ignore l'historique multi-tours de `bfcl-multi` (medium). Une partie de ces questions risque de passer en `context_exceeded`.
- Lancer `tests/unit` en entier sur une machine qui a un venv d'app.
- La licence des fichiers bruts OneRuler FR (texte et dictionnaires) n'est pas déclarée.

**Story 3**

- La provenance du jeu n'est pas versionnée ; il faut amender AD-6 (medium).
- Les identifiants M-IFEval FR étaient à vérifier contre le registre. La story 4 l'a fait, ils existent tous : ce point est levé.
- 87 des 418 critères de rédaction demandent au juge de compter (medium).

**Story 4**

- Contrat des outils à un seul tour : `bfcl_ast` réunit tous les pas du tour 0 (medium). La story 5 l'a tranché : sans env, la génération s'arrête après la première réponse.
- Décider si `conformity_error` doit vérifier les `format` des schémas JSONSchemaBench (medium).
- Exclure de `set-v1` 5 cibles `bfcl-live` défectueuses dans BFCL lui-même, avant de figer le jeu.
- `tools-fr` : 3 valeurs attendues sur 63 sont perdues à la traduction (« Californie » → CA).

**Story 5**

- Borner les reprises non comptées au cas où une question ferait tomber Ollama entier (medium, à observer au pilote).
- Confronter `tests/quality_bench/ollama_fake.py` au vrai Ollama 0.40.2 (medium, story 8) : `remote_host`, `context_length`, `/api/ps`, cache, `done_reason`, déchargement.
- Les deux reports tranchés par cette story, outils à un seul tour et panne d'Ollama comptée comme essai, figurent encore dans le fichier.

**Story 6**

- Le meneur, le rang et Spearman reposent sur des moyennes calculées sur des ensembles d'unités différents d'un modèle à l'autre, selon la règle d'AD-10 (medium, à trancher au pilote).
- Le fichier AA réel est à fournir avant le rapport final (story 10).

## Ce qui reste à vérifier à la main

1. **Relire les questions rédigées par les agents** avant de figer le jeu :
   - questions privées : `data/quality_bench/review/private-sample.md` (échantillon de 25) et `data/quality_bench/private/*.yaml` (144 au total) ;
   - questions de rédaction : `data/quality_bench/review/writing-sample.md` (échantillon de 10) et `scripts/quality_bench/questions/writing/writing-fr.yaml` (80 au total).
2. **Sauvegarder hors de la tour `data/quality_bench/private/`**, qui n'existe que sur cette machine.
3. **Figer `set-v1`** une fois la relecture faite : exclure les 5 cibles `bfcl-live` défectueuses et trancher les 3 valeurs `tools-fr`, puis lancer `build-set --set set-v1` et commiter l'index `benchmarks/quality/sets/set-v1/index.jsonl`.
4. **Faire la revue de suivi des stories 4, 5 et 6**, par exemple avec `bmad-code-review` sur `e033e3f..06f5432`. Ces stories ont 5, 2 et 7 corrections medium qu'aucune passe n'a relues.
5. **Licences à confirmer** :
   - 3 paquets NLTK sont « Unknown » dans l'index ;
   - le MIT de JSONSchemaBench ne repose que sur la carte Hugging Face ;
   - la licence des fichiers OneRuler FR n'est pas déclarée.
6. **Lancer `python -m pytest tests/unit` en entier** sur une machine qui a un venv d'app : la modification de `TELEMETRY_ROOTS` et `TELEMETRY_IMPORTERS` n'a été vérifiée qu'avec le filtre télémétrie.
7. **Fournir `benchmarks/quality/references/aa-<date>.json`**, au format décrit dans `scripts/quality_bench/questions/SOURCES.md`, section « Rapport ».
8. **Retirer de `deferred-work.md`** les entrées déjà tranchées : identifiants M-IFEval FR, outils à un seul tour, panne d'Ollama comptée comme essai.
