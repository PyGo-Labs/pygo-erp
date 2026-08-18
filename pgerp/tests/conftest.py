import pytest
import sys
import os
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


def _setup_db():
    """Create test DB with all tables."""
    db_path = "/tmp/pgerp_test.db"
    os.environ["PYGO_DB"] = db_path
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    from core.auth import User, Company, Session
    User.create_table(conn)
    Company.create_table(conn)
    Session.create_table(conn)
    
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS productos (id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT, nombre TEXT, precio_unitario REAL, stock_minimo REAL);
        CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, email TEXT);
        CREATE TABLE IF NOT EXISTS facturas (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT DEFAULT (datetime('now')), total REAL DEFAULT 0.0, cliente_id INTEGER);
        CREATE TABLE IF NOT EXISTS warehouses (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, code TEXT, location TEXT, company_id INTEGER, is_active INTEGER DEFAULT 1, created_at TEXT DEFAULT (datetime('now')));
        CREATE TABLE IF NOT EXISTS stock (id INTEGER PRIMARY KEY AUTOINCREMENT, producto_id INTEGER NOT NULL, warehouse_id INTEGER NOT NULL, quantity REAL DEFAULT 0, UNIQUE(producto_id, warehouse_id));
        CREATE TABLE IF NOT EXISTS stock_movements (id INTEGER PRIMARY KEY AUTOINCREMENT, producto_id INTEGER NOT NULL, from_warehouse_id INTEGER, to_warehouse_id INTEGER, quantity REAL NOT NULL, type TEXT, reason TEXT, user_id INTEGER, created_at TEXT DEFAULT (datetime('now')));
        CREATE TABLE IF NOT EXISTS categorias (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, parent_id INTEGER);
        CREATE TABLE IF NOT EXISTS sales_orders (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER NOT NULL, status TEXT DEFAULT 'draft', subtotal REAL DEFAULT 0, tax REAL DEFAULT 0, total REAL DEFAULT 0, notes TEXT, user_id INTEGER, created_at TEXT DEFAULT (datetime('now')));
        CREATE TABLE IF NOT EXISTS sales_order_items (id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL, producto_id INTEGER NOT NULL, quantity REAL DEFAULT 1, precio_unitario REAL DEFAULT 0, discount REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS purchase_orders (id INTEGER PRIMARY KEY AUTOINCREMENT, supplier_name TEXT, status TEXT DEFAULT 'draft', subtotal REAL DEFAULT 0, tax REAL DEFAULT 0, total REAL DEFAULT 0, notes TEXT, user_id INTEGER, created_at TEXT DEFAULT (datetime('now')));
        CREATE TABLE IF NOT EXISTS purchase_order_items (id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL, producto_id INTEGER NOT NULL, quantity REAL DEFAULT 1, precio_unitario REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS quotes (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER NOT NULL, status TEXT DEFAULT 'draft', subtotal REAL DEFAULT 0, tax REAL DEFAULT 0, total REAL DEFAULT 0, valid_until TEXT, created_at TEXT DEFAULT (datetime('now')));
        CREATE TABLE IF NOT EXISTS quote_items (id INTEGER PRIMARY KEY AUTOINCREMENT, quote_id INTEGER NOT NULL, producto_id INTEGER NOT NULL, quantity REAL DEFAULT 1, precio_unitario REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, type TEXT CHECK(type IN ('asset','liability','equity','revenue','expense')), parent_id INTEGER, created_at TEXT DEFAULT (datetime('now')));
        CREATE TABLE IF NOT EXISTS journal_entries (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, description TEXT, debit_total REAL DEFAULT 0, credit_total REAL DEFAULT 0, user_id INTEGER, created_at TEXT DEFAULT (datetime('now')));
        CREATE TABLE IF NOT EXISTS journal_entry_lines (id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id INTEGER NOT NULL, account_id INTEGER NOT NULL, debit REAL DEFAULT 0, credit REAL DEFAULT 0, description TEXT);
        CREATE TABLE IF NOT EXISTS leads (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT, phone TEXT, company TEXT, source TEXT, notes TEXT, status TEXT DEFAULT 'new', user_id INTEGER, created_at TEXT DEFAULT (datetime('now')));
        CREATE TABLE IF NOT EXISTS opportunities (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, company TEXT, contact_name TEXT, contact_email TEXT, contact_phone TEXT, value REAL DEFAULT 0, stage TEXT DEFAULT 'prospecting', probability INTEGER DEFAULT 50, source TEXT, expected_close_date TEXT, user_id INTEGER, lead_id INTEGER, notes TEXT, created_at TEXT DEFAULT (datetime('now')));
        CREATE TABLE IF NOT EXISTS activities (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT CHECK(type IN ('call','email','meeting','note','task')), subject TEXT NOT NULL, description TEXT, related_type TEXT, related_id INTEGER, user_id INTEGER, created_at TEXT DEFAULT (datetime('now')));
        CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT, status TEXT DEFAULT 'planning', start_date TEXT, end_date TEXT, user_id INTEGER, created_at TEXT DEFAULT (datetime('now')));
        CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, title TEXT NOT NULL, description TEXT, assigned_to INTEGER, priority TEXT DEFAULT 'medium', status TEXT DEFAULT 'todo', due_date TEXT, completed_at TEXT, created_at TEXT DEFAULT (datetime('now')));
        CREATE TABLE IF NOT EXISTS timesheets (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER NOT NULL, user_id INTEGER, hours REAL NOT NULL, description TEXT, date TEXT, created_at TEXT DEFAULT (datetime('now')));
        CREATE TABLE IF NOT EXISTS milestones (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, name TEXT NOT NULL, description TEXT, due_date TEXT, completed INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now')));
    """)
    conn.commit()
    
    conn.execute("INSERT OR IGNORE INTO companies (id, name, slug) VALUES (1, 'Test Co', 'test')")
    conn.commit()
    
    return conn


@pytest.fixture(autouse=True)
def db_conn():
    """Auto-use fixture: every test gets a fresh DB."""
    conn = _setup_db()
    yield conn
    conn.close()
    try:
        os.unlink("/tmp/pgerp_test.db")
    except:
        pass
