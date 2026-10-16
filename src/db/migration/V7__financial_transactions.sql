-- =====================================================
-- AgriVoice-AI: Migration V7 - Financial Management
-- Income & Expense Categories and Financial Transactions
-- =====================================================

PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-- =====================================================
-- 1. DANH MUC THU CHI (Transaction Categories)
-- =====================================================

CREATE TABLE IF NOT EXISTS transaction_categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL
        CHECK (type IN ('INCOME', 'EXPENSE')),
    parent_id INTEGER
        REFERENCES transaction_categories(category_id) ON DELETE SET NULL,
    is_cycle_mandatory INTEGER NOT NULL DEFAULT 0
        CHECK (is_cycle_mandatory IN (0, 1)),
    convenient_names TEXT,
    description TEXT,
    is_active INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(name)) > 0)
);

-- =====================================================
-- 2. GIAO DICH THU CHI (Financial Transactions)
-- =====================================================

CREATE TABLE IF NOT EXISTS financial_transactions (
    transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,

    cycle_id INTEGER
        REFERENCES production_cycles(cycle_id)
        ON DELETE SET NULL,

    category_id INTEGER NOT NULL
        REFERENCES transaction_categories(category_id)
        ON DELETE RESTRICT,

    supplier_id INTEGER
        REFERENCES suppliers(supplier_id)
        ON DELETE SET NULL,

    recorded_by INTEGER
        REFERENCES collaborators(collaborator_id)
        ON DELETE SET NULL,

    type TEXT NOT NULL
        CHECK (type IN ('INCOME', 'EXPENSE')),

    amount INTEGER NOT NULL
        CHECK (amount >= 0),

    transaction_date TEXT NOT NULL,

    partner_name TEXT,

    payment_method TEXT NOT NULL DEFAULT 'CASH'
        CHECK (payment_method IN (
            'CASH', 'TRANSFER', 'DEBT', 'BARTER'
        )),

    status TEXT NOT NULL DEFAULT 'COMPLETED'
        CHECK (status IN (
            'COMPLETED', 'PENDING', 'CANCELLED'
        )),

    barter_id INTEGER,
    invoice_image_path TEXT,
    inventory_transaction_id INTEGER
        REFERENCES inventory_transactions(transaction_id)
        ON DELETE SET NULL,
    pending_event_id INTEGER,
    is_estimated INTEGER NOT NULL DEFAULT 0
        CHECK (is_estimated IN (0, 1)),

    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (date(transaction_date) IS NOT NULL)
);

-- =====================================================
-- 2.1. TRAO DOI HANG HOA TRUC TIEP (Barter Transactions)
-- =====================================================

