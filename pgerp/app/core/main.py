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
    # timeout: wait instead of failing instantly on a busy lock
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    # WAL allows concurrent readers alongside a writer
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("PRAGMA foreign_keys=ON")
    except Exception:
        pass
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

# --- Reports PDF ---
from core.reports import reports_pdf_invoice, reports_pdf_quote, reports_pdf_ticket

# --- i18n ---
from core import i18n_handlers

# --- Files ---
from core import files

# --- Accounting Real ---
from core import accounting_real

# --- Accounting migrations ---
from core.migrations import accounting  # noqa: F401

# --- Workflow + Permissions ---
from core import workflow_permissions

# --- Workflow migrations ---
from core.migrations import workflow  # noqa: F401

# --- Export/Import ---
from core import export_import
from core import export_excel

# --- Notifications ---
from core import notifications

# --- Cache ---
from core import cache

# --- Commercial base (B1) ---
from core import commercial_uom
from core import commercial_pricing
from core import commercial_terms
from core.migrations import commercial  # noqa: F401

# --- Purchasing full (B2) ---
from core import purchasing_suppliers
from core import purchasing_rfq
from core import purchasing_receipts
from core.migrations import purchasing  # noqa: F401
from core.migrations import purchasing_fix  # noqa: F401

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
        
        filtered_args = {k: v for k, v in args.items() if k != "token"}
        result = fn(**filtered_args)
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
    """Initialize database via versioned migrations."""
    from core import migrations  # noqa: F401
    from core.orm.migrations import migrate
    
    results = migrate()
    print(f'Migrations applied: {len(results)}', flush=True)
    
    # Seed default admin if no users exist
    db = get_db()
    if db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
        db.execute("INSERT INTO companies (id, name, slug) VALUES (1, 'Demo Company', 'demo')")
        from core.auth import hash_password
        pw_hash, salt = hash_password('admin123')
        db.execute('INSERT INTO users (email, password_hash, salt, full_name, role, company_id) VALUES (?, ?, ?, ?, ?, ?)',
                   ('admin@demo.com', pw_hash, salt, 'Admin', 'admin', 1))
        db.commit()
        print('Default admin: admin@demo.com / admin123', flush=True)

    # Seed universal core data (idempotent)
    try:
        from core.accounting import accounts_seed
        accounts_seed()
    except Exception as e:
        print(f'accounts_seed skipped: {e}', flush=True)

    for seed_fn, label in [
        ('core.commercial_uom:uom_seed', 'uom'),
        ('core.commercial_pricing:pricelists_seed', 'pricelists'),
        ('core.commercial_terms:payment_terms_seed', 'payment_terms'),
        ('core.commercial_terms:sequences_seed', 'sequences'),
    ]:
        mod_name, fn_name = seed_fn.split(':')
        try:
            mod = __import__(mod_name, fromlist=[fn_name])
            getattr(mod, fn_name)()
        except Exception as e:
            print(f'{label} seed skipped: {e}', flush=True)

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
