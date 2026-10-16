-- =====================================================
-- AgriVoice-AI: Migration V5 - Production Cycles & Harvest
-- Production Cycles, Logs, Harvests & Yield Records
-- =====================================================

PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-- =====================================================
-- 1. PRODUCTION CYCLES (Vu mua / Chu ky chan nuoi, thuy san)
-- =====================================================

CREATE TABLE IF NOT EXISTS production_cycles (
    cycle_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id           INTEGER REFERENCES production_cycles(cycle_id) ON DELETE SET NULL,
    project_id          INTEGER REFERENCES projects(project_id) ON DELETE SET NULL,
    zone_id             TEXT NOT NULL REFERENCES zones(zone_id) ON DELETE RESTRICT,

    code                TEXT UNIQUE,
    name                TEXT NOT NULL,
    description         TEXT,
    subject_name        TEXT NOT NULL DEFAULT '', -- Cay trong / vat nuoi cu the
    variety             TEXT,          -- Giong (vd: Huynh Long, F1, ...)

    start_date          TEXT NOT NULL,
    expected_end_date   TEXT,
    actual_end_date     TEXT,

    initial_stock       REAL CHECK (initial_stock IS NULL OR initial_stock >= 0),
    initial_stock_unit  TEXT,

    -- Lien ket truc tiep tu dien nong trai (dau vao giong/vat tu va dau ra nong san/thanh pham)
    input_category_id   INTEGER REFERENCES dictionary(dict_id) ON DELETE SET NULL,
    input_quantity      REAL DEFAULT 0.0 CHECK (input_quantity IS NULL OR input_quantity >= 0),
    input_unit          TEXT,

    area_size           REAL CHECK (area_size IS NULL OR area_size >= 0),
    unit_of_size        TEXT DEFAULT 'm2',
    expected_yield      REAL CHECK (expected_yield IS NULL OR expected_yield >= 0),

    output_category_id  INTEGER REFERENCES dictionary(dict_id) ON DELETE SET NULL,
    output_quantity     REAL CHECK (output_quantity IS NULL OR output_quantity >= 0),
    output_unit         TEXT,

    status              TEXT NOT NULL DEFAULT 'ACTIVE'
                        CHECK (status IN ('PLANNED', 'ACTIVE', 'COMPLETED', 'CANCELLED')),

    notes               TEXT,
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (length(trim(name)) > 0),
    CHECK (date(start_date) IS NOT NULL),
    CHECK (expected_end_date IS NULL OR date(expected_end_date) IS NOT NULL),
    CHECK (actual_end_date IS NULL OR date(actual_end_date) IS NOT NULL),
    CHECK (expected_end_date IS NULL OR date(expected_end_date) >= date(start_date)),
    CHECK (actual_end_date IS NULL OR date(actual_end_date) >= date(start_date))
);

-- =====================================================
-- 1.1. RUNNING TASKS (Cong viec thuc thi tren thuc dia)
-- =====================================================