CREATE TABLE IF NOT EXISTS barter_transactions (
    barter_id INTEGER PRIMARY KEY AUTOINCREMENT,
    partner_name TEXT NOT NULL,

    give_category_id INTEGER NOT NULL
        REFERENCES dictionary(dict_id) ON DELETE RESTRICT,
    give_quantity REAL NOT NULL CHECK (give_quantity > 0),
    give_unit TEXT NOT NULL,
    give_cycle_id INTEGER
        REFERENCES production_cycles(cycle_id) ON DELETE SET NULL,
    give_inventory_tx_id INTEGER
        REFERENCES inventory_transactions(transaction_id) ON DELETE SET NULL,

    receive_category_id INTEGER NOT NULL
        REFERENCES dictionary(dict_id) ON DELETE RESTRICT,
    receive_quantity REAL NOT NULL CHECK (receive_quantity > 0),
    receive_unit TEXT NOT NULL,
    receive_cycle_id INTEGER
        REFERENCES production_cycles(cycle_id) ON DELETE SET NULL,
    receive_inventory_tx_id INTEGER
        REFERENCES inventory_transactions(transaction_id) ON DELETE SET NULL,

    estimated_value_vnd INTEGER NOT NULL DEFAULT 0
        CHECK (estimated_value_vnd >= 0),
    cash_difference_vnd INTEGER NOT NULL DEFAULT 0,
    payment_transaction_id INTEGER
        REFERENCES financial_transactions(transaction_id) ON DELETE SET NULL,

    status TEXT NOT NULL DEFAULT 'COMPLETED'
        CHECK (status IN ('COMPLETED', 'PENDING', 'CANCELLED')),
    notes TEXT,
    pending_event_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- 2.2. CONG NO CHI TIET (Debt Records & Payments)
-- =====================================================

CREATE TABLE IF NOT EXISTS debt_records (
    debt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    initial_transaction_id INTEGER
        REFERENCES financial_transactions(transaction_id) ON DELETE SET NULL,
    debt_type TEXT NOT NULL
        CHECK (debt_type IN ('PAYABLE', 'RECEIVABLE')),
    partner_name TEXT NOT NULL,
    supplier_id INTEGER
        REFERENCES suppliers(supplier_id) ON DELETE SET NULL,
    collaborator_id INTEGER
        REFERENCES collaborators(collaborator_id) ON DELETE SET NULL,

    initial_amount INTEGER NOT NULL CHECK (initial_amount > 0),
    paid_amount INTEGER NOT NULL DEFAULT 0
        CHECK (paid_amount >= 0 AND paid_amount <= initial_amount),
    remaining_amount INTEGER GENERATED ALWAYS AS
        (initial_amount - paid_amount) VIRTUAL,

    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'UNPAID'
        CHECK (status IN ('UNPAID', 'PARTIAL', 'SETTLED', 'CANCELLED')),

    notes TEXT,
    pending_event_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS debt_payments (
    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    debt_id INTEGER NOT NULL
        REFERENCES debt_records(debt_id) ON DELETE CASCADE,
    payment_transaction_id INTEGER NOT NULL
        REFERENCES financial_transactions(transaction_id) ON DELETE RESTRICT,
    amount_paid INTEGER NOT NULL CHECK (amount_paid > 0),
    payment_date TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- 3. INDEXES
-- =====================================================

CREATE INDEX IF NOT EXISTS idx_financial_transactions_date
    ON financial_transactions(transaction_date);

CREATE INDEX IF NOT EXISTS idx_financial_transactions_cycle
    ON financial_transactions(cycle_id);

CREATE INDEX IF NOT EXISTS idx_financial_transactions_category
    ON financial_transactions(category_id);

CREATE INDEX IF NOT EXISTS idx_financial_transactions_type_status
    ON financial_transactions(type, status);

CREATE INDEX IF NOT EXISTS idx_financial_transactions_recorded_by
    ON financial_transactions(recorded_by);

-- =====================================================
-- 4. TRIGGERS
-- =====================================================

CREATE TRIGGER IF NOT EXISTS trg_transaction_categories_updated_at
AFTER UPDATE ON transaction_categories
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE transaction_categories
    SET updated_at = CURRENT_TIMESTAMP
    WHERE category_id = NEW.category_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_debt_records_updated_at
AFTER UPDATE ON debt_records
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE debt_records
    SET updated_at = CURRENT_TIMESTAMP
    WHERE debt_id = NEW.debt_id;
END;

-- =====================================================
-- 5. VIEWS
-- =====================================================

CREATE VIEW IF NOT EXISTS v_cycle_financial_summary AS
SELECT 
    c.cycle_id,
    c.name AS cycle_name,
    c.status AS cycle_status,
    c.start_date,
    c.actual_end_date,
    p.name AS project_name,
    z.zone_name,
    COALESCE(SUM(CASE WHEN ft.type = 'INCOME' AND ft.status = 'COMPLETED' THEN ft.amount ELSE 0 END), 0) AS total_income_vnd,
    COALESCE(SUM(CASE WHEN ft.type = 'EXPENSE' AND ft.status = 'COMPLETED' THEN ft.amount ELSE 0 END), 0) AS total_expense_vnd,
    COALESCE(SUM(CASE WHEN ft.type = 'INCOME' AND ft.status = 'COMPLETED' THEN ft.amount ELSE 0 END), 0) -
    COALESCE(SUM(CASE WHEN ft.type = 'EXPENSE' AND ft.status = 'COMPLETED' THEN ft.amount ELSE 0 END), 0) AS net_profit_vnd,
    CASE 
        WHEN COALESCE(SUM(CASE WHEN ft.type = 'EXPENSE' AND ft.status = 'COMPLETED' THEN ft.amount ELSE 0 END), 0) > 0 
        THEN ROUND(
            (
                (COALESCE(SUM(CASE WHEN ft.type = 'INCOME' AND ft.status = 'COMPLETED' THEN ft.amount ELSE 0 END), 0) -
                 COALESCE(SUM(CASE WHEN ft.type = 'EXPENSE' AND ft.status = 'COMPLETED' THEN ft.amount ELSE 0 END), 0)) * 100.0
            ) / SUM(CASE WHEN ft.type = 'EXPENSE' AND ft.status = 'COMPLETED' THEN ft.amount ELSE 0 END),
            2
        )
        ELSE NULL 
    END AS roi_percentage,
    COUNT(ft.transaction_id) AS total_transaction_count
FROM production_cycles c
LEFT JOIN projects p ON c.project_id = p.project_id
LEFT JOIN zones z ON c.zone_id = z.zone_id
LEFT JOIN financial_transactions ft ON c.cycle_id = ft.cycle_id
GROUP BY c.cycle_id, c.name, c.status, c.start_date, c.actual_end_date, p.name, z.zone_name;

CREATE VIEW IF NOT EXISTS v_daily_cashflow_summary AS
SELECT 
    transaction_date,
    payment_method,
    COALESCE(SUM(CASE WHEN type = 'INCOME' THEN amount ELSE 0 END), 0) AS daily_income_vnd,
    COALESCE(SUM(CASE WHEN type = 'EXPENSE' THEN amount ELSE 0 END), 0) AS daily_expense_vnd,
    (COALESCE(SUM(CASE WHEN type = 'INCOME' THEN amount ELSE 0 END), 0) - 
     COALESCE(SUM(CASE WHEN type = 'EXPENSE' THEN amount ELSE 0 END), 0)) AS net_cashflow_vnd,
    COUNT(transaction_id) AS transaction_count
FROM financial_transactions
WHERE status = 'COMPLETED'
  AND payment_method IN ('CASH', 'TRANSFER')
GROUP BY transaction_date, payment_method;

COMMIT;
