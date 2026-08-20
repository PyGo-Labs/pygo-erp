"""PyGo ERP — Migrations for the module system (installable/removable modules)."""
from core.orm.migrations import Migration, migration


@migration("054_create_module_registry")
class CreateModuleRegistry(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS modules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                display_name TEXT,
                version TEXT DEFAULT '1.0.0',
                category TEXT,
                summary TEXT,
                author TEXT,
                depends TEXT DEFAULT '[]',
                state TEXT DEFAULT 'uninstalled',
                is_core INTEGER DEFAULT 0,
                auto_install INTEGER DEFAULT 0,
                path TEXT,
                installed_at TEXT,
                updated_at TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS module_migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_name TEXT NOT NULL,
                migration_name TEXT NOT NULL,
                applied_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS module_hooks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_name TEXT NOT NULL,
                hook_point TEXT NOT NULL,
                handler TEXT NOT NULL,
                priority INTEGER DEFAULT 100,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_mod_mig
                ON module_migrations(module_name, migration_name);
            CREATE INDEX IF NOT EXISTS idx_hooks ON module_hooks(hook_point, is_active, priority);
        """)

    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS module_hooks;
            DROP TABLE IF EXISTS module_migrations;
            DROP TABLE IF EXISTS modules;
        """)
