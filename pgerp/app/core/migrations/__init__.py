"""PyGo ERP V2.0 — Database migrations.

All table creation is tracked via migrations for version control.
"""
from core.orm.migrations import Migration, migration


@migration("001_create_companies")
class CreateCompanies(Migration):
    def up(self, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    
    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS companies")
        conn.commit()


@migration("002_create_users")
class CreateUsers(Migration):
    def up(self, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT,
                salt TEXT,
                full_name TEXT,
                role TEXT DEFAULT 'user',
                company_id INTEGER,
                is_active INTEGER DEFAULT 1,
                last_login TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    
    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS users")
        conn.commit()


@migration("003_create_sessions")
class CreateSessions(Migration):
    def up(self, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT UNIQUE NOT NULL,
                expires_at TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    
    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS sessions")
        conn.commit()


@migration("004_create_productos")
class CreateProductos(Migration):
    def up(self, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS productos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT,
                nombre TEXT,
                precio_unitario REAL,
                stock_minimo REAL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    
    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS productos")
        conn.commit()


@migration("005_create_clientes")
class CreateClientes(Migration):
    def up(self, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT,
                email TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    
    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS clientes")
        conn.commit()


@migration("006_create_facturas")
class CreateFacturas(Migration):
    def up(self, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS facturas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT DEFAULT (datetime('now')),
                total REAL DEFAULT 0.0,
                cliente_id INTEGER,
                sales_order_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    
    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS facturas")
        conn.commit()


@migration("007_create_warehouses")
class CreateWarehouses(Migration):
    def up(self, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS warehouses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                code TEXT UNIQUE,
                location TEXT,
                company_id INTEGER,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    
    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS warehouses")
        conn.commit()


@migration("008_create_stock")
class CreateStock(Migration):
    def up(self, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                producto_id INTEGER NOT NULL,
                warehouse_id INTEGER NOT NULL,
                quantity REAL DEFAULT 0,
                UNIQUE(producto_id, warehouse_id)
            )
        """)
        conn.commit()
    
    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS stock")
        conn.commit()


@migration("009_create_stock_movements")
class CreateStockMovements(Migration):
    def up(self, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                producto_id INTEGER NOT NULL,
                from_warehouse_id INTEGER,
                to_warehouse_id INTEGER,
                quantity REAL NOT NULL,
                type TEXT CHECK(type IN ('transfer', 'adjustment', 'sale', 'purchase')),
                reason TEXT,
                user_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    
    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS stock_movements")
        conn.commit()


@migration("010_create_categorias")
class CreateCategorias(Migration):
    def up(self, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS categorias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                parent_id INTEGER
            )
        """)
        conn.commit()
    
    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS categorias")
        conn.commit()


@migration("011_create_sales_orders")
class CreateSalesOrders(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sales_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER NOT NULL,
                status TEXT DEFAULT 'draft' CHECK(status IN ('draft', 'confirmed', 'delivered', 'invoiced', 'cancelled')),
                subtotal REAL DEFAULT 0,
                tax REAL DEFAULT 0,
                total REAL DEFAULT 0,
                notes TEXT,
                user_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS sales_order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                producto_id INTEGER NOT NULL,
                quantity REAL DEFAULT 1,
                precio_unitario REAL DEFAULT 0,
                discount REAL DEFAULT 0
            );
        """)
        conn.commit()
    
    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS sales_orders;
            DROP TABLE IF EXISTS sales_order_items;
        """)
        conn.commit()


@migration("012_create_purchase_orders")
class CreatePurchaseOrders(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS purchase_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_name TEXT,
                status TEXT DEFAULT 'draft' CHECK(status IN ('draft', 'received', 'cancelled')),
                subtotal REAL DEFAULT 0,
                tax REAL DEFAULT 0,
                total REAL DEFAULT 0,
                notes TEXT,
                user_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS purchase_order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                producto_id INTEGER NOT NULL,
                quantity REAL DEFAULT 1,
                precio_unitario REAL DEFAULT 0
            );
        """)
        conn.commit()
    
    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS purchase_orders;
            DROP TABLE IF EXISTS purchase_order_items;
        """)
        conn.commit()


@migration("013_create_quotes")
class CreateQuotes(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS quotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER NOT NULL,
                status TEXT DEFAULT 'draft',
                subtotal REAL DEFAULT 0,
                tax REAL DEFAULT 0,
                total REAL DEFAULT 0,
                valid_until TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS quote_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quote_id INTEGER NOT NULL,
                producto_id INTEGER NOT NULL,
                quantity REAL DEFAULT 1,
                precio_unitario REAL DEFAULT 0
            );
        """)
        conn.commit()
    
    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS quotes;
            DROP TABLE IF EXISTS quote_items;
        """)
        conn.commit()


@migration("014_create_accounts_journal")
class CreateAccountsJournal(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                type TEXT CHECK(type IN ('asset', 'liability', 'equity', 'revenue', 'expense')),
                parent_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS journal_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                description TEXT,
                debit_total REAL DEFAULT 0,
                credit_total REAL DEFAULT 0,
                user_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS journal_entry_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                debit REAL DEFAULT 0,
                credit REAL DEFAULT 0,
                description TEXT
            );
        """)
        conn.commit()
    
    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS accounts;
            DROP TABLE IF EXISTS journal_entries;
            DROP TABLE IF EXISTS journal_entry_lines;
        """)
        conn.commit()


@migration("015_create_leads_opportunities")
class CreateLeadsOpportunities(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                company TEXT,
                source TEXT,
                notes TEXT,
                status TEXT DEFAULT 'new' CHECK(status IN ('new', 'contacted', 'qualified', 'converted', 'lost')),
                user_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS opportunities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                company TEXT,
                contact_name TEXT,
                contact_email TEXT,
                contact_phone TEXT,
                value REAL DEFAULT 0,
                stage TEXT DEFAULT 'prospecting' CHECK(stage IN ('prospecting', 'qualification', 'proposal', 'negotiation', 'qualified', 'won', 'lost')),
                probability INTEGER DEFAULT 50,
                source TEXT,
                expected_close_date TEXT,
                user_id INTEGER,
                lead_id INTEGER,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT CHECK(type IN ('call', 'email', 'meeting', 'note', 'task')),
                subject TEXT NOT NULL,
                description TEXT,
                related_type TEXT,
                related_id INTEGER,
                user_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
    
    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS leads;
            DROP TABLE IF EXISTS opportunities;
            DROP TABLE IF EXISTS activities;
        """)
        conn.commit()


@migration("016_create_projects")
class CreateProjects(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'planning' CHECK(status IN ('planning', 'in_progress', 'completed', 'cancelled')),
                start_date TEXT,
                end_date TEXT,
                user_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                assigned_to INTEGER,
                priority TEXT DEFAULT 'medium' CHECK(priority IN ('low', 'medium', 'high', 'urgent')),
                status TEXT DEFAULT 'todo' CHECK(status IN ('todo', 'in_progress', 'done', 'cancelled')),
                due_date TEXT,
                completed_at TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS timesheets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                user_id INTEGER,
                hours REAL NOT NULL,
                description TEXT,
                date TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS milestones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                due_date TEXT,
                completed INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
    
    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS projects;
            DROP TABLE IF EXISTS tasks;
            DROP TABLE IF EXISTS timesheets;
            DROP TABLE IF EXISTS milestones;
        """)
        conn.commit()


@migration("017_create_files")
class CreateFiles(Migration):
    def up(self, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                original_name TEXT,
                mime_type TEXT,
                size INTEGER DEFAULT 0,
                path TEXT NOT NULL,
                related_type TEXT,
                related_id INTEGER,
                user_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    
    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS files")
        conn.commit()


@migration("018_seed_chart_of_accounts")
class SeedChartOfAccounts(Migration):
    def up(self, conn):
        if conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] > 0:
            return
        
        accounts = [
            ("1000", "Activo", "asset", None),
            ("1100", "Activo Circulante", "asset", 1),
            ("1101", "Caja", "asset", 2),
            ("1102", "Bancos", "asset", 2),
            ("1103", "Cuentas por Cobrar", "asset", 2),
            ("1104", "Inventario", "asset", 2),
            ("1200", "Activo Fijo", "asset", 1),
            ("2000", "Pasivo", "liability", None),
            ("2100", "Pasivo Circulante", "liability", 9),
            ("2101", "Cuentas por Pagar", "liability", 10),
            ("2102", "IVA por Pagar", "liability", 10),
            ("3000", "Capital", "equity", None),
            ("3100", "Capital Social", "equity", 13),
            ("3200", "Utilidades Retenidas", "equity", 13),
            ("4000", "Ingresos", "revenue", None),
            ("4100", "Ventas", "revenue", 16),
            ("5000", "Gastos", "expense", None),
            ("5100", "Costo de Ventas", "expense", 18),
            ("5200", "Gastos Operativos", "expense", 18),
        ]
        
        ids = {}
        for i, (code, name, type_, parent_idx) in enumerate(accounts):
            cursor = conn.execute(
                "INSERT INTO accounts (code, name, type) VALUES (?, ?, ?)",
                (code, name, type_)
            )
            ids[i + 1] = cursor.lastrowid
        
        for i, (code, name, type_, parent_idx) in enumerate(accounts):
            if parent_idx and parent_idx in ids:
                conn.execute("UPDATE accounts SET parent_id = ? WHERE id = ?",
                           (ids[parent_idx], ids[i + 1]))
        conn.commit()
    
    def down(self, conn):
        conn.execute("DELETE FROM accounts")
        conn.commit()
