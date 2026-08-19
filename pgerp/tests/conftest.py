"""Pytest configuration."""
import pytest
import sys
import os
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


def _setup_db():
    """Create test DB using migrations."""
    db_path = "/tmp/pgerp_test.db"
    try:
        os.unlink(db_path)
    except FileNotFoundError:
        pass
    
    os.environ["PYGO_DB"] = db_path
    
    from core import migrations  # noqa: F401
    from core.orm.migrations import migrate
    migrate()
    
    conn = sqlite3.connect(db_path)
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
        os.unlink("/tmp/pgerp_test.db")
    except:
        pass
