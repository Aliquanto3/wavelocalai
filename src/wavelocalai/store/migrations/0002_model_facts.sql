-- Cache de `/api/show` d'Ollama par (tag, digest) : le registre des modèles (AD-15) le relit
-- Ollama arrêté. Un nouveau digest pour le même tag = nouvelle ligne ; le registre lui-même
-- n'est pas une table (il se reconstruit en mémoire).
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
    fetched_at REAL NOT NULL, -- secondes depuis l'époque Unix
    PRIMARY KEY (tag, digest)
) WITHOUT ROWID;
