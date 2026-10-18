# Archive de l'ancien dépôt `wave_local_ai_v2`

Copie de documents et de quelques modules de l'ancien dépôt public `Aliquanto3/wave_local_ai_v2` (août à octobre 2026), avant sa suppression. Ce dépôt visait un banc reproductible local contre cloud, avec un front React ; il a été abandonné le 2026-10-18 (analyse : [`../../audits/refonte-2026-10/04-analyse-ancienne-v2.md`](../../audits/refonte-2026-10/04-analyse-ancienne-v2.md) et [`05-code-ancienne-v2.md`](../../audits/refonte-2026-10/05-code-ancienne-v2.md)).

- **Lecture seule.** Fichiers copiés tels quels (`git show`), en anglais pour la plupart, sans retouche. Le code n'est ni importé ni testé ici : c'est une référence.
- **Sources :** `main` au commit `c68b23e` ; `feat/night-run-2026-10-02` (jamais fusionnée) au commit `d28c8a7`.
- **Licence :** MIT, Aliquanto3 (voir [`LICENSE`](LICENSE)).
- **Copie complète** (toutes branches, `git bundle` vérifié) hors dépôt : `C:\Users\Utilisateur\Documents\GitHub\_hors-depot\wave_local_ai_v2\wave_local_ai_v2-toutes-branches-20261018.bundle`. Elle contient aussi ce qui n'est pas copié ici et relève de `slm-quality-bench` : modules statistiques (`score_interval`, `agreement`, `chrf`, `repetitions`, `aggregation`, `verdict`), suites de tâches (`suite_data/`) et résultats bruts (`aidd_docs/results/quality-reference.jsonl`, 5,6 Mo). Restauration : `git clone <bundle> wave_local_ai_v2`.

## Contenu

| Priorité | Fichiers | Branche | Pourquoi |
|---|---|---|---|
| 1 | `context_input/` (5 fichiers) | `main` | Notes d'Anaël : ambitions de publication, brief d'écarts, machines (`hardware.md`, écrit de sa main), base llama.cpp, choix des modèles |
| 1 | `aidd_docs/product/wave-local-ai-v2.md` | `main` | Brief produit (généré à partir de ses décisions) |
| 1 | `aidd_docs/tasks/2026_08/2026_08_21_expectations-gap-audit/audit-and-plan.md` | nuit | Seule trace de son prompt fondateur (attentes E1 à E16) |
| 2 | PRD (`2026_08_21-…-prd.md`), questions au propriétaire (3 fichiers), `run-log.md`, décision Google AI Studio | nuit | Décisions et arbitrages |
| 3 | `aidd_docs/results/README.md`, `memory/architecture.md`, audit du 2026-09-22, `roster/*.json*`, 6 spikes | nuit | Constats de mesure, pièges, licences vérifiées, faits sur Ollama |
| 3 | `src/wave_local_ai_v2/hardware.py`, `nvml.py`, `machine_state.py`, `local_client.py` | nuit | Fiche matérielle, NVML et bridage, client local : idées reprises pour l'app (05 §4.1) |

Notes françaises d'origine et prompt fondateur : absents de l'ancien dépôt (seulement traduits ou reformulés) ; à ajouter ici s'ils sont retrouvés.
