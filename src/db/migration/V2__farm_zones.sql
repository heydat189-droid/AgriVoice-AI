-- =====================================================
-- AgriVoice-AI: Migration V2 - Farm Spatial Infrastructure
-- Farm Zones, Plots & Production Locations
-- =====================================================

PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-- -----------------------------------------------------
-- 1. BANG ZONES (Khu vuc / Lo dat / Chuong trai / Nha mang)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS zones (
    -- Ma khu vuc (vi du: 'KHU_A', 'VUON_CAM_1', 'CHUONG_BO_02', 'AO_CA_1')
    zone_id TEXT PRIMARY KEY,

    -- Ten goi hien thi ro rang cho nguoi dung
    zone_name TEXT NOT NULL,

    -- Phan loai mang san xuat
    sector TEXT NOT NULL DEFAULT 'MIXED'
        CHECK (sector IN ('CROP', 'LIVESTOCK', 'AQUACULTURE', 'MIXED')),

    -- Dien tich hoac dung tich khu vuc
    area_size REAL
        CHECK (area_size IS NULL OR area_size >= 0),

    -- Don vi do dien tich/the tich
    unit_of_size TEXT NOT NULL DEFAULT 'm2'
        CHECK (unit_of_size IN ('m2', 'ha', 'm3')),

    -- Vi tri / Dia chi chi tiet trong trang trai
    address TEXT,

    -- Tom tat hien trang canh tac / vat nuoi hien tai
    current_stock_summary TEXT,

    -- Danh sach JSON cac khu vuc tiep giap (ho tro suy luan vi tri giap ranh)
    neighboring_zone_ids TEXT,

    -- Ten thuong goi / bi danh khau ngu nha nong hay dung
    convenient_names TEXT,

    -- Ghi chu dac tinh dat, nguon nuoc, thiet bi san co
    notes TEXT,

    -- Trang thai hoat dong (1: dang canh tac/su dung, 0: tam ngung)
    is_active INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1)),

    -- Thoi gian tao va cap nhat
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (length(trim(zone_id)) > 0),
    CHECK (length(trim(zone_name)) > 0)
);

-- -----------------------------------------------------
-- 2. INDEXES
-- -----------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_zones_name
    ON zones(zone_name);

CREATE INDEX IF NOT EXISTS idx_zones_sector
    ON zones(sector);

CREATE INDEX IF NOT EXISTS idx_zones_is_active
    ON zones(is_active);

-- -----------------------------------------------------
-- 3. TRIGGERS
-- -----------------------------------------------------
CREATE TRIGGER IF NOT EXISTS trg_zones_updated_at
AFTER UPDATE ON zones
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE zones
    SET updated_at = CURRENT_TIMESTAMP
    WHERE zone_id = NEW.zone_id;
END;

-- -----------------------------------------------------
-- 4. BACKWARD-COMPATIBILITY VIEW
-- Cung cap view production_locations cho cac truy van cu
-- -----------------------------------------------------
CREATE VIEW IF NOT EXISTS production_locations AS
SELECT
    zone_id AS location_id,
    zone_id AS code,
    zone_name AS name,
    sector,
    COALESCE(area_size, 0) AS size_value,
    unit_of_size AS size_unit,
    address,
    notes AS description,
    is_active,
    created_at,
    updated_at
FROM zones;

COMMIT;
