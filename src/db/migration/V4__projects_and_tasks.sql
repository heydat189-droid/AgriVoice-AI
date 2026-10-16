-- =====================================================
-- AgriVoice-AI: Migration V4 - Projects & Tasks
-- Projects, Tasks, Subtasks, Tags, Comments & Audit Logs
-- =====================================================

PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-- =====================================================
-- 1. PROJECTS (Ke hoach & Du an nong nghiep)
-- =====================================================

CREATE TABLE IF NOT EXISTS projects (
    project_id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE,
    name TEXT NOT NULL,
    description TEXT,

    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN (
            'PLANNED', 'ACTIVE', 'ON_HOLD',
            'COMPLETED', 'CANCELLED', 'ARCHIVED'
        )),

    start_date TEXT,
    due_date TEXT,
    expected_end_date TEXT,
    actual_end_date TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (length(trim(name)) > 0),
    CHECK (start_date IS NULL OR date(start_date) IS NOT NULL),
    CHECK (due_date IS NULL OR date(due_date) IS NOT NULL),
    CHECK (expected_end_date IS NULL OR date(expected_end_date) IS NOT NULL),
    CHECK (actual_end_date IS NULL OR date(actual_end_date) IS NOT NULL),
    CHECK (
        start_date IS NULL
        OR due_date IS NULL
        OR date(due_date) >= date(start_date)
    ),
    CHECK (
        start_date IS NULL
        OR expected_end_date IS NULL
        OR date(expected_end_date) >= date(start_date)
    ),
    CHECK (
        start_date IS NULL
        OR actual_end_date IS NULL
        OR date(actual_end_date) >= date(start_date)
    )
);

-- =====================================================
-- 2. TASKS (Cong viec tren nong trai)
-- =====================================================

CREATE TABLE IF NOT EXISTS tasks (
    task_id INTEGER PRIMARY KEY AUTOINCREMENT,

    project_id INTEGER
        REFERENCES projects(project_id) ON DELETE CASCADE,

    parent_task_id INTEGER
        REFERENCES tasks(task_id) ON DELETE CASCADE,

    assigned_to INTEGER
        REFERENCES collaborators(collaborator_id) ON DELETE SET NULL,

    code TEXT,
    title TEXT NOT NULL,
    name TEXT,
    description TEXT,

    status TEXT NOT NULL DEFAULT 'TODO'
        CHECK (status IN (
            'TODO',
            'IN_PROGRESS',
            'IN_REVIEW',
            'BLOCKED',
            'DONE',
            'CANCELLED'
        )),

    priority TEXT NOT NULL DEFAULT 'MEDIUM'
        CHECK (priority IN (
            'LOW', 'MEDIUM', 'HIGH', 'URGENT'
        )),

    time_delta TEXT DEFAULT '1 day',
    delay TEXT DEFAULT '0 days',
    last TEXT DEFAULT '90 days',
    min_repeats_ratio REAL DEFAULT 0.8
        CHECK (min_repeats_ratio IS NULL OR min_repeats_ratio BETWEEN 0.0 AND 1.0),
    max_repeats_ratio REAL DEFAULT 1.2
        CHECK (max_repeats_ratio IS NULL OR max_repeats_ratio >= 1.0),

    start_date TEXT,
    due_date TEXT,
    completed_at TEXT,

    estimated_minutes INTEGER
        CHECK (
            estimated_minutes IS NULL
            OR estimated_minutes >= 0
        ),
    actual_minutes INTEGER
        CHECK (
            actual_minutes IS NULL
            OR actual_minutes >= 0
        ),

    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1)),

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        parent_task_id IS NULL
        OR parent_task_id <> task_id
    ),
    CHECK (start_date IS NULL OR date(start_date) IS NOT NULL),
    CHECK (due_date IS NULL OR date(due_date) IS NOT NULL),
    CHECK (
        completed_at IS NULL
        OR datetime(completed_at) IS NOT NULL
    ),
    CHECK (
        start_date IS NULL
        OR due_date IS NULL
        OR datetime(due_date) >= datetime(start_date)
    )
);

-- =====================================================
-- 3. SUBTASKS (Dau viec con)
-- =====================================================

