## 7. Carte de péremption

Calculée avec `recon_kit.py staleness`. Fenêtres de revérification retenues : version et compatibilité 1 mois, fonctionnalité 3 mois, performance et contamination 3 mois (paysage IA), licence 6 mois.

Pour les licences, les versions et les fonctionnalités, la date retenue est celle de la lecture en direct (2026-10). Pour les scores et la contamination, c'est la date de la source.

Les formules et méthodes statistiques (Connor, Holm, O'Brien-Fleming, Miller) ne périment pas et sont exclues.

| Affirmation | Classe | Date retenue | À revérifier le | Périmée ? |
|---|---|---|---|---|
| [5] Scores Open LLM Leaderboard v2 de SLM 1B–14B (IFEval, BBH, MATH Lvl5, MuSR) | perf | 2025-02 | 2025-05-01 | **oui** |
| [4] IFBench : 300 prompts, 58 contraintes, saturation d'IFEval, scores | contamination | 2025-07 | 2025-10-01 | **oui** |
| [6] Contamination de Qwen2.5 sur MATH-500 | contamination | 2025-07 | 2025-10-01 | **oui** |
| [27] Scores BFCL des SLM par catégorie | perf | 2026-04 | 2026-07-01 | **oui** |
| [76] multipletests : Holm-Šidák par défaut | version | 2026-10 | 2026-11-01 | non |
| [10] Provider ollama d'Inspect sur /v1 (vérifié à la source) | compatibilite | 2026-10 | 2026-11-01 | non |
| [63] API native /api/chat : logprobs, think, format, seed | compatibilite | 2026-10 | 2026-11-01 | non |
| [62] Ollama v0.40.2 (08/10/2026), ordre des releases, capacité decision | version | 2026-10 | 2026-11-01 | non |
| [16] #18774 : format non appliqué avec think (vérifié à la source) | fonctionnalite | 2026-10 | 2027-01-01 | non |
| [11] Types des tâches leaderboard de lm-eval (multichoice vs génératif) | fonctionnalite | 2026-10 | 2027-01-01 | non |
| [13] ast_checker non importable seul, sortie par item | fonctionnalite | 2026-10 | 2027-01-01 | non |
| [30] Code OneRuler MIT avec scripts de génération (vérifié à la source) | licence | 2026-10 | 2027-04-01 | non |
| [15] Code M-IFEval Apache-2.0, FR/JA/ES, modèles spaCy (vérifié à la source) | licence | 2026-10 | 2027-04-01 | non |
| [48] Données GSM-Symbolic sous CC-BY-NC-ND-4.0 | licence | 2026-10 | 2027-04-01 | non |
| [42] BBEH : licences, 4 520 items, mini 460 | licence | 2026-10 | 2027-04-01 | non |
| [23] IFEval-fr de le-leadboard sans licence déclarée | licence | 2026-10 | 2027-04-01 | non |
| [33] FQuAD : non commercial, redistribution interdite | licence | 2026-10 | 2027-04-01 | non |

**Constat :** 4 affirmations de performance ou de contamination sont déjà périmées selon ces fenêtres. Les scores publiés de SLM datent de la génération 2024–2025 (Llama 3.2, Qwen2.5, Gemma 3) et ne couvrent pas les modèles actuels du catalogue. Le pilote (questions ouvertes, section 6) doit donc mesurer directement la saturation et la discordance sur les modèles réels, au lieu de se fier aux chiffres publiés.

**Prochaine revérification : 2026-11-01**, pour la version d'Ollama, son API et sa compatibilité (logprobs, `format` et `think`, issue #18774) ; à refaire avant de figer le harnais.