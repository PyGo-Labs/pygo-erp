"""PyGo ERP — Migrations for MRP (BOM, work centers, routings, production orders)."""
from core.orm.migrations import Migration, migration


@migration("051_create_bom")
class CreateBom(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS boms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                producto_id INTEGER NOT NULL,
                quantity REAL DEFAULT 1,
                uom_id INTEGER,
                bom_type TEXT DEFAULT 'manufacture',
                routing_id INTEGER,
                is_active INTEGER DEFAULT 1,
                version TEXT DEFAULT '1.0',
                company_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS bom_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bom_id INTEGER NOT NULL,
                component_id INTEGER NOT NULL,
                quantity REAL DEFAULT 1,
                uom_id INTEGER,
                scrap_pct REAL DEFAULT 0,
                child_bom_id INTEGER,
                FOREIGN KEY (bom_id) REFERENCES boms(id)
            );
            CREATE INDEX IF NOT EXISTS idx_bom_prod ON boms(producto_id, is_active);
            CREATE INDEX IF NOT EXISTS idx_bom_lines ON bom_lines(bom_id);
        """)

    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS bom_lines;
            DROP TABLE IF EXISTS boms;
        """)


@migration("052_create_work_centers")
class CreateWorkCenters(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS work_centers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                name TEXT NOT NULL,
                capacity_per_hour REAL DEFAULT 1,
                cost_per_hour REAL DEFAULT 0,
                efficiency_pct REAL DEFAULT 100,
                cost_center_id INTEGER,
                is_active INTEGER DEFAULT 1,
                company_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS routings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                name TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS routing_operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                routing_id INTEGER NOT NULL,
                sequence INTEGER DEFAULT 10,
                name TEXT NOT NULL,
                work_center_id INTEGER,
                setup_minutes REAL DEFAULT 0,
                minutes_per_unit REAL DEFAULT 0,
                FOREIGN KEY (routing_id) REFERENCES routings(id)
            );
            CREATE INDEX IF NOT EXISTS idx_routing_ops ON routing_operations(routing_id, sequence);
        """)

    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS routing_operations;
            DROP TABLE IF EXISTS routings;
            DROP TABLE IF EXISTS work_centers;
        """)


@migration("053_create_production_orders")
class CreateProductionOrders(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS production_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folio TEXT,
                producto_id INTEGER NOT NULL,
                bom_id INTEGER,
                quantity REAL DEFAULT 1,
                quantity_produced REAL DEFAULT 0,
                warehouse_id INTEGER,
                status TEXT DEFAULT 'draft',
                planned_start TEXT,
                planned_end TEXT,
                actual_start TEXT,
                actual_end TEXT,
                material_cost REAL DEFAULT 0,
                labor_cost REAL DEFAULT 0,
                total_cost REAL DEFAULT 0,
                cost_center_id INTEGER,
                company_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS production_order_materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                component_id INTEGER NOT NULL,
                qty_required REAL DEFAULT 0,
                qty_consumed REAL DEFAULT 0,
                unit_cost REAL DEFAULT 0,
                FOREIGN KEY (order_id) REFERENCES production_orders(id)
            );
            CREATE TABLE IF NOT EXISTS production_order_operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                sequence INTEGER DEFAULT 10,
                name TEXT,
                work_center_id INTEGER,
                planned_minutes REAL DEFAULT 0,
                actual_minutes REAL DEFAULT 0,
                status TEXT DEFAULT 'pending',
                FOREIGN KEY (order_id) REFERENCES production_orders(id)
            );
            CREATE INDEX IF NOT EXISTS idx_prod_status ON production_orders(status);
        """)

    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS production_order_operations;
            DROP TABLE IF EXISTS production_order_materials;
            DROP TABLE IF EXISTS production_orders;
        """)
