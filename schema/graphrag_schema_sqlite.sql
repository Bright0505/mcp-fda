-- GraphRAG SQLite Schema（SQLite 3.24+ 相容）
-- 使用 TEXT 取代 UUID / TIMESTAMPTZ / ARRAY / JSONB
-- 使用 INTEGER 取代 BOOLEAN（0/1）
-- 使用 INTEGER PRIMARY KEY 作為自增主鍵（= ROWID autoincrement）

CREATE TABLE IF NOT EXISTS graphrag_drug_entities (
    entity_id          INTEGER PRIMARY KEY,
    generic_name_norm  TEXT NOT NULL UNIQUE,
    generic_name       TEXT NOT NULL,
    display_name_cn    TEXT,
    brand_names        TEXT,                          -- JSON array string，如 '["Tylenol","Panadol"]'
    link_permit_number TEXT,
    in_local_whitelist INTEGER NOT NULL DEFAULT 0,   -- 0=否, 1=是
    source             TEXT NOT NULL DEFAULT 'fda',  -- 'fda' | 'local' | 'both'
    raw_openfda        TEXT,                         -- JSON string
    fetched_at         TEXT                          -- ISO 8601 UTC，如 '2026-01-01T00:00:00+00:00'
);
CREATE INDEX IF NOT EXISTS idx_ge_permit ON graphrag_drug_entities (link_permit_number);
CREATE INDEX IF NOT EXISTS idx_ge_wl     ON graphrag_drug_entities (in_local_whitelist);

CREATE TABLE IF NOT EXISTS graphrag_drug_interactions (
    interaction_id   INTEGER PRIMARY KEY,
    drug_1_id        INTEGER NOT NULL REFERENCES graphrag_drug_entities(entity_id) ON DELETE CASCADE,
    drug_2_name      TEXT NOT NULL,
    drug_2_id        INTEGER REFERENCES graphrag_drug_entities(entity_id),
    relation         TEXT NOT NULL,                  -- 'interacts_with' | 'contraindicated' | ...
    severity         TEXT,                           -- 'major' | 'moderate' | 'minor' | 'unknown'
    entity_type      TEXT DEFAULT 'drug',            -- 'drug' | 'supplement' | 'food' | 'class'
    description_id   TEXT NOT NULL,                  -- UUID as TEXT
    evidence_snippet TEXT,
    extracted_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_gi_d1  ON graphrag_drug_interactions (drug_1_id);
CREATE INDEX IF NOT EXISTS idx_gi_d2  ON graphrag_drug_interactions (drug_2_id);
CREATE INDEX IF NOT EXISTS idx_gi_sev ON graphrag_drug_interactions (severity);

CREATE TABLE IF NOT EXISTS graphrag_fetch_log (
    generic_name_norm TEXT PRIMARY KEY,
    last_fetched_at   TEXT,
    status            TEXT NOT NULL DEFAULT 'pending', -- 'pending' | 'ok' | 'not_found' | 'error'
    http_code         INTEGER,
    error_message     TEXT,
    interaction_count INTEGER DEFAULT 0,
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
