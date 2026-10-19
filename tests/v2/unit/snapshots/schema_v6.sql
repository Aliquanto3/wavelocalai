-- user_version: 6

CREATE UNIQUE INDEX documents_fingerprint_active ON documents (fingerprint)
    WHERE status <> 'failed';

CREATE INDEX documents_status ON documents (status);

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

CREATE TABLE chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position >= 0),
    -- Page d'origine (PDF) ; nul pour un format sans page.
    page INTEGER CHECK (page IS NULL OR page >= 1),
    text TEXT NOT NULL,
    UNIQUE (document_id, position)
);

CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('chat', 'rag', 'agent')),
    title TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    -- Empreinte SHA-256 du contenu : un même fichier n'est pas indexé deux fois.
    fingerprint TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    embedding_model TEXT NOT NULL,
    -- Dimension des vecteurs, connue une fois le premier lot calculé.
    embedding_dim INTEGER CHECK (embedding_dim IS NULL OR embedding_dim > 0),
    status TEXT NOT NULL CHECK (status IN ('indexing', 'ready', 'failed')),
    chunk_count INTEGER NOT NULL DEFAULT 0 CHECK (chunk_count >= 0),
    page_count INTEGER CHECK (page_count IS NULL OR page_count >= 0),
    -- Enveloppe d'AD-18 (`ingest_failed`) quand le document a échoué.
    error TEXT CHECK (error IS NULL OR json_valid(error)),
    -- Run `ingest` qui l'a créé (le registre des runs survit au document).
    run_id TEXT REFERENCES runs (id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    ready_at TEXT,
    CHECK (status <> 'failed' OR error IS NOT NULL),
    CHECK (status <> 'ready' OR (embedding_dim IS NOT NULL AND ready_at IS NOT NULL))
);

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
    fetched_at TEXT NOT NULL, parameters TEXT, -- ISO 8601 UTC avec `Z` (convention des dates)
    PRIMARY KEY (tag, digest)
) WITHOUT ROWID;

CREATE TABLE preferences (
    key TEXT NOT NULL PRIMARY KEY,
    value TEXT NOT NULL, -- JSON
    updated_at TEXT NOT NULL -- ISO 8601 UTC avec `Z` (convention des dates)
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