CREATE TABLE IF NOT EXISTS subtasks (
    subtask_id INTEGER PRIMARY KEY AUTOINCREMENT,

    task_id INTEGER NOT NULL
        REFERENCES tasks(task_id) ON DELETE CASCADE,

    project_id INTEGER
        REFERENCES projects(project_id) ON DELETE CASCADE,

    title TEXT NOT NULL,
    name TEXT,
    description TEXT,

    open_at TEXT DEFAULT '05:00:00',
    close_at TEXT DEFAULT '18:00:00',
    duration_minutes INTEGER DEFAULT 30
        CHECK (duration_minutes IS NULL OR duration_minutes > 0),

    target_ids TEXT DEFAULT '[]',
    lock INTEGER NOT NULL DEFAULT 0
        CHECK (lock IN (0, 1)),
    glock INTEGER NOT NULL DEFAULT 0
        CHECK (glock IN (0, 1)),

    is_completed INTEGER NOT NULL DEFAULT 0
        CHECK (is_completed IN (0, 1)),
    is_active INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1)),

    sort_order INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (length(trim(title)) > 0),
    CHECK (
        completed_at IS NULL
        OR datetime(completed_at) IS NOT NULL
    )
);

-- =====================================================
-- 4. TAGS (Nhan phan loai)
-- =====================================================

CREATE TABLE IF NOT EXISTS tags (
    tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT,

    CHECK (length(trim(name)) > 0)
);

-- =====================================================
-- 5. TASK_TAGS (Lien ket Task - Tag)
-- =====================================================

CREATE TABLE IF NOT EXISTS task_tags (
    task_id INTEGER NOT NULL
        REFERENCES tasks(task_id) ON DELETE CASCADE,

    tag_id INTEGER NOT NULL
        REFERENCES tags(tag_id) ON DELETE CASCADE,

    PRIMARY KEY (task_id, tag_id)
);

-- =====================================================
-- 6. TASK_COMMENTS (Binh luan / Trao doi tren cong viec)
-- =====================================================

CREATE TABLE IF NOT EXISTS task_comments (
    comment_id INTEGER PRIMARY KEY AUTOINCREMENT,

    task_id INTEGER NOT NULL
        REFERENCES tasks(task_id) ON DELETE CASCADE,

    author_id INTEGER
        REFERENCES collaborators(collaborator_id) ON DELETE SET NULL,

    content TEXT NOT NULL,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (length(trim(content)) > 0)
);

-- =====================================================
-- 7. TASK_ACTIVITIES (Lich su thao tac cong viec)
-- =====================================================

CREATE TABLE IF NOT EXISTS task_activities (
    activity_id INTEGER PRIMARY KEY AUTOINCREMENT,

    task_id INTEGER NOT NULL
        REFERENCES tasks(task_id) ON DELETE CASCADE,

    performed_by INTEGER
        REFERENCES collaborators(collaborator_id) ON DELETE SET NULL,

    action TEXT NOT NULL,
    field_name TEXT,
    old_value TEXT,
    new_value TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (length(trim(action)) > 0)
);

-- =====================================================
-- 8. INDEXES
-- =====================================================

CREATE INDEX IF NOT EXISTS idx_projects_status
    ON projects(status);

CREATE INDEX IF NOT EXISTS idx_tasks_project
    ON tasks(project_id);

CREATE INDEX IF NOT EXISTS idx_tasks_assigned_to
    ON tasks(assigned_to);

CREATE INDEX IF NOT EXISTS idx_tasks_status
    ON tasks(status);

CREATE INDEX IF NOT EXISTS idx_tasks_priority
    ON tasks(priority);

CREATE INDEX IF NOT EXISTS idx_tasks_due_date
    ON tasks(due_date);

CREATE INDEX IF NOT EXISTS idx_tasks_parent
    ON tasks(parent_task_id);

CREATE INDEX IF NOT EXISTS idx_subtasks_task
    ON subtasks(task_id, sort_order);

CREATE INDEX IF NOT EXISTS idx_comments_task
    ON task_comments(task_id, created_at);

CREATE INDEX IF NOT EXISTS idx_activities_task
    ON task_activities(task_id, created_at);

-- =====================================================
-- 9. TRIGGERS
-- =====================================================

CREATE TRIGGER IF NOT EXISTS trg_projects_updated_at
AFTER UPDATE ON projects
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE projects
    SET updated_at = CURRENT_TIMESTAMP
    WHERE project_id = NEW.project_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_tasks_updated_at
AFTER UPDATE ON tasks
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE tasks
    SET updated_at = CURRENT_TIMESTAMP
    WHERE task_id = NEW.task_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_subtasks_updated_at
AFTER UPDATE ON subtasks
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE subtasks
    SET updated_at = CURRENT_TIMESTAMP
    WHERE subtask_id = NEW.subtask_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_subtasks_completed
AFTER UPDATE OF is_completed ON subtasks
FOR EACH ROW
WHEN NEW.is_completed <> OLD.is_completed
BEGIN
    UPDATE subtasks
    SET completed_at = CASE
        WHEN NEW.is_completed = 1
            THEN CURRENT_TIMESTAMP
        ELSE NULL
    END
    WHERE subtask_id = NEW.subtask_id;
END;

COMMIT;
