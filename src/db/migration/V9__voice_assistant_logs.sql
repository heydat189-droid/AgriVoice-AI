-- =====================================================
-- AgriVoice-AI: Migration V9 - Voice AI Assistant Logs & Staging Queue
-- Raw Voice Auditing, Transcripts & Pending Events Staging Queue
-- =====================================================

PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-- =====================================================
-- 1. BANG PENDING_EVENTS (Vung dem In-Flight Buffer & Hang doi kiem duyet)
-- =====================================================

CREATE TABLE IF NOT EXISTS pending_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Telegram Sender ID cua nguoi gui tin nhan thoai
    sender_id TEXT NOT NULL DEFAULT 'AI_ASSISTANT',
    -- Thoi gian bac giu vuon gui voice (khoa sap xep duyet tuan tu Strict Ordering)
    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Bang dich nhan du lieu (vd: 'inventory_transactions', 'tasks', 'issues', 'harvests')
    target_table TEXT NOT NULL,

    -- Hanh dong can thuc thi tren bang dich
    action_type TEXT NOT NULL
        CHECK (action_type IN ('INSERT', 'UPDATE', 'DELETE')),

    -- Duong dan file audio goc tren Pi de chu vuon bam nghe lai
    audio_path TEXT,

    -- Van ban giong noi bóc băng tu AI de chu vuon doi chieu ngay lap tuc
    raw_transcript TEXT NOT NULL DEFAULT '',

    -- Tom tat ngan gon su kien (de hien thi tren the thong bao / Tab Cho Duyet)
    summary_text TEXT,

    -- Chuoi JSON nén gon chua toan bo du lieu do AI boc tach
    payload_json TEXT NOT NULL
        CHECK (json_valid(payload_json)),

    -- Trang thai kiem duyet: PENDING (Cho duyet), APPROVED (Da duyet), REJECTED (Tu choi), ERROR (Loi thuc thi)
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'ERROR')),

    -- Thong diep loi chi tiet neu qua trinh insert / update vao bang dich bi loi
    error_message TEXT,

    -- Chu vuon / quan ly thuc hien duyet hoac tu choi
    reviewed_by INTEGER,

    -- Thoi diem duoc duyet hoac tu choi (luu vet Audit Trail)
    reviewed_at TEXT,

    -- Ghi chu cua chu vuon khi duyet hoac ly do tu choi
    review_notes TEXT,

    -- Alias log_id de tuong thich ma nguon cu
    log_id INTEGER,

    -- Thoi gian tao va cap nhat ban ghi
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (reviewed_by)
        REFERENCES collaborators(collaborator_id)
        ON DELETE SET NULL,

    CHECK (length(trim(target_table)) > 0)
);

-- Backward-compatible view cho voice_raw_logs cu
CREATE VIEW IF NOT EXISTS voice_raw_logs AS
SELECT
    event_id AS log_id,
    timestamp,
    sender_id,
    audio_path AS audio_file_path,
    raw_transcript,
    NULL AS detected_intent,
    payload_json AS ai_response_json,
    CASE 
        WHEN status = 'APPROVED' THEN 'SUCCESS'
        WHEN status = 'ERROR' THEN 'ERROR'
        ELSE 'PENDING_APPROVAL'
    END AS execution_status,
    error_message
FROM pending_events;

CREATE TRIGGER IF NOT EXISTS trg_voice_raw_logs_insert_view
INSTEAD OF INSERT ON voice_raw_logs
FOR EACH ROW
BEGIN
    INSERT INTO pending_events (
        sender_id, audio_path, raw_transcript,
        target_table, action_type, payload_json, status, error_message
    ) VALUES (
        COALESCE(NEW.sender_id, 'VOICE_USER'),
        COALESCE(NEW.audio_file_path, ''),
        COALESCE(NEW.raw_transcript, ''),
        'voice_raw_logs',
        'INSERT',
        COALESCE(NEW.ai_response_json, '{}'),
        CASE WHEN NEW.execution_status = 'ERROR' THEN 'ERROR' ELSE 'PENDING' END,
        NEW.error_message
    );
END;
-- 3. INDEXES
-- =====================================================

-- Chi muc cho pending_events
CREATE INDEX IF NOT EXISTS idx_pending_events_sender
    ON pending_events(sender_id);

CREATE INDEX IF NOT EXISTS idx_pending_events_timestamp
    ON pending_events(timestamp);
