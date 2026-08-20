"""PyGo ERP — D1 migrations: inventory valuation, multicurrency, period locking."""
from core.orm.migrations import Migration, migration


@migration("059_create_stock_layers")
class CreateStockLayers(Migration):
    """Cost layers: every inbound movement creates a layer that outbound
    movements consume. This is what makes COGS a real number."""

    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS stock_layers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                producto_id INTEGER NOT NULL,
                warehouse_id INTEGER NOT NULL,
                quantity REAL NOT NULL,
                remaining REAL NOT NULL,
                unit_cost REAL NOT NULL,
                currency TEXT DEFAULT 'USD',
                source_type TEXT,
                source_id INTEGER,
                layer_date TEXT DEFAULT CURRENT_TIMESTAMP,
                company_id INTEGER,
                FOREIGN KEY (producto_id) REFERENCES productos(id),
                FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)
            );
            CREATE INDEX IF NOT EXISTS idx_layers_lookup
                ON stock_layers(producto_id, warehouse_id, remaining);

            CREATE TABLE IF NOT EXISTS stock_valuation_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                producto_id INTEGER NOT NULL,
                warehouse_id INTEGER,
                movement_type TEXT NOT NULL,
                quantity REAL NOT NULL,
                unit_cost REAL NOT NULL,
                total_value REAL NOT NULL,
                method TEXT DEFAULT 'fifo',
                layer_id INTEGER,
                source_type TEXT,
                source_id INTEGER,
                entry_date TEXT DEFAULT CURRENT_TIMESTAMP,
                company_id INTEGER,
                FOREIGN KEY (producto_id) REFERENCES productos(id)
            );
            CREATE INDEX IF NOT EXISTS idx_valuation_product
                ON stock_valuation_entries(producto_id, entry_date);
        """)

    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS stock_valuation_entries;
            DROP TABLE IF EXISTS stock_layers;
        """)


@migration("060_product_costing_method")
class ProductCostingMethod(Migration):
    """Costing method per product: fifo (default), average or standard."""

    def up(self, conn):
        cols = {r[1] for r in conn.execute("PRAGMA table_info(productos)")}
        if "costing_method" not in cols:
            conn.execute(
                "ALTER TABLE productos ADD COLUMN costing_method TEXT DEFAULT 'fifo'")
        if "average_cost" not in cols:
            conn.execute("ALTER TABLE productos ADD COLUMN average_cost REAL DEFAULT 0")

    def down(self, conn):
        pass  # SQLite cannot drop columns safely here


@migration("061_document_currency")
class DocumentCurrency(Migration):
    """Currency + exchange rate on every monetary document and journal entry."""

    def up(self, conn):
        targets = {
            "sales_orders": ["currency", "exchange_rate"],
            "purchase_orders": ["exchange_rate"],
            "journal_entries": ["currency", "exchange_rate"],
            "payments": ["exchange_rate"],
            "facturas": ["exchange_rate"],
        }
        for table, wanted in targets.items():
            existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            if not existing:
                continue
            for col in wanted:
                if col in existing:
                    continue
                if col == "currency":
                    conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN currency TEXT DEFAULT 'USD'")
                else:
                    conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN exchange_rate REAL DEFAULT 1")

    def down(self, conn):
        pass


@migration("062_fx_difference_entries")
class FxDifferenceEntries(Migration):
    """Realised exchange differences when a payment settles a document
    that was issued at a different rate."""

    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS fx_differences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_type TEXT NOT NULL,
                document_id INTEGER NOT NULL,
                payment_id INTEGER,
                currency TEXT NOT NULL,
                document_rate REAL NOT NULL,
                payment_rate REAL NOT NULL,
                amount_currency REAL NOT NULL,
                difference_base REAL NOT NULL,
                gain_or_loss TEXT NOT NULL,
                entry_date TEXT DEFAULT CURRENT_TIMESTAMP,
                company_id INTEGER
            );
        """)

    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS fx_differences")


@migration("063_fiscal_period_locking")
class FiscalPeriodLocking(Migration):
    """Give fiscal_periods real teeth: explicit date range plus a lock flag."""

    def up(self, conn):
        cols = {r[1] for r in conn.execute("PRAGMA table_info(fiscal_periods)")}
        for col, ddl in (
            ("date_from", "TEXT"),
            ("date_to", "TEXT"),
            ("is_locked", "INTEGER DEFAULT 0"),
            ("locked_by", "INTEGER"),
            ("name", "TEXT"),
        ):
            if col not in cols:
                conn.execute(f"ALTER TABLE fiscal_periods ADD COLUMN {col} {ddl}")

        # Backfill ranges for any period that predates this migration
        for row in conn.execute(
                "SELECT id, year, month FROM fiscal_periods "
                "WHERE date_from IS NULL AND year IS NOT NULL").fetchall():
            year, month = int(row[1]), int(row[2] or 1)
            last_day = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
                        else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
            conn.execute(
                "UPDATE fiscal_periods SET date_from = ?, date_to = ?, name = ? WHERE id = ?",
                (f"{year}-{month:02d}-01", f"{year}-{month:02d}-{last_day:02d}",
                 f"{year}-{month:02d}", row[0]),
            )

    def down(self, conn):
        pass
