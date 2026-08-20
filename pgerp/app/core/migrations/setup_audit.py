"""PyGo ERP — Migrations for Fase C (setup wizard, audit trail, attachments)."""
from core.orm.migrations import Migration, migration


@migration("056_create_setup_state")
class CreateSetupState(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS setup_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                step TEXT UNIQUE NOT NULL,
                status TEXT DEFAULT 'pending',
                data TEXT DEFAULT '{}',
                completed_at TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS company_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER,
                setting_key TEXT NOT NULL,
                setting_value TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_company_setting
                ON company_settings(company_id, setting_key);
        """)

    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS company_settings;
            DROP TABLE IF EXISTS setup_state;
        """)


@migration("057_create_audit_log")
class CreateAuditLog(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id INTEGER,
                action TEXT NOT NULL,
                user_id INTEGER,
                user_email TEXT,
                changes TEXT DEFAULT '{}',
                old_values TEXT,
                new_values TEXT,
                ip_address TEXT,
                company_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id);
            CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_audit_date ON audit_log(created_at);
        """)

    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS audit_log")


@migration("058_create_attachments")
class CreateAttachments(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                file_id INTEGER,
                filename TEXT,
                mime_type TEXT,
                size_bytes INTEGER DEFAULT 0,
                storage_path TEXT,
                description TEXT,
                uploaded_by INTEGER,
                company_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_attach_entity ON attachments(entity_type, entity_id);
        """)

    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS attachments")
