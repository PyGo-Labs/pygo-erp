"""PyGo ERP — D3 migrations: sales returns, line discounts, credit limits."""
from core.orm.migrations import Migration, migration


@migration("069_create_sales_returns")
class CreateSalesReturns(Migration):
    """Customer returns and credit notes. Purchase returns already existed;
    the sales side did not, so a customer return had nowhere to live."""

    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sales_returns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folio TEXT,
                cliente_id INTEGER NOT NULL,
                sales_order_id INTEGER,
                invoice_id INTEGER,
                warehouse_id INTEGER,
                reason TEXT,
                status TEXT DEFAULT 'draft'
                    CHECK (status IN ('draft', 'received', 'credited', 'cancelled')),
                restock INTEGER DEFAULT 1,
                subtotal REAL DEFAULT 0,
                tax_amount REAL DEFAULT 0,
                total REAL DEFAULT 0,
                currency TEXT DEFAULT 'USD',
                company_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                received_at TEXT,
                credited_at TEXT,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id)
            );

            CREATE TABLE IF NOT EXISTS sales_return_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                return_id INTEGER NOT NULL,
                producto_id INTEGER NOT NULL,
                quantity REAL NOT NULL,
                unit_price REAL DEFAULT 0,
                discount_pct REAL DEFAULT 0,
                line_total REAL DEFAULT 0,
                lot_id INTEGER,
                FOREIGN KEY (return_id) REFERENCES sales_returns(id),
                FOREIGN KEY (producto_id) REFERENCES productos(id)
            );
            CREATE INDEX IF NOT EXISTS idx_sales_return_lines
                ON sales_return_lines(return_id);

            CREATE TABLE IF NOT EXISTS credit_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folio TEXT,
                cliente_id INTEGER NOT NULL,
                return_id INTEGER,
                invoice_id INTEGER,
                amount REAL NOT NULL,
                applied_amount REAL DEFAULT 0,
                status TEXT DEFAULT 'open'
                    CHECK (status IN ('open', 'partially_applied', 'applied', 'cancelled')),
                currency TEXT DEFAULT 'USD',
                reason TEXT,
                company_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id)
            );

            CREATE TABLE IF NOT EXISTS credit_note_applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                credit_note_id INTEGER NOT NULL,
                invoice_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                applied_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (credit_note_id) REFERENCES credit_notes(id)
            );
        """)

    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS credit_note_applications;
            DROP TABLE IF EXISTS credit_notes;
            DROP TABLE IF EXISTS sales_return_lines;
            DROP TABLE IF EXISTS sales_returns;
        """)


@migration("070_line_discounts")
class LineDiscounts(Migration):
    """Percentage discount per line. sales_order_items already had a `discount`
    column that nothing ever wrote to; this adds the missing pieces so a
    discount actually changes the totals."""

    def up(self, conn):
        for table, cols in {
            "sales_order_items": [("discount_pct", "REAL DEFAULT 0"),
                                  ("line_total", "REAL DEFAULT 0")],
            "quote_items": [("discount_pct", "REAL DEFAULT 0"),
                            ("line_total", "REAL DEFAULT 0")],
            "purchase_order_items": [("discount_pct", "REAL DEFAULT 0")],
        }.items():
            existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            if not existing:
                continue
            for name, ddl in cols:
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

        # Document-level totals so a discount is visible on the order itself
        existing = {r[1] for r in conn.execute("PRAGMA table_info(sales_orders)")}
        for name, ddl in (("discount_total", "REAL DEFAULT 0"),
                          ("gross_subtotal", "REAL DEFAULT 0")):
            if name not in existing:
                conn.execute(f"ALTER TABLE sales_orders ADD COLUMN {name} {ddl}")

    def down(self, conn):
        pass


@migration("071_customer_credit")
class CustomerCredit(Migration):
    """Credit limit and payment behaviour per customer."""

    def up(self, conn):
        existing = {r[1] for r in conn.execute("PRAGMA table_info(clientes)")}
        for name, ddl in (
            ("credit_limit", "REAL DEFAULT 0"),
            ("credit_hold", "INTEGER DEFAULT 0"),
            ("payment_term_id", "INTEGER"),
            ("tax_id", "TEXT"),
            ("phone", "TEXT"),
            ("company_id", "INTEGER"),
        ):
            if name not in existing:
                conn.execute(f"ALTER TABLE clientes ADD COLUMN {name} {ddl}")

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS credit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                document_type TEXT,
                document_id INTEGER,
                amount REAL DEFAULT 0,
                exposure_before REAL DEFAULT 0,
                exposure_after REAL DEFAULT 0,
                credit_limit REAL DEFAULT 0,
                blocked INTEGER DEFAULT 0,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id)
            );
            CREATE INDEX IF NOT EXISTS idx_credit_events_customer
                ON credit_events(cliente_id, created_at);
        """)

    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS credit_events")
