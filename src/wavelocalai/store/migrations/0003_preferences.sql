-- Choix de l'UI qui priment sur `Settings` pour ces seules clés (AD-15) : défaut de modèle par
-- usage (`default_model.<usage>`), stratégie RAG, découpe, reranker. L'app n'écrit jamais
-- `wavelocalai.toml`. `value` est un document JSON.
CREATE TABLE preferences (
    key TEXT NOT NULL PRIMARY KEY,
    value TEXT NOT NULL, -- JSON
    updated_at TEXT NOT NULL -- ISO 8601 UTC avec `Z` (convention des dates)
) WITHOUT ROWID;
