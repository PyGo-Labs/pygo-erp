"""PyGo ERP — Migrations for commercial base (UoM, pricelists, terms, sequences)."""
from core.orm.migrations import Migration, migration


@migration("030_create_uom_categories")
class CreateUomCategories(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS uom_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)

    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS uom_categories")


@migration("031_create_uom")
class CreateUom(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS uom (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                code TEXT UNIQUE NOT NULL,
                category_id INTEGER,
                ratio REAL DEFAULT 1.0,
                uom_type TEXT DEFAULT 'reference',
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (category_id) REFERENCES uom_categories(id)
            );
            CREATE INDEX IF NOT EXISTS idx_uom_category ON uom(category_id);
        """)

    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS uom")


@migration("032_create_pricelists")
class CreatePricelists(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS pricelists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                currency TEXT DEFAULT 'USD',
                is_default INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                company_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS pricelist_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pricelist_id INTEGER NOT NULL,
                producto_id INTEGER NOT NULL,
                price REAL,
                min_qty REAL DEFAULT 1,
                discount_pct REAL DEFAULT 0,
                valid_from TEXT,
                valid_to TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (pricelist_id) REFERENCES pricelists(id)
            );
            CREATE TABLE IF NOT EXISTS cliente_pricelist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER NOT NULL,
                pricelist_id INTEGER NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_pl_items ON pricelist_items(pricelist_id, producto_id);
        """)

    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS cliente_pricelist;
            DROP TABLE IF EXISTS pricelist_items;
            DROP TABLE IF EXISTS pricelists;
        """)


@migration("033_create_payment_terms")
class CreatePaymentTerms(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS payment_terms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                early_discount_pct REAL DEFAULT 0,
                early_discount_days INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS payment_term_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                term_id INTEGER NOT NULL,
                days INTEGER DEFAULT 0,
                percent REAL DEFAULT 100,
                FOREIGN KEY (term_id) REFERENCES payment_terms(id)
            );
        """)

    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS payment_term_lines;
            DROP TABLE IF EXISTS payment_terms;
        """)


@migration("034_create_sequences")
class CreateSequences(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sequences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_type TEXT NOT NULL,
                prefix TEXT DEFAULT '',
                suffix TEXT DEFAULT '',
                padding INTEGER DEFAULT 6,
                next_number INTEGER DEFAULT 1,
                reset_period TEXT DEFAULT 'never',
                current_period TEXT DEFAULT '',
                company_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_seq_doc ON sequences(doc_type, company_id);
        """)

    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS sequences")


@migration("035_add_uom_to_productos")
class AddUomToProductos(Migration):
    def up(self, conn):
        for col, ddl in [
            ("uom_id", "ALTER TABLE productos ADD COLUMN uom_id INTEGER"),
            ("purchase_uom_id", "ALTER TABLE productos ADD COLUMN purchase_uom_id INTEGER"),
            ("cost", "ALTER TABLE productos ADD COLUMN cost REAL DEFAULT 0"),
            ("product_type", "ALTER TABLE productos ADD COLUMN product_type TEXT DEFAULT 'goods'"),
            ("barcode", "ALTER TABLE productos ADD COLUMN barcode TEXT"),
            ("is_active", "ALTER TABLE productos ADD COLUMN is_active INTEGER DEFAULT 1"),
        ]:
            try:
                conn.execute(f"SELECT {col} FROM productos LIMIT 1")
            except Exception:
                conn.execute(ddl)

    def down(self, conn):
        pass