CREATE TABLE IF NOT EXISTS running_tasks (
    running_task_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id            INTEGER REFERENCES production_cycles(cycle_id) ON DELETE CASCADE,
    project_id          INTEGER REFERENCES projects(project_id) ON DELETE CASCADE,
    task_id             INTEGER REFERENCES tasks(task_id) ON DELETE SET NULL,
    subtask_id          INTEGER REFERENCES subtasks(subtask_id) ON DELETE SET NULL,
    assigned_to         INTEGER REFERENCES collaborators(collaborator_id) ON DELETE SET NULL,

    name                TEXT NOT NULL,
    description         TEXT,
    scheduled_start     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    duration_minutes    INTEGER NOT NULL DEFAULT 30 CHECK (duration_minutes > 0),

    status              TEXT NOT NULL DEFAULT 'TODO'
                        CHECK (status IN ('TODO', 'IN_PROGRESS', 'DONE', 'SKIPPED', 'CANCELLED')),
    material_category_id INTEGER REFERENCES dictionary(dict_id) ON DELETE SET NULL,
    quantity_used       REAL CHECK (quantity_used IS NULL OR quantity_used > 0),
    material_unit       TEXT,
    inventory_transaction_id INTEGER REFERENCES inventory_transactions(transaction_id) ON DELETE SET NULL,
    pending_event_id    INTEGER,

    report_complete_at  TEXT,
    completion_notes    TEXT,
    is_active           INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),

    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (length(trim(name)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_running_tasks_cycle ON running_tasks(cycle_id);
CREATE INDEX IF NOT EXISTS idx_running_tasks_status ON running_tasks(status);
CREATE INDEX IF NOT EXISTS idx_running_tasks_start ON running_tasks(scheduled_start);
CREATE INDEX IF NOT EXISTS idx_running_tasks_assigned ON running_tasks(assigned_to);

-- =====================================================
-- 2. PRODUCTION LOGS (Nhat ky canh tac / cham soc)
-- =====================================================

CREATE TABLE IF NOT EXISTS production_logs (
    log_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id            INTEGER NOT NULL
                        REFERENCES production_cycles(cycle_id) ON DELETE RESTRICT,
    logged_by           INTEGER
                        REFERENCES collaborators(collaborator_id) ON DELETE SET NULL,

    log_date            TEXT NOT NULL,
    activity_type       TEXT NOT NULL DEFAULT 'OTHER'
                        CHECK (activity_type IN (
                            'SOWING', 'PLANTING', 'FERTILIZING',
                            'PEST_CONTROL', 'IRRIGATION', 'FEEDING',
                            'VACCINATION', 'WATER_QUALITY', 'PRUNING',
                            'WEEDING', 'HARVEST_PREP', 'OTHER'
                        )),
    title               TEXT NOT NULL,
    description         TEXT,

    quantity            REAL CHECK (quantity IS NULL OR quantity >= 0),
    unit                TEXT,
    material_name       TEXT,

    cost_amount         INTEGER CHECK (cost_amount IS NULL OR cost_amount >= 0),
    duration_minutes    INTEGER CHECK (duration_minutes IS NULL OR duration_minutes >= 0),

    notes               TEXT,
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (length(trim(title)) > 0),
    CHECK (date(log_date) IS NOT NULL)
);

-- =====================================================
-- 3. HARVESTS (Cac dot thu hoach)
-- =====================================================

CREATE TABLE IF NOT EXISTS harvests (
    harvest_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id        INTEGER NOT NULL
                    REFERENCES production_cycles(cycle_id) ON DELETE RESTRICT,
    code            TEXT UNIQUE,
    harvest_date    TEXT NOT NULL,

    harvest_type    TEXT NOT NULL DEFAULT 'MAIN'
                    CHECK (harvest_type IN ('MAIN', 'PARTIAL', 'FINAL')),

    total_quantity  REAL NOT NULL DEFAULT 0 CHECK (total_quantity >= 0),
    unit            TEXT NOT NULL DEFAULT 'kg',

    total_value     INTEGER CHECK (total_value IS NULL OR total_value >= 0),
    labor_cost      INTEGER NOT NULL DEFAULT 0 CHECK (labor_cost >= 0),
    other_cost      INTEGER NOT NULL DEFAULT 0 CHECK (other_cost >= 0),

    worker_name     TEXT,
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (date(harvest_date) IS NOT NULL)
);

-- =====================================================
-- 4. YIELD RECORDS (San luong chi tiet theo loai va phan hang)
-- =====================================================

CREATE TABLE IF NOT EXISTS yield_records (
    record_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    harvest_id          INTEGER NOT NULL
                        REFERENCES harvests(harvest_id) ON DELETE RESTRICT,

    output_type         TEXT NOT NULL DEFAULT 'HARVEST_CROP'
                        CHECK (output_type IN (
                            'HARVEST_CROP', 'MILK', 'EGGS',
                            'MEAT', 'FISH', 'OTHER'
                        )),

    product_name        TEXT NOT NULL,

    quantity_total      REAL NOT NULL DEFAULT 0 CHECK (quantity_total >= 0),
    quantity_grade_a    REAL NOT NULL DEFAULT 0 CHECK (quantity_grade_a >= 0),
    quantity_grade_b    REAL NOT NULL DEFAULT 0 CHECK (quantity_grade_b >= 0),
    quantity_defect     REAL NOT NULL DEFAULT 0 CHECK (quantity_defect >= 0),

    storage_quantity    REAL NOT NULL DEFAULT 0 CHECK (storage_quantity >= 0),

    unit                TEXT NOT NULL DEFAULT 'kg',
    unit_price          INTEGER CHECK (unit_price IS NULL OR unit_price >= 0),
    economic_value      INTEGER CHECK (economic_value IS NULL OR economic_value >= 0),
    actual_revenue      INTEGER CHECK (actual_revenue IS NULL OR actual_revenue >= 0),

    notes               TEXT,
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (length(trim(product_name)) > 0),
    CHECK (quantity_grade_a + quantity_grade_b + quantity_defect <= quantity_total),
    CHECK (storage_quantity <= quantity_total)
);

-- =====================================================
-- 5. INDEXES
-- =====================================================

CREATE INDEX IF NOT EXISTS idx_cycles_project
    ON production_cycles(project_id);

CREATE INDEX IF NOT EXISTS idx_cycles_zone
    ON production_cycles(zone_id);

CREATE INDEX IF NOT EXISTS idx_cycles_status_start_date
    ON production_cycles(status, start_date);

CREATE INDEX IF NOT EXISTS idx_production_logs_cycle_date
    ON production_logs(cycle_id, log_date);

CREATE INDEX IF NOT EXISTS idx_production_logs_type
    ON production_logs(activity_type);

CREATE INDEX IF NOT EXISTS idx_harvests_cycle_date
    ON harvests(cycle_id, harvest_date);

CREATE INDEX IF NOT EXISTS idx_yield_records_harvest
    ON yield_records(harvest_id);

-- =====================================================
-- 6. TRIGGERS
-- =====================================================

CREATE TRIGGER IF NOT EXISTS trg_production_cycles_updated_at
AFTER UPDATE ON production_cycles
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE production_cycles
    SET updated_at = CURRENT_TIMESTAMP
    WHERE cycle_id = NEW.cycle_id;
END;
CREATE TRIGGER IF NOT EXISTS trg_running_tasks_updated_at
AFTER UPDATE ON running_tasks
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE running_tasks
    SET updated_at = CURRENT_TIMESTAMP
    WHERE running_task_id = NEW.running_task_id;
END;

-- =====================================================
-- 7. VIEWS
-- =====================================================

CREATE VIEW IF NOT EXISTS v_cycle_yield_performance AS
SELECT 
    c.cycle_id,
    c.name AS cycle_name,
    c.status AS cycle_status,
    c.start_date,
    c.actual_end_date,
    p.name AS project_name,
    z.zone_name,
    c.area_size,
    c.unit_of_size,
    c.input_quantity,
    c.input_unit,
    c.expected_yield,
    c.output_quantity AS actual_yield,
    c.output_unit,
    CASE 
        WHEN c.area_size > 0 AND c.output_quantity IS NOT NULL 
        THEN ROUND(c.output_quantity / c.area_size, 2)
        ELSE NULL 
    END AS yield_per_area_unit,
    CASE 
        WHEN c.expected_yield > 0 AND c.output_quantity IS NOT NULL 
        THEN ROUND((c.output_quantity * 100.0) / c.expected_yield, 1)
        ELSE NULL 
    END AS yield_achievement_rate
FROM production_cycles c
LEFT JOIN projects p ON c.project_id = p.project_id
LEFT JOIN zones z ON c.zone_id = z.zone_id;

COMMIT;
