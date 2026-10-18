-- Migration 0001 : tables du hub des runs (AD-5, AD-7, AD-10, AD-12).
-- Une migration fusionnée n'est jamais modifiée : tout changement passe par 0002 et suivantes.
-- Toutes les valeurs de `kind` et de `status` d'AD-5 existent dès ici, post-MVP compris.
-- Dates en ISO 8601 UTC avec `Z`, durées en secondes (`_s`), identifiants `uuid4().hex`.

-- Une par démarrage du serveur et par remise à zéro du CO2 (AD-10).
CREATE TABLE app_sessions (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    reason TEXT NOT NULL CHECK (reason IN ('startup', 'reset'))
);

-- Créée par le hub avec le premier run ; son `kind` est fixe (AD-5).
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('chat', 'rag', 'agent')),
    title TEXT,
    created_at TEXT NOT NULL
);

-- Le run est l'unique modèle d'exécution (AD-5). Racines : chat, arena, rag, agent, ingest, pull,
-- eval, bench. Feuilles (un run enfant par appel de modèle) : generation, judge, embedding.
-- Les lignes `runs` survivent à l'effacement d'une conversation (conversation_id passe à NULL) :
-- elles forment le registre carbone (AD-13).
CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN (
        'chat', 'arena', 'rag', 'agent', 'ingest', 'pull', 'eval', 'bench',
        'generation', 'judge', 'embedding'
    )),
    parent_run_id TEXT REFERENCES runs (id),
    app_session TEXT NOT NULL REFERENCES app_sessions (id),
    conversation_id TEXT REFERENCES conversations (id) ON DELETE SET NULL,
    model TEXT,
    status TEXT NOT NULL CHECK (status IN (
        'running', 'awaiting_approval', 'ok', 'error', 'cancelled', 'interrupted'
    )),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    origin TEXT CHECK (origin IN ('local', 'cloud')),
    input_tokens INTEGER,
    output_tokens INTEGER,
    ttft_s REAL,
    load_s REAL,
    eval_s REAL,
    total_s REAL,
    tps REAL,
    tps_source TEXT CHECK (tps_source IN ('ollama_eval', 'wallclock')),
    energy_wh REAL,
    -- Champ `co2` d'AD-10, à plat ; renseigné sur les feuilles seulement.
    co2_mg REAL,
    co2_method TEXT CHECK (co2_method IN ('codecarbon', 'ecologits', 'unmeasurable')),
    co2_estimated INTEGER CHECK (co2_estimated IN (0, 1)),
    co2_range_low_mg REAL,
    co2_range_high_mg REAL,
    co2_allocation TEXT CHECK (co2_allocation IN ('direct', 'prorata_tokens')),
    co2_reason TEXT,
    -- Erreur au format unique d'AD-18 (JSON), si le run a échoué.
    error TEXT CHECK (error IS NULL OR json_valid(error)),
    -- Paramètres sans aucun texte saisi (AD-7) : la question vit dans `messages`.
    params TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(params)),
    -- `reason` est requis quand `mg` est nul : jamais 0 pour un inconnu (AD-10).
    CHECK (co2_method IS NULL OR co2_mg IS NOT NULL OR co2_reason IS NOT NULL),
    CHECK (co2_method IS NULL OR co2_estimated IS NOT NULL)
);
CREATE INDEX runs_app_session ON runs (app_session);
CREATE INDEX runs_parent ON runs (parent_run_id);
CREATE INDEX runs_conversation ON runs (conversation_id);
CREATE INDEX runs_status ON runs (status);

-- Événements d'un run, écrits par lots (AD-7). `sources` y est stocké sans `text`.
CREATE TABLE run_events (
    run_id TEXT NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
    seq INTEGER NOT NULL CHECK (seq >= 1),
    type TEXT NOT NULL,
    ts TEXT NOT NULL,
    data TEXT NOT NULL CHECK (json_valid(data)),
    PRIMARY KEY (run_id, seq)
) WITHOUT ROWID;

-- Écrits par le hub seul (AD-5) ; l'ordre est celui de l'insertion (rowid).
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    run_id TEXT REFERENCES runs (id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL DEFAULT '',
    reasoning TEXT,
    tool_calls TEXT CHECK (tool_calls IS NULL OR json_valid(tool_calls)),
    created_at TEXT NOT NULL
);
CREATE INDEX messages_conversation ON messages (conversation_id);
CREATE INDEX messages_run ON messages (run_id);
