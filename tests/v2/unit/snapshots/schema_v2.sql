-- user_version: 2

CREATE INDEX messages_conversation ON messages (conversation_id);

CREATE INDEX messages_run ON messages (run_id);

CREATE INDEX runs_app_session ON runs (app_session);

CREATE INDEX runs_conversation ON runs (conversation_id);

CREATE INDEX runs_parent ON runs (parent_run_id);

CREATE INDEX runs_status ON runs (status);

CREATE TABLE app_sessions (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    reason TEXT NOT NULL CHECK (reason IN ('startup', 'reset'))
);

CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('chat', 'rag', 'agent')),
    title TEXT,
    created_at TEXT NOT NULL
);

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

CREATE TABLE model_facts (
    tag TEXT NOT NULL,
    digest TEXT NOT NULL,
    size_bytes INTEGER,
    family TEXT,
    parameter_size TEXT,
    quantization TEXT,
    context_length INTEGER,
    capabilities TEXT NOT NULL DEFAULT '[]', -- tableau JSON de noms de capacités d'Ollama
    params_total_b REAL,
    expert_count INTEGER,
    expert_used_count INTEGER,
    fetched_at TEXT NOT NULL, -- ISO 8601 UTC avec `Z` (convention des dates)
    PRIMARY KEY (tag, digest)
) WITHOUT ROWID;

CREATE TABLE run_events (
    run_id TEXT NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
    seq INTEGER NOT NULL CHECK (seq >= 1),
    type TEXT NOT NULL,
    ts TEXT NOT NULL,
    data TEXT NOT NULL CHECK (json_valid(data)),
    PRIMARY KEY (run_id, seq)
) WITHOUT ROWID;

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
