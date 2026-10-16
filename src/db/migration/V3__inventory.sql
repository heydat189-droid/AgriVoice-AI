-- =====================================================
-- AgriVoice-AI: Migration V3 - Farm Dictionary & Inventory
-- Unified Dictionary (Categories & Locations), Suppliers, Batches, Stock & Transactions
-- =====================================================

PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-- =====================================================
-- 1. TU DIEN NONG TRAI HOP NHAT (Unified Dictionary)
-- Hop nhat danh muc vat tu, nong san, giong cay va diem luu tru (kho)
-- =====================================================

CREATE TABLE IF NOT EXISTS dictionary (
    dict_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER,
    warehouse_id INTEGER,
    product_id INTEGER,
    code TEXT UNIQUE,
    sku TEXT UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    parent_id INTEGER REFERENCES dictionary(dict_id) ON DELETE SET NULL,
    level INTEGER NOT NULL DEFAULT 0,
    root_path TEXT NOT NULL DEFAULT '/',
    entry_type TEXT NOT NULL DEFAULT 'CATEGORY'
        CHECK (entry_type IN ('CATEGORY', 'LOCATION', 'SERVICE', 'OTHER')),
    zone_id TEXT REFERENCES zones(zone_id) ON DELETE SET NULL,
    warehouse_type TEXT DEFAULT 'STANDARD',
    address TEXT,
    default_unit_id INTEGER,
    base_unit_id INTEGER,
    barcode TEXT,
    item_type TEXT DEFAULT 'CONSUMABLE',
    tracking_method TEXT DEFAULT 'LOT',
    brand TEXT,
    specification TEXT,
    manufacturer TEXT,
    country_of_origin TEXT,
    unit_price_vnd INTEGER DEFAULT 0,
    standard_cost_vnd INTEGER DEFAULT 0,
    min_stock REAL DEFAULT 0.0,
    reorder_level REAL DEFAULT 0.0,
    max_stock REAL,
    requires_batch_tracking INTEGER DEFAULT 1,
    requires_expiry_tracking INTEGER NOT NULL DEFAULT 0
        CHECK (requires_expiry_tracking IN (0, 1)),
    storage_instructions TEXT,
    registration_number TEXT,
    active_ingredient TEXT,
    formulation TEXT,
    status TEXT DEFAULT 'ACTIVE',
    convenient_names TEXT,
    is_active INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (parent_id IS NULL OR parent_id <> dict_id)
);

CREATE TRIGGER IF NOT EXISTS trg_dictionary_populate_ids
AFTER INSERT ON dictionary
FOR EACH ROW
BEGIN
    UPDATE dictionary
    SET category_id = NEW.dict_id,
        warehouse_id = NEW.dict_id,
        product_id = NEW.dict_id,
        sku = COALESCE(NEW.sku, NEW.code),
        code = COALESCE(NEW.code, NEW.sku),
        base_unit_id = COALESCE(NEW.base_unit_id, NEW.default_unit_id),
        default_unit_id = COALESCE(NEW.default_unit_id, NEW.base_unit_id)
    WHERE dict_id = NEW.dict_id
      AND (category_id IS NULL OR warehouse_id IS NULL OR product_id IS NULL OR sku IS NULL OR code IS NULL);
END;