-- Chi muc cho pending_events:
-- Chi muc quan trong nhat cho hang doi duyet theo thu tu thoi gian nghiem ngat (Strict Ordering)
CREATE INDEX IF NOT EXISTS idx_pending_events_queue
    ON pending_events(status, timestamp ASC, event_id ASC);

-- Loc theo bang dich va trang thai
CREATE INDEX IF NOT EXISTS idx_pending_events_target
    ON pending_events(target_table, status);

-- Truy vet nguoc tu nhat ky voice
CREATE INDEX IF NOT EXISTS idx_pending_events_log_id
    ON pending_events(log_id);

-- Loc theo nguoi duyet
CREATE INDEX IF NOT EXISTS idx_pending_events_reviewed_by
    ON pending_events(reviewed_by);

-- Loc theo nguoi gui
CREATE INDEX IF NOT EXISTS idx_pending_events_sender
    ON pending_events(sender_id);
-- 4. TRIGGERS
-- =====================================================

-- Tu dong cap nhat updated_at khi sua pending_events
CREATE TRIGGER IF NOT EXISTS trg_pending_events_updated_at
AFTER UPDATE ON pending_events
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE pending_events
    SET updated_at = CURRENT_TIMESTAMP
    WHERE event_id = NEW.event_id;
END;

-- Tu dong dien reviewed_at khi status chuyen sang APPROVED hoac REJECTED
CREATE TRIGGER IF NOT EXISTS trg_pending_events_auto_reviewed_at
BEFORE UPDATE OF status ON pending_events
FOR EACH ROW
WHEN NEW.status IN ('APPROVED', 'REJECTED') AND NEW.reviewed_at IS NULL
BEGIN
    UPDATE pending_events
    SET reviewed_at = CURRENT_TIMESTAMP
    WHERE event_id = NEW.event_id;
END;

-- =====================================================
-- 5. VIEWS
-- =====================================================

-- Hang doi cac su kien dang cho duyet sap xep theo thu tu thoi gian (Strict Queue)
CREATE VIEW IF NOT EXISTS v_pending_events_queue AS
SELECT
    p.event_id,
    p.log_id,
    p.sender_id,
    p.timestamp,
    p.target_table,
    p.action_type,
    p.audio_path,
    p.raw_transcript,
    p.summary_text,
    p.payload_json,
    p.status,
    p.error_message,
    p.reviewed_by,
    c.full_name AS reviewer_name,
    p.reviewed_at,
    p.review_notes,
    p.created_at,
    p.updated_at
FROM pending_events p
LEFT JOIN collaborators c ON p.reviewed_by = c.collaborator_id
WHERE p.status = 'PENDING' AND p.target_table <> 'voice_raw_logs'
ORDER BY p.timestamp ASC, p.event_id ASC;

-- Lich su toan bo cac su kien de Chu vuon tra cuu kiem toan (Audit Trail)
CREATE VIEW IF NOT EXISTS v_pending_events_history AS
SELECT
    p.event_id,
    p.log_id,
    p.sender_id,
    p.timestamp,
    p.target_table,
    p.action_type,
    p.audio_path,
    p.raw_transcript,
    p.summary_text,
    p.payload_json,
    p.status,
    p.error_message,
    p.reviewed_by,
    c.full_name AS reviewer_name,
    p.reviewed_at,
    p.review_notes,
    p.created_at,
    p.updated_at
FROM pending_events p
LEFT JOIN collaborators c ON p.reviewed_by = c.collaborator_id
WHERE p.target_table <> 'voice_raw_logs'
ORDER BY p.timestamp DESC, p.event_id DESC;

-- Danh sach cac su kien gap loi khi thuc thi de Chu vuon ra soat va kiem tra chi tiet
CREATE VIEW IF NOT EXISTS v_pending_events_errors AS
SELECT
    p.event_id,
    p.log_id,
    p.sender_id,
    p.timestamp,
    p.target_table,
    p.action_type,
    p.audio_path,
    p.raw_transcript,
    p.summary_text,
    p.payload_json,
    p.status,
    p.error_message,
    p.reviewed_by,
    c.full_name AS reviewer_name,
    p.reviewed_at,
    p.review_notes,
    p.created_at,
    p.updated_at
FROM pending_events p
LEFT JOIN collaborators c ON p.reviewed_by = c.collaborator_id
WHERE p.status = 'ERROR'
ORDER BY p.timestamp DESC, p.event_id DESC;

-- Views tuong thich ten goi so it / alias
CREATE VIEW IF NOT EXISTS pending_event AS SELECT * FROM pending_events;
CREATE VIEW IF NOT EXISTS pendind_event AS SELECT * FROM pending_events;

COMMIT;
