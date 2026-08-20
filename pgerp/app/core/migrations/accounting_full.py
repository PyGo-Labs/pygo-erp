"""PyGo ERP — Migrations for full accounting (cost centers, budgets, fixed assets, banking, AR/AP)."""
from core.orm.migrations import Migration, migration


@migration("041_create_cost_centers")
class CreateCostCenters(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS cost_centers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                parent_id INTEGER,
                is_active INTEGER DEFAULT 1,
                company_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS analytic_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cost_center_id INTEGER NOT NULL,
                account_id INTEGER,
                journal_entry_id INTEGER,
                amount REAL DEFAULT 0,
                entry_date TEXT,
                description TEXT,
                company_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_analytic_cc ON analytic_lines(cost_center_id, entry_date);
        """)

    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS analytic_lines;
            DROP TABLE IF EXISTS cost_centers;
        """)


@migration("042_create_budgets")
class CreateBudgets(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                fiscal_year TEXT,
                date_from TEXT,
                date_to TEXT,
                status TEXT DEFAULT 'draft',
                company_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS budget_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                budget_id INTEGER NOT NULL,
                account_id INTEGER,
                cost_center_id INTEGER,
                planned_amount REAL DEFAULT 0,
                FOREIGN KEY (budget_id) REFERENCES budgets(id)
            );
            CREATE INDEX IF NOT EXISTS idx_budget_lines ON budget_lines(budget_id);
        """)

    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS budget_lines;
            DROP TABLE IF EXISTS budgets;
        """)


@migration("043_create_fixed_assets")
class CreateFixedAssets(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS fixed_assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                name TEXT NOT NULL,
                category TEXT,
                acquisition_date TEXT,
                acquisition_cost REAL DEFAULT 0,
                salvage_value REAL DEFAULT 0,
                useful_life_months INTEGER DEFAULT 60,
                method TEXT DEFAULT 'straight_line',
                accumulated_depreciation REAL DEFAULT 0,
                status TEXT DEFAULT 'active',
                disposal_date TEXT,
                disposal_amount REAL,
                cost_center_id INTEGER,
                asset_account_id INTEGER,
                depreciation_account_id INTEGER,
                company_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS depreciation_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER NOT NULL,
                period TEXT,
                amount REAL DEFAULT 0,
                accumulated REAL DEFAULT 0,
                book_value REAL DEFAULT 0,
                posted INTEGER DEFAULT 0,
                journal_entry_id INTEGER,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (asset_id) REFERENCES fixed_assets(id)
            );
            CREATE INDEX IF NOT EXISTS idx_dep_asset ON depreciation_entries(asset_id, period);
        """)

    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS depreciation_entries;
            DROP TABLE IF EXISTS fixed_assets;
        """)


@migration("044_create_bank_reconciliation")
class CreateBankReconciliation(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS bank_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                bank_name TEXT,
                account_number TEXT,
                iban TEXT,
                currency TEXT DEFAULT 'USD',
                account_id INTEGER,
                opening_balance REAL DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                company_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS bank_statements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bank_account_id INTEGER NOT NULL,
                reference TEXT,
                date_from TEXT,
                date_to TEXT,
                opening_balance REAL DEFAULT 0,
                closing_balance REAL DEFAULT 0,
                status TEXT DEFAULT 'open',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS bank_statement_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                statement_id INTEGER,
                bank_account_id INTEGER NOT NULL,
                line_date TEXT,
                description TEXT,
                reference TEXT,
                amount REAL DEFAULT 0,
                matched INTEGER DEFAULT 0,
                matched_payment_id INTEGER,
                matched_type TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_bsl ON bank_statement_lines(bank_account_id, matched);
        """)

    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS bank_statement_lines;
            DROP TABLE IF EXISTS bank_statements;
            DROP TABLE IF EXISTS bank_accounts;
        """)


@migration("045_create_ar_ap")
class CreateArAp(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folio TEXT,
                payment_type TEXT DEFAULT 'inbound',
                partner_type TEXT DEFAULT 'customer',
                partner_id INTEGER,
                amount REAL DEFAULT 0,
                currency TEXT DEFAULT 'USD',
                payment_date TEXT,
                method TEXT DEFAULT 'transfer',
                bank_account_id INTEGER,
                reference TEXT,
                status TEXT DEFAULT 'posted',
                company_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS payment_allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payment_id INTEGER NOT NULL,
                document_type TEXT NOT NULL,
                document_id INTEGER NOT NULL,
                amount REAL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (payment_id) REFERENCES payments(id)
            );
            CREATE INDEX IF NOT EXISTS idx_pay_alloc ON payment_allocations(document_type, document_id);
            CREATE INDEX IF NOT EXISTS idx_payments_partner ON payments(partner_type, partner_id);
        """)

    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS payment_allocations;
            DROP TABLE IF EXISTS payments;
        """)


@migration("046_extend_facturas_ar")
class ExtendFacturasAr(Migration):
    def up(self, conn):
        for col, ddl in [
            ("folio", "ALTER TABLE facturas ADD COLUMN folio TEXT"),
            ("due_date", "ALTER TABLE facturas ADD COLUMN due_date TEXT"),
            ("payment_term_id", "ALTER TABLE facturas ADD COLUMN payment_term_id INTEGER"),
            ("amount_paid", "ALTER TABLE facturas ADD COLUMN amount_paid REAL DEFAULT 0"),
            ("payment_status", "ALTER TABLE facturas ADD COLUMN payment_status TEXT DEFAULT 'unpaid'"),
            ("currency", "ALTER TABLE facturas ADD COLUMN currency TEXT DEFAULT 'USD'"),
        ]:
            try:
                conn.execute(f"SELECT {col} FROM facturas LIMIT 1")
            except Exception:
                conn.execute(ddl)

    def down(self, conn):
        pass
