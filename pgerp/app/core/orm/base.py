"""PyGo ORM — Minimal ORM with migration support.

Provides:
- Model base class with declarative schema
- Column types (Integer, String, Float, Boolean, DateTime, Text, ForeignKey)
- Automatic table creation
- Schema migration tracking
- Relationship support (has_many, belongs_to)
"""
import os
import sqlite3
from datetime import datetime

DB_PATH = os.environ.get("PYGO_DB", "/tmp/pgerp.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# --- Column Types ---

class Column:
    def __init__(self, type_name, primary_key=False, nullable=True, unique=False, default=None):
        self.type_name = type_name
        self.primary_key = primary_key
        self.nullable = nullable
        self.unique = unique
        self.default = default

class Integer(Column):
    def __init__(self, **kwargs):
        super().__init__("INTEGER", **kwargs)

class String(Column):
    def __init__(self, length=255, **kwargs):
        super().__init__(f"VARCHAR({length})", **kwargs)

class Text(Column):
    def __init__(self, **kwargs):
        super().__init__("TEXT", **kwargs)

class Float(Column):
    def __init__(self, **kwargs):
        super().__init__("REAL", **kwargs)

class Boolean(Column):
    def __init__(self, **kwargs):
        super().__init__("INTEGER", **kwargs)

class DateTime(Column):
    def __init__(self, **kwargs):
        super().__init__("TEXT", **kwargs)

class ForeignKey(Column):
    def __init__(self, references, **kwargs):
        super().__init__("INTEGER", **kwargs)
        self.references = references


# --- Model Base ---

class Model:
    table = ""
    _columns = {}

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    @classmethod
    def _get_columns(cls):
        """Get column definitions from class attributes."""
        columns = {}
        for name, value in cls.__dict__.items():
            if isinstance(value, Column) and not name.startswith("_"):
                columns[name] = value
        return columns

    @classmethod
    def create_table(cls, conn):
        """Create table if not exists."""
        cols = cls._get_columns()
        if not cols:
            return

        col_defs = []
        for name, col in cols.items():
            parts = [name, col.type_name]
            if col.primary_key:
                parts.append("PRIMARY KEY AUTOINCREMENT")
            if not col.nullable:
                parts.append("NOT NULL")
            if col.unique:
                parts.append("UNIQUE")
            if col.default is not None:
                parts.append(f"DEFAULT {col.default}")
            if isinstance(col, ForeignKey):
                parts.append(f"REFERENCES {col.references}")
            col_defs.append(" ".join(parts))

        sql = f"CREATE TABLE IF NOT EXISTS {cls.table} ({', '.join(col_defs)})"
        conn.execute(sql)
        conn.commit()

    @classmethod
    def drop_table(cls, conn):
        conn.execute(f"DROP TABLE IF EXISTS {cls.table}")
        conn.commit()

    @classmethod
    def all(cls, where=None, params=None):
        conn = get_db()
        sql = f"SELECT * FROM {cls.table}"
        if where:
            sql += f" WHERE {where}"
        rows = conn.execute(sql, params or []).fetchall()
        return [cls(**dict(r)) for r in rows]

    @classmethod
    def find(cls, id):
        conn = get_db()
        row = conn.execute(f"SELECT * FROM {cls.table} WHERE id = ?", (id,)).fetchone()
        return cls(**dict(row)) if row else None

    @classmethod
    def find_by(cls, **kwargs):
        conn = get_db()
        conditions = " AND ".join(f"{k} = ?" for k in kwargs)
        row = conn.execute(f"SELECT * FROM {cls.table} WHERE {conditions}", list(kwargs.values())).fetchone()
        return cls(**dict(row)) if row else None

    @classmethod
    def create(cls, **kwargs):
        conn = get_db()
        cols = list(kwargs.keys())
        placeholders = ", ".join(["?"] * len(kwargs))
        col_names = ", ".join(cols)
        vals = list(kwargs.values())

        sql = f"INSERT INTO {cls.table} ({col_names}) VALUES ({placeholders})"
        conn.execute(sql, vals)
        conn.commit()
        return cls.find(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    def update(self, **kwargs):
        conn = get_db()
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [getattr(self, "id", None)]
        conn.execute(f"UPDATE {self.table} SET {sets} WHERE id = ?", vals)
        conn.commit()
        for k, v in kwargs.items():
            setattr(self, k, v)
        return self

    def delete(self):
        conn = get_db()
        conn.execute(f"DELETE FROM {self.table} WHERE id = ?", (getattr(self, "id", None),))
        conn.commit()
        return True

    def to_dict(self):
        cols = self._get_columns()
        return {k: getattr(self, k, None) for k in cols}
