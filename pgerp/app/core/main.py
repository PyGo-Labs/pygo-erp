"""PyGo ERP V2.0 — Python domain runtime server.

Serves all business logic handlers via UDS + MessagePack.
Go web layer calls handlers like: app.Call("core.services.productos.list", {})

All models, services, and business logic live here.
V2.0: Full CRUD + Auth/Users/Multi-tenancy.
"""
import asyncio
import os
import socket
import sys
import traceback
import sqlite3
from pathlib import Path

import msgpack

# Add framework and app to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "app"))

# Database setup
DB_PATH = os.environ.get("PYGO_DB", "/tmp/pgerp.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Handlers registry (shared)
from core.registry import HANDLERS, register

# --- Auth models (load first for migrations) ---
from core.auth import User, Company, Session, hash_password

# --- Auth handlers ---
from core import auth_handlers

# --- Tenancy ---
from core import tenancy

# --- Inventory ---
from core import inventory

# --- Sales ---
from core import sales

# --- Accounting ---
from core import accounting

# --- CRM ---
from core import crm

# --- Projects ---
from core import projects

# --- Reports ---
from core import reports

# --- Models ---

class BaseModel:
    table = ""
    
    @classmethod
    def all(cls):
        db = get_db()
        rows = db.execute(f"SELECT * FROM {cls.table}").fetchall()
        return [dict(r) for r in rows]
    
    @classmethod
    def find(cls, id):
        db = get_db()
        row = db.execute(f"SELECT * FROM {cls.table} WHERE id = ?", (id,)).fetchone()
        return dict(row) if row else None
    
    @classmethod
    def create(cls, **data):
        db = get_db()
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        db.execute(f"INSERT INTO {cls.table} ({cols}) VALUES ({placeholders})", list(data.values()))
        db.commit()
        return cls.find(db.execute("SELECT last_insert_rowid()").fetchone()[0])
    
    @classmethod
    def update(cls, id, **data):
        db = get_db()
        sets = ", ".join(f"{k} = ?" for k in data)
        vals = list(data.values()) + [id]
        db.execute(f"UPDATE {cls.table} SET {sets} WHERE id = ?", vals)
        db.commit()
        return cls.find(id)
    
    @classmethod
    def delete(cls, id):
        db = get_db()
        db.execute(f"DELETE FROM {cls.table} WHERE id = ?", (id,))
        db.commit()
        return True

class Producto(BaseModel):
    table = "productos"
    
    @classmethod
    def create(cls, **data):
        field_map = {"precio": "precio_unitario", "codigo": "codigo", "nombre": "nombre"}
        type_casts = {"precio_unitario": float, "codigo": str, "nombre": str}
        mapped = {}
        for k, v in data.items():
            col = field_map.get(k, k)
            cast = type_casts.get(col, str)
            try:
                mapped[col] = cast(v)
            except (ValueError, TypeError):
                mapped[col] = v
        return super().create(**mapped)
    
    @classmethod
    def update(cls, id, **data):
        field_map = {"precio": "precio_unitario", "codigo": "codigo", "nombre": "nombre"}
        type_casts = {"precio_unitario": float, "codigo": str, "nombre": str}
        mapped = {}
        for k, v in data.items():
            col = field_map.get(k, k)
            cast = type_casts.get(col, str)
            try:
                mapped[col] = cast(v)
            except (ValueError, TypeError):
                mapped[col] = v
        return super().update(id, **mapped)

class Cliente(BaseModel):
    table = "clientes"

class Factura(BaseModel):
    table = "facturas"

# --- Service handlers ---

@register("core.services.health")
def health():
    """Health check handler."""
    db = get_db()
    counts = {}
    for t in ["productos", "clientes", "facturas", "users", "companies"]:
        try:
            counts[t] = db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except:
            counts[t] = 0
    return {"status": "ok", "models": ["Producto", "Cliente", "Factura", "User"], "counts": counts}

@register("core.services.dashboard")
def dashboard():
    """Dashboard stats."""
    db = get_db()
    productos = db.execute("SELECT COUNT(*) FROM productos").fetchone()[0]
    clientes = db.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
    facturas = db.execute("SELECT COUNT(*) FROM facturas").fetchone()[0]
    total_ventas = db.execute("SELECT COALESCE(SUM(total), 0) FROM facturas").fetchone()[0]
    users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    return {
        "productos": productos,
        "clientes": clientes,
        "facturas": facturas,
        "total_ventas": total_ventas,
        "users": users,
    }

# --- Productos CRUD ---

@register("core.services.productos.list")
def productos_list(**kwargs):
    return Producto.all()

@register("core.services.productos.find")
def productos_find(id=None, **kwargs):
    if not id:
        return {"error": "id is required"}
    return Producto.find(id) or {"error": "not found"}

@register("core.services.productos.create")
def productos_create(**data):
    if not data.get("nombre"):
        return {"error": "nombre is required"}
    if not data.get("precio") and not data.get("precio_unitario"):
        return {"error": "precio is required"}
    return Producto.create(**data)

@register("core.services.productos.update")
def productos_update(id=None, **data):
    if not id:
        return {"error": "id is required"}
    return Producto.update(id, **data)

@register("core.services.productos.delete")
def productos_delete(id=None, **kwargs):
    if not id:
        return {"error": "id is required"}
    Producto.delete(id)
    return {"deleted": True, "id": id}

# --- Clientes CRUD ---

@register("core.services.clientes.list")
def clientes_list(**kwargs):
    return Cliente.all()

@register("core.services.clientes.find")
def clientes_find(id=None, **kwargs):
    if not id:
        return {"error": "id is required"}
    return Cliente.find(id) or {"error": "not found"}

@register("core.services.clientes.create")
def clientes_create(**data):
    if not data.get("nombre"):
        return {"error": "nombre is required"}
    return Cliente.create(**data)

@register("core.services.clientes.update")
def clientes_update(id=None, **data):
    if not id:
        return {"error": "id is required"}
    return Cliente.update(id, **data)

@register("core.services.clientes.delete")
def clientes_delete(id=None, **kwargs):
    if not id:
        return {"error": "id is required"}
    Cliente.delete(id)
    return {"deleted": True, "id": id}

# --- Facturas CRUD ---

@register("core.services.facturas.list")
def facturas_list(**kwargs):
    return Factura.all()

@register("core.services.facturas.find")
def facturas_find(id=None, **kwargs):
    if not id:
        return {"error": "id is required"}
    return Factura.find(id) or {"error": "not found"}

@register("core.services.facturas.create")
def facturas_create(**data):
    if not data.get("cliente_id"):
        return {"error": "cliente_id is required"}
    if data.get("total") is None:
        data["total"] = 0.0
    return Factura.create(**data)

@register("core.services.facturas.update")
def facturas_update(id=None, **data):
    if not id:
        return {"error": "id is required"}
    return Factura.update(id, **data)

@register("core.services.facturas.delete")
def facturas_delete(id=None, **kwargs):
    if not id:
        return {"error": "id is required"}
    Factura.delete(id)
    return {"deleted": True, "id": id}

# --- UDS server ---

def handle_request(payload: bytes) -> bytes:
    try:
        req = msgpack.unpackb(payload, raw=False, strict_map_key=False)
        method = req.get("method", "")
        args = req.get("args", {}) or {}
        fn = HANDLERS.get(method)
        if fn is None:
            return msgpack.packb({"result": None, "error": f"Handler not found: {method}"}, use_bin_type=True)
        result = fn(**args)
        return msgpack.packb({"result": result, "error": None}, use_bin_type=True)
    except Exception as e:
        trace = traceback.format_exc()
        return msgpack.packb({"result": None, "error": f"{e}\n{trace}"}, use_bin_type=True)

async def start_server(socket_path):
    try:
        os.unlink(socket_path)
    except FileNotFoundError:
        pass
    os.makedirs(os.path.dirname(socket_path) or ".", exist_ok=True)

    async def handle_conn(reader, writer):
        try:
            while True:
                header = await reader.readexactly(4)
                length = int.from_bytes(header, byteorder="big")
                if length == 0:
                    continue
                payload = await reader.readexactly(length)
                response = handle_request(payload)
                resp_header = len(response).to_bytes(4, byteorder="big")
                writer.write(resp_header + response)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
            pass
        finally:
            writer.close()

    server = await asyncio.start_unix_server(handle_conn, path=socket_path)
    os.chmod(socket_path, 0o660)
    print(f"PyGo ERP Python domain server ready on {socket_path}", flush=True)

    async with server:
        await server.serve_forever()

def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT,
            nombre TEXT,
            precio_unitario REAL
        );
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            email TEXT
        );
        CREATE TABLE IF NOT EXISTS facturas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT DEFAULT (datetime('now')),
            total REAL DEFAULT 0.0,
            cliente_id INTEGER
        );
    """)
    db.commit()
    
    # Auth tables
    User.create_table(db)
    Company.create_table(db)
    Session.create_table(db)
    
    # Inventory tables
    db.executescript("""
        CREATE TABLE IF NOT EXISTS warehouses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT UNIQUE,
            location TEXT,
            company_id INTEGER,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL,
            warehouse_id INTEGER NOT NULL,
            quantity REAL DEFAULT 0,
            UNIQUE(producto_id, warehouse_id)
        );
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
        );
        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            parent_id INTEGER
        );
    """)
    db.commit()
    
    # Add stock_minimo column to productos if not exists
    try:
        db.execute("SELECT stock_minimo FROM productos LIMIT 1")
    except:
        db.execute("ALTER TABLE productos ADD COLUMN stock_minimo REAL")
        db.commit()
    
    # Sales tables
    db.executescript("""
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
    db.commit()
    
    # Accounting tables
    db.executescript("""
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
    db.commit()
    
    # Seed chart of accounts
    if db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0:
        from core.accounting import accounts_seed
        accounts_seed()
    
    # CRM tables
    db.executescript("""
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
    db.commit()
    
    # Projects tables
    db.executescript("""
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
    db.commit()
    
    # Seed
    if db.execute("SELECT COUNT(*) FROM productos").fetchone()[0] == 0:
        db.execute("INSERT INTO productos (codigo, nombre, precio_unitario) VALUES ('PROD-001', 'Laptop', 15000.00)")
    if db.execute("SELECT COUNT(*) FROM clientes").fetchone()[0] == 0:
        db.execute("INSERT INTO clientes (nombre, email) VALUES ('Acme Corp', 'contact@acme.com')")
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        db.execute("INSERT INTO companies (name, slug) VALUES ('Demo Company', 'demo')")
        pw_hash, salt = hash_password("admin123")
        db.execute("INSERT INTO users (email, password_hash, salt, full_name, role, company_id) VALUES (?, ?, ?, ?, ?, ?)",
                   ("admin@demo.com", pw_hash, salt, "Admin", "admin", 1))
    db.commit()

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", default="/tmp/pgerp.sock")
    args = parser.parse_args()
    init_db()
    print(f"Handlers registered: {list(HANDLERS.keys())}", flush=True)
    asyncio.run(start_server(args.socket))

if __name__ == "__main__":
    main()
