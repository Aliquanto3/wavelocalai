-- Migration 0004 : base documentaire (AD-12, AD-16, story 4.1).
-- Une migration fusionnée n'est jamais modifiée : tout changement passe par 0005 et suivantes.
-- Les tables vec0 `chunks_vec_<dim>` (rowid = chunks.id) ne sont PAS créées ici : elles dépendent
-- de la dimension du modèle d'embedding et sont créées par `store.ensure_vec_table(dim)` au premier
-- embedding (seule exception écrite aux migrations, AD-12).

-- Un fichier importé. Une base = un modèle d'embedding (AD-16) : seuls les documents `ready` sont
-- interrogés. `source` est le nom du fichier tel que déposé (jamais son chemin).
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
-- Un contenu déjà présent (indexation en cours ou terminée) n'est pas indexé deux fois ; un
-- document `failed` ne bloque pas un nouvel essai.
CREATE UNIQUE INDEX documents_fingerprint_active ON documents (fingerprint)
    WHERE status <> 'failed';
CREATE INDEX documents_status ON documents (status);

-- Extraits d'un document : texte et position. `id` est le `rowid` de la ligne vec0 correspondante ;
-- AUTOINCREMENT pour qu'un identifiant supprimé ne soit jamais réattribué à un autre extrait.
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position >= 0),
    -- Page d'origine (PDF) ; nul pour un format sans page.
    page INTEGER CHECK (page IS NULL OR page >= 1),
    text TEXT NOT NULL,
    UNIQUE (document_id, position)
);
