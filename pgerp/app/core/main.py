"""PyGo ERP — Python domain runtime server.

Serves all business logic handlers via UDS + MessagePack.
Go web layer calls handlers like: app.Call("core.services.productos.list", {})

All models, services, and business logic live here.
V2.0: Full CRUD for productos, clientes, facturas + dashboard stats.
"""
import asyncio
import os
import socket
import sys
import traceback
import sqlite3
from pathlib import Path

import msgpack

# Add framework to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Database setup
DB_PATH = os.environ.get("PYGO_DB", "/tmp/pgerp.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Handlers registry
HANDLERS = {}

def register(name):
    """Decorator to register a handler by qualified name."""
    def decorator(func):
        HANDLERS[name] = func
        return func
    return decorator

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
    for t in ["productos", "clientes", "facturas"]:
        counts[t] = db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    return {"status": "ok", "models": ["Producto", "Cliente", "Factura"], "counts": counts}

@register("core.services.dashboard")
def dashboard():
    """Dashboard stats."""
    db = get_db()
    productos = db.execute("SELECT COUNT(*) FROM productos").fetchone()[0]
    clientes = db.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
    facturas = db.execute("SELECT COUNT(*) FROM facturas").fetchone()[0]
    total_ventas = db.execute("SELECT COALESCE(SUM(total), 0) FROM facturas").fetchone()[0]
    return {
        "productos": productos,
        "clientes": clientes,
        "facturas": facturas,
        "total_ventas": total_ventas,
    }

# --- Productos CRUD ---

@register("core.services.productos.list")
def productos_list(**kwargs):
    """List all productos."""
    return Producto.all()

@register("core.services.productos.find")
def productos_find(id=None, **kwargs):
    """Find a producto by id."""
    if not id:
        return {"error": "id is required"}
    return Producto.find(id) or {"error": "not found"}

@register("core.services.productos.create")
def productos_create(**data):
    """Create a new producto."""
    if not data.get("nombre"):
        return {"error": "nombre is required"}
    if not data.get("precio") and not data.get("precio_unitario"):
        return {"error": "precio is required"}
    return Producto.create(**data)

@register("core.services.productos.update")
def productos_update(id=None, **data):
    """Update a producto."""
    if not id:
        return {"error": "id is required"}
    return Producto.update(id, **data)

@register("core.services.productos.delete")
def productos_delete(id=None, **kwargs):
    """Delete a producto."""
    if not id:
        return {"error": "id is required"}
    Producto.delete(id)
    return {"deleted": True, "id": id}

# --- Clientes CRUD ---

@register("core.services.clientes.list")
def clientes_list(**kwargs):
    """List all clientes."""
    return Cliente.all()

@register("core.services.clientes.find")
def clientes_find(id=None, **kwargs):
    """Find a cliente by id."""
    if not id:
        return {"error": "id is required"}
    return Cliente.find(id) or {"error": "not found"}

@register("core.services.clientes.create")
def clientes_create(**data):
    """Create a new cliente."""
    if not data.get("nombre"):
        return {"error": "nombre is required"}
    return Cliente.create(**data)

@register("core.services.clientes.update")
def clientes_update(id=None, **data):
    """Update a cliente."""
    if not id:
        return {"error": "id is required"}
    return Cliente.update(id, **data)

@register("core.services.clientes.delete")
def clientes_delete(id=None, **kwargs):
    """Delete a cliente."""
    if not id:
        return {"error": "id is required"}
    Cliente.delete(id)
    return {"deleted": True, "id": id}

# --- Facturas CRUD ---

@register("core.services.facturas.list")
def facturas_list(**kwargs):
    """List all facturas."""
    return Factura.all()

@register("core.services.facturas.find")
def facturas_find(id=None, **kwargs):
    """Find a factura by id."""
    if not id:
        return {"error": "id is required"}
    return Factura.find(id) or {"error": "not found"}

@register("core.services.facturas.create")
def facturas_create(**data):
    """Create a new factura."""
    if not data.get("cliente_id"):
        return {"error": "cliente_id is required"}
    if data.get("total") is None:
        data["total"] = 0.0
    return Factura.create(**data)

@register("core.services.facturas.update")
def facturas_update(id=None, **data):
    """Update a factura."""
    if not id:
        return {"error": "id is required"}
    return Factura.update(id, **data)

@register("core.services.facturas.delete")
def facturas_delete(id=None, **kwargs):
    """Delete a factura."""
    if not id:
        return {"error": "id is required"}
    Factura.delete(id)
    return {"deleted": True, "id": id}

# --- UDS server ---

def handle_request(payload: bytes) -> bytes:
    """Process a single msgpack-encoded request frame."""
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

class UDSHandler:
    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer

    async def handle(self):
        try:
            while True:
                header = await self.reader.readexactly(4)
                length = int.from_bytes(header, byteorder="big")
                if length == 0:
                    continue
                payload = await self.reader.readexactly(length)
                response = handle_request(payload)
                resp_header = len(response).to_bytes(4, byteorder="big")
                self.writer.write(resp_header)
                self.writer.write(response)
                await self.writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            self.writer.close()

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
    """Initialize default tables if they don't exist."""
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
    # Seed data (only if empty)
    if db.execute("SELECT COUNT(*) FROM productos").fetchone()[0] == 0:
        db.execute("INSERT INTO productos (codigo, nombre, precio_unitario) VALUES ('PROD-001', 'Laptop', 15000.00)")
    if db.execute("SELECT COUNT(*) FROM clientes").fetchone()[0] == 0:
        db.execute("INSERT INTO clientes (nombre, email) VALUES ('Acme Corp', 'contact@acme.com')")
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
