-- Migration 0006 : notes de l'évaluation de la qualité d'une réponse documentaire (story 7.1).
-- Une ligne par (modèle évalué, question, métrique) d'un run racine `eval`. `score` nul : non évalué
-- (jamais 0 pour un inconnu) et `reason` dit pourquoi. `detail` (JSON) : `verdicts` (fidélité, un par
-- affirmation), `questions` (pertinence) ou `useful` (précision du contexte). Effacer l'évaluation
-- supprime ces lignes et ses `run_events`, et garde les lignes `runs` (AD-13).
CREATE TABLE evaluations (
    run_id TEXT NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
    lane TEXT NOT NULL,
    question_index INTEGER NOT NULL CHECK (question_index >= 0),
    metric TEXT NOT NULL CHECK (metric IN ('faithfulness', 'relevance', 'context_precision')),
    score INTEGER CHECK (score IS NULL OR score BETWEEN 0 AND 100),
    reason TEXT NOT NULL,
    detail TEXT CHECK (detail IS NULL OR json_valid(detail)),
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, lane, question_index, metric)
) WITHOUT ROWID;
