-- GraphRAG 知識圖譜 Schema
-- 建立藥品交互作用圖譜所需的 PostgreSQL 資料表
-- 執行方式：python scripts/init_graphrag_db.py

-- 藥品實體節點（對應 FDA openfda 紀錄 + 本地 drug_permits 白名單）
CREATE TABLE IF NOT EXISTS graphrag_drug_entities (
    entity_id          SERIAL PRIMARY KEY,
    generic_name_norm  TEXT NOT NULL UNIQUE,           -- lower(trim()) 正規化後
    generic_name       TEXT NOT NULL,                  -- 原始英文學名
    display_name_cn    TEXT,                           -- 對應 drug_permits.name_cn
    brand_names        TEXT[],                         -- 品牌名陣列
    link_permit_number TEXT,                           -- 對應 drug_permits.permit_number
    in_local_whitelist BOOLEAN NOT NULL DEFAULT FALSE, -- 是否在台灣合法用藥清單
    source             TEXT NOT NULL                   -- 'fda' | 'local' | 'both'
                       CHECK (source IN ('fda', 'local', 'both')),
    raw_openfda        JSONB,                          -- 保留 openfda section 供 debug
    fetched_at         TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_graphrag_entities_permit
    ON graphrag_drug_entities (link_permit_number);
CREATE INDEX IF NOT EXISTS idx_graphrag_entities_whitelist
    ON graphrag_drug_entities (in_local_whitelist);


-- 藥品交互作用關係邊
CREATE TABLE IF NOT EXISTS graphrag_drug_interactions (
    interaction_id   SERIAL PRIMARY KEY,
    drug_1_id        INT NOT NULL
                     REFERENCES graphrag_drug_entities(entity_id) ON DELETE CASCADE,
    drug_2_name      TEXT NOT NULL,                    -- 對方藥名（可能尚未在實體表）
    drug_2_id        INT
                     REFERENCES graphrag_drug_entities(entity_id),
    relation         TEXT NOT NULL                     -- 關係類型
                     CHECK (relation IN (
                         'interacts_with',
                         'contraindicated',
                         'increases_effect',
                         'decreases_effect',
                         'monitor_closely'
                     )),
    severity         TEXT                              -- 嚴重程度
                     CHECK (severity IN ('major', 'moderate', 'minor', 'unknown')),
    entity_type      TEXT DEFAULT 'drug',               -- 'drug' | 'supplement' | 'food' | 'class'
    description_id   UUID NOT NULL,                    -- ChromaDB document id
    evidence_snippet TEXT,                             -- 500 字摘要，方便 SQL 預覽
    extracted_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_graphrag_interactions_drug1
    ON graphrag_drug_interactions (drug_1_id);
CREATE INDEX IF NOT EXISTS idx_graphrag_interactions_drug2
    ON graphrag_drug_interactions (drug_2_id);
CREATE INDEX IF NOT EXISTS idx_graphrag_interactions_severity
    ON graphrag_drug_interactions (severity);
CREATE INDEX IF NOT EXISTS idx_graphrag_interactions_desc_id
    ON graphrag_drug_interactions (description_id);


-- FDA 查詢快取追蹤（懶加載 TTL 控制）
CREATE TABLE IF NOT EXISTS graphrag_fetch_log (
    generic_name_norm TEXT PRIMARY KEY,
    last_fetched_at   TIMESTAMPTZ,
    status            TEXT NOT NULL DEFAULT 'pending'  -- ok | not_found | error | pending
                      CHECK (status IN ('ok', 'not_found', 'error', 'pending')),
    http_code         INT,
    error_message     TEXT,
    interaction_count INT DEFAULT 0,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
