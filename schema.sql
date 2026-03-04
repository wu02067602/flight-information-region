-- ADIZ 圖片座標抽取專案 - 資料庫 Schema
-- 需使用 PostgreSQL + PostGIS 擴充

CREATE EXTENSION IF NOT EXISTS postgis;

-- 原始圖片來源
CREATE TABLE IF NOT EXISTS raw_images (
    id SERIAL PRIMARY KEY,
    source_id VARCHAR(64) UNIQUE NOT NULL,           -- article_id/filename 作為唯一鍵
    article_id VARCHAR(32) NOT NULL,
    source_url TEXT,
    file_path TEXT NOT NULL,
    file_hash VARCHAR(64),
    fetched_at TIMESTAMPTZ,
    processing_status VARCHAR(32) DEFAULT 'pending',  -- pending, processing, done, failed
    error_message TEXT,
    pipeline_version VARCHAR(32),
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_raw_images_article_id ON raw_images(article_id);
CREATE INDEX idx_raw_images_status ON raw_images(processing_status);
CREATE INDEX idx_raw_images_processed_at ON raw_images(processed_at);

-- 偵測結果（紅框像素、經緯度、OCR 原文、信心分數）
CREATE TABLE IF NOT EXISTS detections (
    id SERIAL PRIMARY KEY,
    raw_image_id INTEGER NOT NULL REFERENCES raw_images(id) ON DELETE CASCADE,
    detection_index INTEGER NOT NULL,                -- 同一張圖內第幾個紅框
    pixel_geometry TEXT,                             -- 像素多邊形 JSON: [[x,y],...]
    geo_geometry GEOMETRY(Polygon, 4326),            -- PostGIS 經緯度多邊形
    ocr_raw_text TEXT,                              -- 原始 OCR 文字
    confidence_score NUMERIC(5,4) CHECK (confidence_score >= 0 AND confidence_score <= 1),
    error_message TEXT,
    pipeline_version VARCHAR(32),
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(raw_image_id, detection_index)
);

CREATE INDEX idx_detections_raw_image ON detections(raw_image_id);
CREATE INDEX idx_detections_confidence ON detections(confidence_score);
CREATE INDEX idx_detections_geo ON detections USING GIST(geo_geometry);

-- 業務事件（時間、機型、架次、備註、幾何）
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    detection_id INTEGER REFERENCES detections(id) ON DELETE SET NULL,
    raw_image_id INTEGER NOT NULL REFERENCES raw_images(id) ON DELETE CASCADE,
    item_number VARCHAR(16),                         -- 項次（①②③ 等）
    event_time TIMESTAMPTZ,                          -- 事件時間
    aircraft_type VARCHAR(128),                      -- 機型/類型
    sorties VARCHAR(64),                             -- 架次
    remarks TEXT,                                    -- 備註
    geometry GEOMETRY(Point, 4326),                  -- 事件代表點（可為多邊形質心）
    review_status VARCHAR(32) DEFAULT 'pending',     -- pending, auto_accepted, manual_review, approved, rejected
    confidence_score NUMERIC(5,4),
    source_id VARCHAR(64) NOT NULL,
    pipeline_version VARCHAR(32),
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_events_raw_image ON events(raw_image_id);
CREATE INDEX idx_events_detection ON events(detection_id);
CREATE INDEX idx_events_review_status ON events(review_status);
CREATE INDEX idx_events_processed_at ON events(processed_at);
CREATE INDEX idx_events_geometry ON events USING GIST(geometry);
CREATE UNIQUE INDEX idx_events_source_version ON events(source_id, pipeline_version);

-- 處理報告快取（可選，供統計用）
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(64) UNIQUE NOT NULL,
    pipeline_version VARCHAR(32) NOT NULL,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    total_images INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    low_confidence_count INTEGER DEFAULT 0,
    error_summary JSONB
);

CREATE INDEX idx_pipeline_runs_started ON pipeline_runs(started_at);
