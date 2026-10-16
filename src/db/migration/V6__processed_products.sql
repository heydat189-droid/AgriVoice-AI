-- =====================================================
-- AgriVoice-AI: Migration V6 - Value-Added Products
-- Processed Products, Recipes & Processing Batches
-- =====================================================

PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-- =====================================================
-- 1. THANH PHAM SAU CHE BIEN (Tra, hoa qua say, nuoc ep, tinh dau...)
-- =====================================================

CREATE TABLE IF NOT EXISTS processed_products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,

    sku TEXT NOT NULL UNIQUE,
    barcode TEXT UNIQUE,
    name TEXT NOT NULL,
    category TEXT,

    unit TEXT NOT NULL DEFAULT 'gói',
    unit_weight REAL
        CHECK (unit_weight IS NULL OR unit_weight >= 0),

    -- Gia ban le tham khao (VND)
    unit_price INTEGER
        CHECK (unit_price IS NULL OR unit_price >= 0),

    -- Tong so luong ton kho hien tai
    quantity_in_stock REAL NOT NULL DEFAULT 0
        CHECK (quantity_in_stock >= 0),

    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN (
            'ACTIVE', 'OUT_OF_STOCK', 'DISCONTINUED'
        )),

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (length(trim(sku)) > 0),
    CHECK (length(trim(name)) > 0)
);

-- =====================================================
-- 2. LO CHE BIEN (Processing Batches)
-- =====================================================

CREATE TABLE IF NOT EXISTS processing_batches (
    batch_id INTEGER PRIMARY KEY AUTOINCREMENT,

    batch_code TEXT NOT NULL UNIQUE,
    product_id INTEGER NOT NULL
        REFERENCES processed_products(product_id)
        ON DELETE RESTRICT,

    source_cycle_id INTEGER
        REFERENCES production_cycles(cycle_id)
        ON DELETE SET NULL,

    processing_date TEXT NOT NULL,

    raw_material_input_qty REAL NOT NULL DEFAULT 0
        CHECK (raw_material_input_qty >= 0),

    raw_material_unit TEXT NOT NULL DEFAULT 'kg',

    output_quantity REAL NOT NULL DEFAULT 0
        CHECK (output_quantity >= 0),

    defect_quantity REAL NOT NULL DEFAULT 0
        CHECK (defect_quantity >= 0),

    -- Chi phi gia cong che bien (VND)
    processing_cost INTEGER NOT NULL DEFAULT 0
        CHECK (processing_cost >= 0),

    expiry_date TEXT,
    notes TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (length(trim(batch_code)) > 0),
    CHECK (date(processing_date) IS NOT NULL),
    CHECK (
        expiry_date IS NULL
        OR date(expiry_date) >= date(processing_date)
    )
);

-- =====================================================
-- 3. INDEXES
-- =====================================================

CREATE INDEX IF NOT EXISTS idx_processed_products_name
    ON processed_products(name);

CREATE INDEX IF NOT EXISTS idx_processed_products_status
    ON processed_products(status);

CREATE INDEX IF NOT EXISTS idx_processing_batches_product
    ON processing_batches(product_id);

CREATE INDEX IF NOT EXISTS idx_processing_batches_source_cycle
    ON processing_batches(source_cycle_id);

CREATE INDEX IF NOT EXISTS idx_processing_batches_date
    ON processing_batches(processing_date);

-- =====================================================
-- 4. TRIGGERS
-- =====================================================

CREATE TRIGGER IF NOT EXISTS trg_processed_products_updated_at
AFTER UPDATE ON processed_products
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE processed_products
    SET updated_at = CURRENT_TIMESTAMP
    WHERE product_id = NEW.product_id;
END;

COMMIT;
