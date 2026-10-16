-- =====================================================
-- AgriVoice-AI: Migration V8 - Farm Issues & Incident Management
-- Field Incidents, Equipment Failures & Pests/Diseases
-- =====================================================

PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-- =====================================================
-- 1. BANG ISSUES (Su co tai khu vuc / lo dat / chuong trai)
-- =====================================================

CREATE TABLE IF NOT EXISTS issues (
    issue_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Khu vuc xay ra su co
    zone_id TEXT NOT NULL,

    -- Cong tac vien bao cao (lien ket voi bang collaborators)
    reporter_id INTEGER,

    -- Tieu de ngan gon su co
    title TEXT NOT NULL,

    -- Mo ta chi tiet trieu chung, hien truong
    description TEXT,

    -- Muc do nghiem trong
    severity TEXT NOT NULL DEFAULT 'MEDIUM'
        CHECK (severity IN (
            'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
        )),

    -- Tien do xu ly
    status TEXT NOT NULL DEFAULT 'OPEN'
        CHECK (status IN (
            'OPEN', 'IN_PROGRESS', 'CLOSED', 'CANCELLED'
        )),

    -- Nguoi bao cao (dang chuoi van ban de tuong thich voice bot)
    reported_by TEXT DEFAULT 'Bác giữ vườn',

    cycle_id INTEGER
        REFERENCES production_cycles(cycle_id) ON DELETE SET NULL,
    project_id INTEGER
        REFERENCES projects(project_id) ON DELETE SET NULL,
    task_id INTEGER
        REFERENCES tasks(task_id) ON DELETE SET NULL,

    -- Phuong an xu ly va ket qua
    resolution_notes TEXT,
    notes TEXT,
    pending_event_id INTEGER,

    -- Thoi diem dong su co
    closed_at TEXT,

    -- Thoi gian tao va cap nhat
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (zone_id)
        REFERENCES zones(zone_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    FOREIGN KEY (reporter_id)
        REFERENCES collaborators(collaborator_id)
        ON DELETE SET NULL,

    CHECK (length(trim(title)) > 0),
    CHECK (
        status != 'CLOSED'
        OR closed_at IS NOT NULL
    )
);

-- =====================================================
-- 2. INDEXES
-- =====================================================

-- Tim su co theo khu vuc
CREATE INDEX IF NOT EXISTS idx_issues_zone
    ON issues(zone_id);

-- Loc su co theo trang thai
CREATE INDEX IF NOT EXISTS idx_issues_status
    ON issues(status);

-- Uu tien xu ly su co nghiem trong
CREATE INDEX IF NOT EXISTS idx_issues_severity
    ON issues(severity);

-- Sap xep su co moi nhat
CREATE INDEX IF NOT EXISTS idx_issues_created_at
    ON issues(created_at);

-- Tim kiem theo nguoi bao cao
CREATE INDEX IF NOT EXISTS idx_issues_reporter_id
    ON issues(reporter_id);

-- =====================================================
-- 3. TRIGGERS
-- =====================================================

-- Tu dong cap nhat updated_at khi sua su co
CREATE TRIGGER IF NOT EXISTS trg_issues_updated_at
AFTER UPDATE ON issues
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE issues
    SET updated_at = CURRENT_TIMESTAMP
    WHERE issue_id = NEW.issue_id;
END;

-- Tu dong dong thoi gian khi chuyen trang thai sang CLOSED
CREATE TRIGGER IF NOT EXISTS trg_issues_auto_close
BEFORE UPDATE OF status ON issues
FOR EACH ROW
WHEN NEW.status = 'CLOSED' AND NEW.closed_at IS NULL
BEGIN
    UPDATE issues
    SET closed_at = CURRENT_TIMESTAMP
    WHERE issue_id = NEW.issue_id;
END;

COMMIT;
