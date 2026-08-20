"""Pytest configuration.

The DB is rebuilt from real migrations for every test, so the schema under
test is exactly the production schema — this is what lets these tests catch
column drift and broken SQL instead of only checking that functions exist.
"""
import pytest
import sys
import os
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

DB_PATH = "/tmp/pgerp_test.db"


def _load_all_migrations():
    """Import every migration package so migrate() sees the full schema."""
    from core import migrations  # noqa: F401  (base tables)
    from core.migrations import accounting  # noqa: F401
    from core.migrations import workflow  # noqa: F401
    from core.migrations import commercial  # noqa: F401
    from core.migrations import purchasing  # noqa: F401
    from core.migrations import purchasing_fix  # noqa: F401
    from core.migrations import accounting_full  # noqa: F401
    from core.migrations import hr  # noqa: F401
    from core.migrations import mrp  # noqa: F401
    from core.migrations import modules  # noqa: F401
    from core.migrations import tax_engine  # noqa: F401
    from core.migrations import setup_audit  # noqa: F401
    from core.migrations import valuation  # noqa: F401
    from core.migrations import traceability  # noqa: F401


def _setup_db():
    """Create test DB using migrations."""
    try:
        os.unlink(DB_PATH)
    except FileNotFoundError:
        pass

    os.environ["PYGO_DB"] = DB_PATH

    _load_all_migrations()
    from core.orm.migrations import migrate
    migrate()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("INSERT OR IGNORE INTO companies (id, name, slug) VALUES (1, 'Test Co', 'test')")
    conn.commit()

    return conn


@pytest.fixture(autouse=True)
def db_conn():
    """Auto-use fixture: every test gets a fresh DB via migrations."""
    conn = _setup_db()
    yield conn
    conn.close()
    try:
        os.unlink(DB_PATH)
    except OSError:
        pass


# ---------------------------------------------------------------- seed helpers

@pytest.fixture
def seed_commercial():
    """UoM, pricelists, payment terms and document sequences."""
    from core.commercial_uom import uom_seed
    from core.commercial_pricing import pricelists_seed
    from core.commercial_terms import payment_terms_seed, sequences_seed
    uom_seed()
    pricelists_seed()
    payment_terms_seed()
    sequences_seed()


@pytest.fixture
def seed_taxes():
    """Generic (country-agnostic) tax engine data."""
    from core.tax_engine import tax_seed_generic
    tax_seed_generic()


@pytest.fixture
def seed_accounting():
    """Chart of accounts plus cost centers."""
    from core.accounting import accounts_seed
    from core.accounting_analytic import cost_centers_seed
    accounts_seed()
    cost_centers_seed()


@pytest.fixture
def seed_hr():
    """Leave types."""
    from core.hr_leave_expenses import leave_types_seed
    leave_types_seed()


@pytest.fixture
def make_product(db_conn):
    """Factory: insert a product and return its id."""
    def _make(codigo="P-1", nombre="Producto", precio=100.0, cost=60.0):
        cur = db_conn.execute(
            "INSERT INTO productos (codigo, nombre, precio_unitario, cost) VALUES (?, ?, ?, ?)",
            (codigo, nombre, precio, cost),
        )
        db_conn.commit()
        return cur.lastrowid
    return _make


@pytest.fixture
def make_warehouse(db_conn):
    """Factory: insert a warehouse and return its id."""
    def _make(name="Main", code="MAIN"):
        cur = db_conn.execute(
            "INSERT INTO warehouses (name, code) VALUES (?, ?)", (name, code))
        db_conn.commit()
        return cur.lastrowid
    return _make


@pytest.fixture
def make_stock(db_conn):
    """Factory: set an absolute stock level for product/warehouse."""
    def _make(producto_id, warehouse_id, qty):
        db_conn.execute(
            "INSERT INTO stock (producto_id, warehouse_id, quantity) VALUES (?, ?, ?)",
            (producto_id, warehouse_id, qty),
        )
        db_conn.commit()
    return _make


@pytest.fixture
def make_employee(db_conn):
    """Factory: insert an employee and return its id."""
    def _make(first="Ana", last="Torres", department_id=None):
        cur = db_conn.execute(
            "INSERT INTO employees (first_name, last_name, status, department_id) "
            "VALUES (?, ?, 'active', ?)",
            (first, last, department_id),
        )
        db_conn.commit()
        return cur.lastrowid
    return _make
