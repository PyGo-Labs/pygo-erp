"""PyGo ERP — D2 migrations: lots/serials, reservations, reorder rules."""
from core.orm.migrations import Migration, migration


@migration("064_create_lots")
class CreateLots(Migration):
    """Lot / serial tracking. A lot groups units sharing an expiry or origin;
    a serial identifies exactly one unit."""

    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS lots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                producto_id INTEGER NOT NULL,
                lot_code TEXT NOT NULL,
                tracking_type TEXT DEFAULT 'lot'
                    CHECK (tracking_type IN ('lot', 'serial')),
                expiry_date TEXT,
                manufactured_date TEXT,
                supplier_id INTEGER,
                notes TEXT,
                company_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (producto_id, lot_code),
                FOREIGN KEY (producto_id) REFERENCES productos(id)
            );

            CREATE TABLE IF NOT EXISTS lot_stock (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lot_id INTEGER NOT NULL,
                warehouse_id INTEGER NOT NULL,
                quantity REAL DEFAULT 0,
                UNIQUE (lot_id, warehouse_id),
                FOREIGN KEY (lot_id) REFERENCES lots(id),
                FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)
            );

            CREATE TABLE IF NOT EXISTS lot_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lot_id INTEGER NOT NULL,
                warehouse_id INTEGER,
                quantity REAL NOT NULL,
                direction TEXT NOT NULL CHECK (direction IN ('in', 'out')),
                reason TEXT,
                source_type TEXT,
                source_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (lot_id) REFERENCES lots(id)
            );
            CREATE INDEX IF NOT EXISTS idx_lot_movements_lot ON lot_movements(lot_id);
        """)

    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS lot_movements;
            DROP TABLE IF EXISTS lot_stock;
            DROP TABLE IF EXISTS lots;
        """)


@migration("065_product_tracking")
class ProductTracking(Migration):
    """Per-product tracking policy: none, lot or serial."""

    def up(self, conn):
        cols = {r[1] for r in conn.execute("PRAGMA table_info(productos)")}
        if "tracking" not in cols:
            conn.execute("ALTER TABLE productos ADD COLUMN tracking TEXT DEFAULT 'none'")
        if "shelf_life_days" not in cols:
            conn.execute("ALTER TABLE productos ADD COLUMN shelf_life_days INTEGER")

    def down(self, conn):
        pass


@migration("066_create_reservations")
class CreateReservations(Migration):
    """Stock reservations so two salespeople cannot sell the same unit."""

    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS stock_reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                producto_id INTEGER NOT NULL,
                warehouse_id INTEGER NOT NULL,
                quantity REAL NOT NULL,
                document_type TEXT NOT NULL,
                document_id INTEGER NOT NULL,
                lot_id INTEGER,
                status TEXT DEFAULT 'active'
                    CHECK (status IN ('active', 'released', 'fulfilled')),
                reserved_at TEXT DEFAULT CURRENT_TIMESTAMP,
                released_at TEXT,
                notes TEXT,
                company_id INTEGER,
                FOREIGN KEY (producto_id) REFERENCES productos(id),
                FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)
            );
            CREATE INDEX IF NOT EXISTS idx_reservations_lookup
                ON stock_reservations(producto_id, warehouse_id, status);
            CREATE INDEX IF NOT EXISTS idx_reservations_doc
                ON stock_reservations(document_type, document_id);
        """)

    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS stock_reservations")


@migration("067_create_backorders")
class CreateBackorders(Migration):
    """What a customer ordered that could not be delivered yet."""

    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS backorders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_type TEXT NOT NULL,
                document_id INTEGER NOT NULL,
                producto_id INTEGER NOT NULL,
                warehouse_id INTEGER,
                quantity_ordered REAL NOT NULL,
                quantity_pending REAL NOT NULL,
                status TEXT DEFAULT 'pending'
                    CHECK (status IN ('pending', 'partial', 'fulfilled', 'cancelled')),
                expected_date TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                fulfilled_at TEXT,
                company_id INTEGER,
                FOREIGN KEY (producto_id) REFERENCES productos(id)
            );
            CREATE INDEX IF NOT EXISTS idx_backorders_product
                ON backorders(producto_id, status);
        """)

    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS backorders")


@migration("068_create_reorder_rules")
class CreateReorderRules(Migration):
    """Min/max per product and warehouse, used to suggest purchases."""

    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS reorder_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                producto_id INTEGER NOT NULL,
                warehouse_id INTEGER NOT NULL,
                min_quantity REAL DEFAULT 0,
                max_quantity REAL DEFAULT 0,
                multiple_of REAL DEFAULT 1,
                lead_time_days INTEGER DEFAULT 0,
                preferred_supplier_id INTEGER,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (producto_id, warehouse_id),
                FOREIGN KEY (producto_id) REFERENCES productos(id),
                FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)
            );
        """)

    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS reorder_rules")
