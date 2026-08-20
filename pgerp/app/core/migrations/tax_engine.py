"""PyGo ERP — Migrations for the generic tax engine."""
from core.orm.migrations import Migration, migration


@migration("055_create_tax_engine")
class CreateTaxEngine(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tax_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                code TEXT,
                country TEXT,
                description TEXT,
                is_default INTEGER DEFAULT 0,
                company_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS taxes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                code TEXT,
                country TEXT,
                tax_group_id INTEGER,
                computation TEXT DEFAULT 'percent',
                amount REAL DEFAULT 0,
                price_include INTEGER DEFAULT 0,
                is_withholding INTEGER DEFAULT 0,
                sequence INTEGER DEFAULT 10,
                include_base_amount INTEGER DEFAULT 0,
                scope TEXT DEFAULT 'sale',
                account_id INTEGER,
                is_active INTEGER DEFAULT 1,
                module_name TEXT,
                company_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS tax_group_taxes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tax_group_id INTEGER NOT NULL,
                tax_id INTEGER NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_taxes_scope ON taxes(scope, is_active, sequence);
            CREATE INDEX IF NOT EXISTS idx_tgt ON tax_group_taxes(tax_group_id);
        """)

    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS tax_group_taxes;
            DROP TABLE IF EXISTS taxes;
            DROP TABLE IF EXISTS tax_groups;
        """)
