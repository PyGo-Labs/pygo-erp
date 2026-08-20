"""PyGo ERP — Migrations for full purchasing (suppliers, RFQ, receipts, returns)."""
from core.orm.migrations import Migration, migration


@migration("036_create_suppliers")
class CreateSuppliers(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                tax_id TEXT,
                email TEXT,
                phone TEXT,
                address TEXT,
                country TEXT,
                currency TEXT DEFAULT 'USD',
                payment_term_id INTEGER,
                lead_time_days INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                company_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS supplier_price_agreements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_id INTEGER NOT NULL,
                producto_id INTEGER NOT NULL,
                price REAL NOT NULL,
                currency TEXT DEFAULT 'USD',
                min_qty REAL DEFAULT 1,
                lead_time_days INTEGER DEFAULT 0,
                valid_from TEXT,
                valid_to TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
            );
            CREATE INDEX IF NOT EXISTS idx_spa ON supplier_price_agreements(producto_id, supplier_id);
        """)

    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS supplier_price_agreements;
            DROP TABLE IF EXISTS suppliers;
        """)


@migration("037_create_rfq")
class CreateRfq(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS rfqs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folio TEXT,
                status TEXT DEFAULT 'draft',
                deadline TEXT,
                notes TEXT,
                company_id INTEGER,
                user_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS rfq_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfq_id INTEGER NOT NULL,
                producto_id INTEGER NOT NULL,
                qty REAL DEFAULT 1,
                uom_id INTEGER,
                FOREIGN KEY (rfq_id) REFERENCES rfqs(id)
            );
            CREATE TABLE IF NOT EXISTS rfq_quotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfq_id INTEGER NOT NULL,
                supplier_id INTEGER NOT NULL,
                total REAL DEFAULT 0,
                currency TEXT DEFAULT 'USD',
                lead_time_days INTEGER DEFAULT 0,
                status TEXT DEFAULT 'received',
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (rfq_id) REFERENCES rfqs(id)
            );
            CREATE TABLE IF NOT EXISTS rfq_quote_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quote_id INTEGER NOT NULL,
                producto_id INTEGER NOT NULL,
                qty REAL DEFAULT 1,
                unit_price REAL DEFAULT 0,
                FOREIGN KEY (quote_id) REFERENCES rfq_quotes(id)
            );
        """)

    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS rfq_quote_lines;
            DROP TABLE IF EXISTS rfq_quotes;
            DROP TABLE IF EXISTS rfq_lines;
            DROP TABLE IF EXISTS rfqs;
        """)


@migration("038_create_receipts")
class CreateReceipts(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS purchase_receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folio TEXT,
                purchase_order_id INTEGER,
                supplier_id INTEGER,
                warehouse_id INTEGER,
                status TEXT DEFAULT 'draft',
                received_at TEXT,
                notes TEXT,
                company_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS purchase_receipt_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_id INTEGER NOT NULL,
                producto_id INTEGER NOT NULL,
                qty_received REAL DEFAULT 0,
                unit_price REAL DEFAULT 0,
                FOREIGN KEY (receipt_id) REFERENCES purchase_receipts(id)
            );
            CREATE TABLE IF NOT EXISTS purchase_returns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folio TEXT,
                receipt_id INTEGER,
                supplier_id INTEGER,
                warehouse_id INTEGER,
                reason TEXT,
                status TEXT DEFAULT 'draft',
                total REAL DEFAULT 0,
                company_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS purchase_return_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                return_id INTEGER NOT NULL,
                producto_id INTEGER NOT NULL,
                qty REAL DEFAULT 0,
                unit_price REAL DEFAULT 0,
                FOREIGN KEY (return_id) REFERENCES purchase_returns(id)
            );
            CREATE INDEX IF NOT EXISTS idx_receipt_po ON purchase_receipts(purchase_order_id);
        """)

    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS purchase_return_lines;
            DROP TABLE IF EXISTS purchase_returns;
            DROP TABLE IF EXISTS purchase_receipt_lines;
            DROP TABLE IF EXISTS purchase_receipts;
        """)


@migration("039_extend_purchase_orders")
class ExtendPurchaseOrders(Migration):
    def up(self, conn):
        for col, ddl in [
            ("folio", "ALTER TABLE purchase_orders ADD COLUMN folio TEXT"),
            ("supplier_id", "ALTER TABLE purchase_orders ADD COLUMN supplier_id INTEGER"),
            ("payment_term_id", "ALTER TABLE purchase_orders ADD COLUMN payment_term_id INTEGER"),
            ("currency", "ALTER TABLE purchase_orders ADD COLUMN currency TEXT DEFAULT 'USD'"),
            ("warehouse_id", "ALTER TABLE purchase_orders ADD COLUMN warehouse_id INTEGER"),
            ("expected_date", "ALTER TABLE purchase_orders ADD COLUMN expected_date TEXT"),
            ("rfq_id", "ALTER TABLE purchase_orders ADD COLUMN rfq_id INTEGER"),
        ]:
            try:
                conn.execute(f"SELECT {col} FROM purchase_orders LIMIT 1")
            except Exception:
                conn.execute(ddl)
        for col, ddl in [
            ("qty_received", "ALTER TABLE purchase_order_items ADD COLUMN qty_received REAL DEFAULT 0"),
            ("uom_id", "ALTER TABLE purchase_order_items ADD COLUMN uom_id INTEGER"),
        ]:
            try:
                conn.execute(f"SELECT {col} FROM purchase_order_items LIMIT 1")
            except Exception:
                conn.execute(ddl)

    def down(self, conn):
        pass
