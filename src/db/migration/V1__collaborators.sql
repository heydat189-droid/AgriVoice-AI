-- =====================================================
-- AgriVoice-AI: Migration V1 - Collaborators & Whitelist
-- Identity, Access Control & Telegram Whitelist
-- =====================================================

PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-- -----------------------------------------------------
-- 1. BANG COLLABORATORS (Danh sach nguoi dung duoc phep)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS collaborators (
    collaborator_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Telegram ID duoc luu dang TEXT tranh tran so nguyen lon tren cac he thong
    telegram_id TEXT NOT NULL UNIQUE,

    -- Ho va ten / Nickname
    full_name TEXT NOT NULL,

    -- Vai tro trong he thong
    role TEXT NOT NULL DEFAULT 'WORKER'
        CHECK (role IN ('OWNER', 'ADMIN', 'WORKER', 'VIEWER')),

    -- Kenh tuong tac duoc phep
    allowed_source TEXT NOT NULL DEFAULT 'GROUP'
        CHECK (allowed_source IN ('PRIVATE', 'GROUP', 'BOTH')),

    -- Trang thai hoat dong (1: dang hoat dong, 0: tam khoa)
    is_active INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1)),

    -- Ghi chu ve quyen han hoac ghi chu quan tri
    notes TEXT,

    -- ID cua nguoi tao ban ghi
    created_id TEXT,

    -- Thoi gian tao va cap nhat
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (length(trim(full_name)) > 0)
);

-- -----------------------------------------------------
-- 2. INDEXES
-- -----------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_collaborators_telegram_id
    ON collaborators(telegram_id);

CREATE INDEX IF NOT EXISTS idx_collaborators_full_name
    ON collaborators(full_name);

CREATE INDEX IF NOT EXISTS idx_collaborators_role
    ON collaborators(role);

CREATE INDEX IF NOT EXISTS idx_collaborators_is_active
    ON collaborators(is_active);

CREATE INDEX IF NOT EXISTS idx_collaborators_allowed_source
    ON collaborators(allowed_source);

-- -----------------------------------------------------
-- 3. TRIGGERS
-- -----------------------------------------------------
CREATE TRIGGER IF NOT EXISTS trg_collaborators_updated_at
AFTER UPDATE ON collaborators
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE collaborators
    SET updated_at = CURRENT_TIMESTAMP
    WHERE collaborator_id = NEW.collaborator_id;
END;

COMMIT;
