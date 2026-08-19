"""PyGo ORM — Migrations.

Versioned schema changes:
- Track applied migrations in _migration table
- Apply forward/backward
- Auto-run pending migrations
"""
import os
import sqlite3
from datetime import datetime

DB_PATH = os.environ.get("PYGO_DB", "/tmp/pgerp.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


class Migration:
    """Base class for schema migrations."""
    
    def __init__(self, name=None):
        self.name = name
    
    def up(self, conn):
        raise NotImplementedError
    
    def down(self, conn):
        raise NotImplementedError


class MigrationHistory:
    """Track which migrations have been applied."""
    
    @staticmethod
    def ensure_table(conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                applied_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    
    @staticmethod
    def applied(conn):
        return [r["name"] for r in conn.execute("SELECT name FROM _migrations").fetchall()]
    
    @staticmethod
    def record(conn, name):
        conn.execute("INSERT INTO _migrations (name) VALUES (?)", (name,))
        conn.commit()
    
    @staticmethod
    def remove(conn, name):
        conn.execute("DELETE FROM _migrations WHERE name = ?", (name,))
        conn.commit()


def migrate():
    """Run all pending migrations."""
    conn = get_db()
    MigrationHistory.ensure_table(conn)
    
    applied = MigrationHistory.applied(conn)
    pending = [m for m in MigrationRegistry.migrations if m.name not in applied]
    
    results = []
    for migration in sorted(pending, key=lambda m: m.name):
        try:
            migration.up(conn)
            MigrationHistory.record(conn, migration.name)
            results.append({"name": migration.name, "status": "applied"})
        except Exception as e:
            results.append({"name": migration.name, "status": "error", "error": str(e)})
    
    return results


def rollback(steps=1):
    """Rollback last N migrations."""
    conn = get_db()
    MigrationHistory.ensure_table(conn)
    
    applied = MigrationHistory.applied(conn)
    to_rollback = applied[-steps:] if steps <= len(applied) else applied
    
    results = []
    for name in reversed(to_rollback):
        migration = next((m for m in MigrationRegistry.migrations if m.name == name), None)
        if migration:
            try:
                migration.down(conn)
                MigrationHistory.remove(conn, name)
                results.append({"name": name, "status": "rolled_back"})
            except Exception as e:
                results.append({"name": name, "status": "error", "error": str(e)})
    
    return results


def migration_status():
    """Check migration status."""
    conn = get_db()
    MigrationHistory.ensure_table(conn)
    
    applied = MigrationHistory.applied(conn)
    all_migrations = [m.name for m in MigrationRegistry.migrations]
    pending = [m for m in all_migrations if m not in applied]
    
    return {
        "applied": applied,
        "pending": pending,
        "total": len(all_migrations),
    }


class MigrationRegistry:
    migrations = []
    
    @classmethod
    def register(cls, migration):
        cls.migrations.append(migration)


def migration(name):
    """Decorator to register a migration."""
    def decorator(cls):
        instance = cls()
        instance.name = name
        MigrationRegistry.register(instance)
        return cls
    return decorator