CREATE TABLE IF NOT EXISTS units (
    unit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    symbol TEXT,
    is_active INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS category_unit_conversions (
    conversion_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL
        REFERENCES dictionary(dict_id) ON DELETE CASCADE,
    unit_id INTEGER NOT NULL REFERENCES units(unit_id) ON DELETE RESTRICT,
    factor_to_base REAL NOT NULL CHECK (factor_to_base > 0),
    is_default_input INTEGER NOT NULL DEFAULT 0
        CHECK (is_default_input IN (0, 1)),
    is_default_output INTEGER NOT NULL DEFAULT 0
        CHECK (is_default_output IN (0, 1)),
    UNIQUE (category_id, unit_id)
);

CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    contact_name TEXT,
    contact_info TEXT,
    email TEXT,
    phone TEXT,
    address TEXT,
    tax_code TEXT,
    resources_path TEXT,
    convenient_names TEXT,
    reliability_rating REAL DEFAULT 5.0,
    notes TEXT,
    description TEXT,
    is_active INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- 2. LO VAT TU & HANG HOA (Product Batches)
-- =====================================================

CREATE TABLE IF NOT EXISTS product_batches (
    batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_code TEXT,
    batch_number TEXT,
    category_id INTEGER REFERENCES dictionary(dict_id) ON DELETE RESTRICT,
    product_id INTEGER REFERENCES dictionary(dict_id) ON DELETE RESTRICT,
    warehouse_id INTEGER REFERENCES dictionary(dict_id) ON DELETE SET NULL,
    supplier_id INTEGER REFERENCES suppliers(supplier_id) ON DELETE SET NULL,
    location_id INTEGER,

    manufacturing_date TEXT,
    date_received TEXT NOT NULL DEFAULT (date('now')),
    expiry_date TEXT,

    -- So luong ton kho thuc te, cho phep am khi xuat truoc nhap sau
    quantity_remaining REAL NOT NULL DEFAULT 0.0,
    base_unit_id INTEGER NOT NULL DEFAULT 1 REFERENCES units(unit_id) ON DELETE RESTRICT,
    cost_price_vnd INTEGER NOT NULL DEFAULT 0
        CHECK (cost_price_vnd >= 0),

    is_virtual INTEGER NOT NULL DEFAULT 0
        CHECK (is_virtual IN (0, 1)),

    status TEXT NOT NULL DEFAULT 'AVAILABLE'
        CHECK (status IN (
            'AVAILABLE', 'QUARANTINE', 'BLOCKED',
            'EXPIRED', 'DEPLETED', 'NEGATIVE_ALERT'
        )),

    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER IF NOT EXISTS trg_product_batches_populate_defaults
AFTER INSERT ON product_batches
FOR EACH ROW
BEGIN
    UPDATE product_batches
    SET category_id = COALESCE(NEW.category_id, NEW.product_id),
        product_id = COALESCE(NEW.product_id, NEW.category_id),
        batch_code = COALESCE(NEW.batch_code, NEW.batch_number, 'BATCH-' || NEW.batch_id),
        batch_number = COALESCE(NEW.batch_number, NEW.batch_code, 'BATCH-' || NEW.batch_id)
    WHERE batch_id = NEW.batch_id
      AND (category_id IS NULL OR product_id IS NULL OR batch_code IS NULL OR batch_number IS NULL);
END;

-- =====================================================
-- 3. GIAO DICH KHO (Inventory Transactions)
-- =====================================================

CREATE TABLE IF NOT EXISTS inventory_transactions (
    transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name TEXT NOT NULL DEFAULT '',
    category_id INTEGER REFERENCES dictionary(dict_id) ON DELETE RESTRICT,
    product_id INTEGER REFERENCES dictionary(dict_id) ON DELETE RESTRICT,
    batch_id INTEGER REFERENCES product_batches(batch_id) ON DELETE RESTRICT,
    warehouse_id INTEGER REFERENCES dictionary(dict_id) ON DELETE SET NULL,
    location_id INTEGER,
    supplier_id INTEGER REFERENCES suppliers(supplier_id) ON DELETE SET NULL,
    cycle_id INTEGER,
    financial_transaction_id INTEGER,
    pending_event_id INTEGER,

    transaction_type TEXT NOT NULL
        CHECK (transaction_type IN (
            'RECEIPT', 'ISSUE', 'RETURN_IN', 'RETURN_OUT',
            'ADJUSTMENT_IN', 'ADJUSTMENT_OUT',
            'TRANSFER_IN', 'TRANSFER_OUT',
            'EXPIRED_WRITE_OFF', 'DISCARD'
        )),

    quantity_change REAL NOT NULL CHECK (quantity_change <> 0),
    unit_id INTEGER NOT NULL REFERENCES units(unit_id) ON DELETE RESTRICT,
    quantity_base REAL NOT NULL DEFAULT 0.0,
    unit_price_vnd INTEGER NOT NULL DEFAULT 0
        CHECK (unit_price_vnd >= 0),
    unit_cost_vnd INTEGER DEFAULT 0,
    is_price_estimated INTEGER NOT NULL DEFAULT 0
        CHECK (is_price_estimated IN (0, 1)),

    reference_type TEXT,
    reference_number TEXT,
    reference_note TEXT,
    performed_by TEXT,

    status TEXT NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT', 'POSTED', 'CANCELLED')),

    notes TEXT,
    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER IF NOT EXISTS trg_inventory_transactions_populate_defaults
AFTER INSERT ON inventory_transactions
FOR EACH ROW
BEGIN
    UPDATE inventory_transactions
    SET category_id = COALESCE(NEW.category_id, NEW.product_id),
        quantity_base = CASE WHEN NEW.quantity_base = 0.0 THEN ABS(NEW.quantity_change) ELSE NEW.quantity_base END,
        unit_price_vnd = CASE WHEN NEW.unit_price_vnd = 0 AND NEW.unit_cost_vnd > 0 THEN NEW.unit_cost_vnd ELSE NEW.unit_price_vnd END,
        unit_cost_vnd = CASE WHEN NEW.unit_cost_vnd = 0 AND NEW.unit_price_vnd > 0 THEN NEW.unit_price_vnd ELSE NEW.unit_cost_vnd END,
        item_name = CASE WHEN NEW.item_name = '' THEN 'Item #' || COALESCE(NEW.category_id, NEW.product_id, 0) ELSE NEW.item_name END
    WHERE transaction_id = NEW.transaction_id
      AND (category_id IS NULL OR product_id IS NULL OR quantity_base = 0.0 OR item_name = '');
END;

-- =====================================================
-- 4. VIEWS TUONG THICH NGUOC (Backward-compatible Views)
-- =====================================================

CREATE VIEW IF NOT EXISTS categories AS
SELECT
    dict_id AS category_id,
    code,
    name,
    description,
    parent_id,
    level,
    root_path,
    default_unit_id,
    requires_expiry_tracking,
    convenient_names,
    is_active,
    created_at,
    updated_at
FROM dictionary
WHERE entry_type <> 'LOCATION';

CREATE TRIGGER IF NOT EXISTS trg_categories_view_insert
INSTEAD OF INSERT ON categories
FOR EACH ROW
BEGIN
    INSERT INTO dictionary (
        code, name, description, parent_id, level, root_path, entry_type,
        default_unit_id, requires_expiry_tracking, convenient_names, is_active
    ) VALUES (
        NEW.code, NEW.name, NEW.description, NEW.parent_id,
        COALESCE(NEW.level, 0), COALESCE(NEW.root_path, '/'),
        'CATEGORY', NEW.default_unit_id,
        COALESCE(NEW.requires_expiry_tracking, 0), NEW.convenient_names,
        COALESCE(NEW.is_active, 1)
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_categories_view_update
INSTEAD OF UPDATE ON categories
FOR EACH ROW
BEGIN
    UPDATE dictionary
    SET code = NEW.code,
        name = NEW.name,
        description = NEW.description,
        parent_id = NEW.parent_id,
        level = COALESCE(NEW.level, OLD.level),
        root_path = COALESCE(NEW.root_path, OLD.root_path),
        default_unit_id = NEW.default_unit_id,
        requires_expiry_tracking = COALESCE(NEW.requires_expiry_tracking, OLD.requires_expiry_tracking),
        convenient_names = NEW.convenient_names,
        is_active = COALESCE(NEW.is_active, OLD.is_active),
        updated_at = CURRENT_TIMESTAMP
    WHERE dict_id = OLD.category_id;
END;

CREATE VIEW IF NOT EXISTS warehouses AS
SELECT
    dict_id AS warehouse_id,
    code,
    name,
    zone_id,
    'STANDARD' AS warehouse_type,
    NULL AS address,
    description,
    convenient_names,
    is_active,
    created_at,
    updated_at
FROM dictionary
WHERE entry_type = 'LOCATION' OR root_path LIKE '/kho/%';

CREATE TRIGGER IF NOT EXISTS trg_warehouses_view_insert
INSTEAD OF INSERT ON warehouses
FOR EACH ROW
BEGIN
    INSERT INTO dictionary (
        code, name, zone_id, description, entry_type, root_path, convenient_names, is_active
    ) VALUES (
        NEW.code, NEW.name, NEW.zone_id, NEW.description, 'LOCATION', '/kho/',
        NEW.convenient_names, COALESCE(NEW.is_active, 1)
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_warehouses_view_update
INSTEAD OF UPDATE ON warehouses
FOR EACH ROW
BEGIN
    UPDATE dictionary
    SET code = NEW.code,
        name = NEW.name,
        zone_id = NEW.zone_id,
        description = NEW.description,
        convenient_names = NEW.convenient_names,
        is_active = COALESCE(NEW.is_active, OLD.is_active),
        updated_at = CURRENT_TIMESTAMP
    WHERE dict_id = OLD.warehouse_id;
END;

CREATE VIEW IF NOT EXISTS products AS
SELECT
    dict_id AS product_id,
    code AS sku,
    code AS barcode,
    name,
    description,
    parent_id AS category_id,
    NULL AS supplier_id,
    COALESCE(default_unit_id, 1) AS base_unit_id,
    'CONSUMABLE' AS item_type,
    'LOT' AS tracking_method,
    NULL AS brand,
    NULL AS specification,
    NULL AS manufacturer,
    NULL AS country_of_origin,
    0 AS unit_price_vnd,
    0 AS standard_cost_vnd,
    0.0 AS min_stock,
    0.0 AS reorder_level,
    NULL AS max_stock,
    1 AS requires_batch_tracking,
    requires_expiry_tracking,
    NULL AS storage_instructions,
    NULL AS registration_number,
    NULL AS active_ingredient,
    NULL AS formulation,
    CASE WHEN is_active = 1 THEN 'ACTIVE' ELSE 'INACTIVE' END AS status,
    created_at,
    updated_at
FROM dictionary
WHERE entry_type <> 'LOCATION';

CREATE TRIGGER IF NOT EXISTS trg_products_insert_view
INSTEAD OF INSERT ON products
FOR EACH ROW
BEGIN
    INSERT INTO dictionary (
        code, name, description, parent_id, default_unit_id,
        requires_expiry_tracking, is_active
    ) VALUES (
        NEW.sku, NEW.name, NEW.description, NEW.category_id, COALESCE(NEW.base_unit_id, 1),
        COALESCE(NEW.requires_expiry_tracking, 0),
        CASE WHEN NEW.status = 'INACTIVE' THEN 0 ELSE 1 END
    );
END;

CREATE VIEW IF NOT EXISTS product_unit_conversions AS
SELECT
    conversion_id,
    category_id AS product_id,
    unit_id,
    factor_to_base,
    is_default_input AS is_purchase_unit,
    is_default_output AS is_issue_unit
FROM category_unit_conversions;

CREATE TRIGGER IF NOT EXISTS trg_product_unit_conversions_insert_view
INSTEAD OF INSERT ON product_unit_conversions
FOR EACH ROW
BEGIN
    INSERT INTO category_unit_conversions (
        category_id, unit_id, factor_to_base, is_default_input, is_default_output
    ) VALUES (
        NEW.product_id, NEW.unit_id, NEW.factor_to_base,
        COALESCE(NEW.is_purchase_unit, 0), COALESCE(NEW.is_issue_unit, 0)
    );
END;

-- =====================================================
-- 5. KIEM KE KHO (Stock Counts)
-- =====================================================

CREATE TABLE IF NOT EXISTS stock_counts (
    stock_count_id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    warehouse_id INTEGER REFERENCES dictionary(dict_id) ON DELETE SET NULL,
    count_date TEXT NOT NULL DEFAULT (date('now')),
    status TEXT NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')),
    performed_by TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (date(count_date) IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS stock_count_lines (
    line_id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_count_id INTEGER NOT NULL
        REFERENCES stock_counts(stock_count_id) ON DELETE CASCADE,
    category_id INTEGER REFERENCES dictionary(dict_id) ON DELETE RESTRICT,
    product_id INTEGER REFERENCES dictionary(dict_id) ON DELETE RESTRICT,
    batch_id INTEGER REFERENCES product_batches(batch_id) ON DELETE SET NULL,
    location_id INTEGER,
    system_quantity REAL NOT NULL CHECK (system_quantity >= 0),
    counted_quantity REAL NOT NULL CHECK (counted_quantity >= 0),
    variance REAL GENERATED ALWAYS AS
        (counted_quantity - system_quantity) VIRTUAL,
    notes TEXT
);

CREATE TRIGGER IF NOT EXISTS trg_stock_count_lines_populate_defaults
AFTER INSERT ON stock_count_lines
FOR EACH ROW
BEGIN
    UPDATE stock_count_lines
    SET category_id = COALESCE(NEW.category_id, NEW.product_id),
        product_id = COALESCE(NEW.product_id, NEW.category_id)
    WHERE line_id = NEW.line_id
      AND (category_id IS NULL OR product_id IS NULL);
END;

-- =====================================================
-- 6. INDEXES
-- =====================================================

CREATE INDEX IF NOT EXISTS idx_dictionary_parent
    ON dictionary(parent_id);

CREATE INDEX IF NOT EXISTS idx_dictionary_root_path
    ON dictionary(root_path);

CREATE INDEX IF NOT EXISTS idx_dictionary_entry_type
    ON dictionary(entry_type);

CREATE INDEX IF NOT EXISTS idx_batches_category
    ON product_batches(category_id);

CREATE INDEX IF NOT EXISTS idx_batches_expiry
    ON product_batches(expiry_date);

CREATE INDEX IF NOT EXISTS idx_batches_warehouse
    ON product_batches(warehouse_id);

CREATE INDEX IF NOT EXISTS idx_transactions_category_time
    ON inventory_transactions(category_id, timestamp);

CREATE INDEX IF NOT EXISTS idx_transactions_batch
    ON inventory_transactions(batch_id);

CREATE INDEX IF NOT EXISTS idx_transactions_status
    ON inventory_transactions(status);

CREATE INDEX IF NOT EXISTS idx_count_lines_count
    ON stock_count_lines(stock_count_id);

-- =====================================================
-- 7. TRIGGERS
-- =====================================================

CREATE TRIGGER IF NOT EXISTS trg_suppliers_updated_at
AFTER UPDATE ON suppliers
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE suppliers
    SET updated_at = CURRENT_TIMESTAMP
    WHERE supplier_id = NEW.supplier_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_dictionary_updated_at
AFTER UPDATE ON dictionary
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE dictionary
    SET updated_at = CURRENT_TIMESTAMP
    WHERE dict_id = NEW.dict_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_product_batches_updated_at
AFTER UPDATE ON product_batches
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE product_batches
    SET updated_at = CURRENT_TIMESTAMP
    WHERE batch_id = NEW.batch_id;
END;

-- Cap nhat so luong ton khi them giao dich POSTED truc tiep
CREATE TRIGGER IF NOT EXISTS trg_transaction_apply_insert
AFTER INSERT ON inventory_transactions
WHEN NEW.status = 'POSTED'
 AND NEW.batch_id IS NOT NULL
BEGIN
    UPDATE product_batches
    SET quantity_remaining =
            quantity_remaining + NEW.quantity_change,
        status = CASE
            WHEN quantity_remaining + NEW.quantity_change = 0
                THEN 'DEPLETED'
            WHEN quantity_remaining + NEW.quantity_change < 0
                THEN 'NEGATIVE_ALERT'
            ELSE 'AVAILABLE'
        END
    WHERE batch_id = NEW.batch_id;
END;

-- Validation khi chuyen giao dich tu DRAFT sang POSTED
CREATE TRIGGER IF NOT EXISTS trg_transaction_validate_post
BEFORE UPDATE OF status ON inventory_transactions
WHEN OLD.status <> 'POSTED' AND NEW.status = 'POSTED'
BEGIN
    SELECT CASE
        WHEN OLD.status <> 'DRAFT'
        THEN RAISE(ABORT, 'Only draft transactions can be posted')
    END;

    SELECT CASE
        WHEN NEW.batch_id IS NOT NULL
         AND NOT EXISTS (
             SELECT 1
             FROM product_batches b
             WHERE b.batch_id = NEW.batch_id
               AND b.category_id = NEW.category_id
               AND (NEW.warehouse_id IS NULL OR b.warehouse_id IS NULL OR b.warehouse_id = NEW.warehouse_id)
         )
        THEN RAISE(ABORT, 'Invalid batch, category, warehouse or location')
    END;

    SELECT CASE
        WHEN NEW.batch_id IS NOT NULL
         AND (
             SELECT requires_expiry_tracking
             FROM dictionary WHERE dict_id = NEW.category_id
         ) = 1
         AND (
             SELECT expiry_date
             FROM product_batches
             WHERE batch_id = NEW.batch_id
         ) IS NULL
        THEN RAISE(ABORT, 'Expiry date is required for this category')
    END;
END;

-- Cap nhat so luong ton khi chuyen giao dich sang POSTED
CREATE TRIGGER IF NOT EXISTS trg_transaction_apply_post
AFTER UPDATE OF status ON inventory_transactions
WHEN OLD.status <> 'POSTED'
 AND NEW.status = 'POSTED'
 AND NEW.batch_id IS NOT NULL
BEGIN
    UPDATE product_batches
    SET quantity_remaining =
            quantity_remaining + NEW.quantity_change,
        status = CASE
            WHEN quantity_remaining + NEW.quantity_change = 0
                THEN 'DEPLETED'
            WHEN quantity_remaining + NEW.quantity_change < 0
                THEN 'NEGATIVE_ALERT'
            ELSE 'AVAILABLE'
        END
    WHERE batch_id = NEW.batch_id;
END;

-- Khong cho phep sua hoac xoa giao dich da POSTED
CREATE TRIGGER IF NOT EXISTS trg_transaction_no_edit_posted
BEFORE UPDATE ON inventory_transactions
WHEN OLD.status = 'POSTED'
  AND (OLD.category_id IS NOT NULL AND OLD.product_id IS NOT NULL AND OLD.item_name <> '')
BEGIN
    SELECT RAISE(ABORT, 'Posted transactions are immutable');
END;

-- Khong cho phep xoa giao dich da POSTED
CREATE TRIGGER IF NOT EXISTS trg_transaction_no_delete_posted
BEFORE DELETE ON inventory_transactions
WHEN OLD.status = 'POSTED'
BEGIN
    SELECT RAISE(ABORT, 'Posted transactions cannot be deleted');
END;

-- =====================================================
-- 8. VIEW TONG HOP TON KHO THEO NHOM GOC
-- =====================================================

CREATE VIEW IF NOT EXISTS v_inventory_root_summary AS
WITH RECURSIVE dict_tree AS (
    SELECT
        dict_id AS current_id,
        dict_id AS root_id,
        name AS root_name
    FROM dictionary
    WHERE parent_id IS NULL OR level = 0

    UNION ALL

    SELECT
        d.dict_id AS current_id,
        dt.root_id,
        dt.root_name
    FROM dictionary d
    JOIN dict_tree dt ON d.parent_id = dt.current_id
)
SELECT
    dt.root_id,
    dt.root_name,
    pb.warehouse_id,
    w.name AS warehouse_name,
    pb.base_unit_id,
    u.name AS unit_name,
    ROUND(SUM(pb.quantity_remaining), 3) AS total_quantity,
    CASE
        WHEN SUM(pb.quantity_remaining) < 0 THEN 'NEGATIVE_ANOMALY'
        WHEN SUM(pb.quantity_remaining) = 0 THEN 'EMPTY'
        ELSE 'IN_STOCK'
    END AS inventory_health,
    COUNT(DISTINCT pb.batch_id) AS active_batches_count,
    MIN(pb.expiry_date) AS nearest_expiry_date,
    MAX(pb.updated_at) AS last_updated_at
FROM product_batches pb
JOIN dict_tree dt ON pb.category_id = dt.current_id
JOIN units u ON pb.base_unit_id = u.unit_id
LEFT JOIN dictionary w ON pb.warehouse_id = w.dict_id
GROUP BY dt.root_id, dt.root_name, pb.warehouse_id, w.name, pb.base_unit_id, u.name;

COMMIT;
