"""PyGo ERP — Python domain runtime server.

Serves all business logic handlers via UDS + MessagePack.
Go web layer calls handlers like: app.Call("core.services.productos.list", {})

All models, services, and business logic live here.
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

# --- Models (simplified ORM) ---

class BaseModel:
    """Minimal ORM — uses SQLite directly."""
    table = ""
    
    @classmethod
    def all(cls):
        db = get_db()
        rows = db.execute(f"SELECT * FROM {cls.table}").fetchall()
        return [dict(r) for r in rows]
    
    @classmethod
    def filter(cls, **conditions):
        db = get_db()
        where = " AND ".join(f"{k} = ?" for k in conditions)
        vals = list(conditions.values())
        rows = db.execute(f"SELECT * FROM {cls.table} WHERE {where}", vals).fetchall()
        return [dict(r) for r in rows]

class Producto(BaseModel):
    table = "productos"

class Cliente(BaseModel):
    table = "clientes"

class Factura(BaseModel):
    table = "facturas"

# --- Service handlers ---

@register("core.services.health")
def health():
    """Health check handler."""
    return {"status": "ok", "models": ["Producto", "Cliente", "Factura"]}

@register("core.services.productos.list")
def productos_list(**kwargs):
    """List all productos."""
    return Producto.all()

@register("core.services.productos.create")
def productos_create(**data):
    """Create a new producto."""
    db = get_db()
    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    db.execute(f"INSERT INTO productos ({cols}) VALUES ({placeholders})", list(data.values()))
    db.commit()
    return {"id": db.execute("SELECT last_insert_rowid()").fetchone()[0], **data}

@register("core.services.clientes.list")
def clientes_list(**kwargs):
    """List all clientes."""
    return Cliente.all()

@register("core.services.facturas.list")
def facturas_list(**kwargs):
    """List all facturas."""
    return Factura.all()

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
            fecha TEXT,
            total REAL,
            cliente_id INTEGER
        );
    """)
    db.commit()
    # Seed data
    db.execute("INSERT OR IGNORE INTO productos (codigo, nombre, precio_unitario) VALUES ('PROD-001', 'Laptop', 15000.00)")
    db.execute("INSERT OR IGNORE INTO clientes (nombre, email) VALUES ('Acme Corp', 'contact@acme.com')")
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
