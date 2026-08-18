"""PyGo ERP V2.0 — Auth module.

Provides:
- User management (CRUD, password hashing, roles)
- Session management (JWT)
- Multi-tenancy (companies + tenant isolation)
- Role-based access control (admin, manager, user)
"""
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from datetime import datetime, timedelta

# Password hashing (PBKDF2 — stdlib only, no bcrypt dependency)
def hash_password(password: str, salt: str = None) -> tuple:
    """Hash a password with PBKDF2-SHA256. Returns (hash, salt)."""
    if salt is None:
        salt = secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100_004)
    return pw_hash.hex(), salt


def verify_password(password: str, pw_hash: str, salt: str) -> bool:
    """Verify a password against a hash."""
    computed, _ = hash_password(password, salt)
    return hmac.compare_digest(computed, pw_hash)


def generate_token() -> str:
    """Generate a secure random token."""
    return secrets.token_urlsafe(32)


class User:
    """User model."""
    TABLE = "users"

    def __init__(self, id=None, email="", password_hash="", salt="", 
                 full_name="", role="user", company_id=None, is_active=True,
                 created_at=None, last_login=None):
        self.id = id
        self.email = email
        self.password_hash = password_hash
        self.salt = salt
        self.full_name = full_name
        self.role = role
        self.company_id = company_id
        self.is_active = is_active
        self.created_at = created_at or datetime.utcnow().isoformat()
        self.last_login = last_login

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "company_id": self.company_id,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "last_login": self.last_login,
        }

    @classmethod
    def create_table(cls, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                full_name TEXT,
                role TEXT DEFAULT 'user' CHECK(role IN ('admin', 'manager', 'user')),
                company_id INTEGER,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                last_login TEXT
            )
        """)

    @classmethod
    def create(cls, conn, email, password, full_name="", role="user", company_id=None):
        pw_hash, salt = hash_password(password)
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash, salt, full_name, role, company_id) VALUES (?, ?, ?, ?, ?, ?)",
            (email, pw_hash, salt, full_name, role, company_id)
        )
        conn.commit()
        return cls.find_by_id(conn, cursor.lastrowid)

    @classmethod
    def find_by_id(cls, conn, user_id):
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return None
        return cls(**dict(row))

    @classmethod
    def find_by_email(cls, conn, email):
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row:
            return None
        return cls(**dict(row))

    @classmethod
    def authenticate(cls, conn, email, password):
        user = cls.find_by_email(conn, email)
        if not user or not user.is_active:
            return None
        if not verify_password(password, user.password_hash, user.salt):
            return None
        conn.execute("UPDATE users SET last_login = ? WHERE id = ?",
                     (datetime.utcnow().isoformat(), user.id))
        conn.commit()
        return user

    @classmethod
    def list_all(cls, conn, company_id=None):
        if company_id:
            rows = conn.execute("SELECT * FROM users WHERE company_id = ?", (company_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM users").fetchall()
        return [cls(**dict(r)) for r in rows]


class Company:
    """Company (tenant) model."""
    TABLE = "companies"

    def __init__(self, id=None, name="", slug="", is_active=True, created_at=None):
        self.id = id
        self.name = name
        self.slug = slug
        self.is_active = is_active
        self.created_at = created_at or datetime.utcnow().isoformat()

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "is_active": self.is_active,
            "created_at": self.created_at,
        }

    @classmethod
    def create_table(cls, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

    @classmethod
    def create(cls, conn, name, slug=None):
        if not slug:
            slug = name.lower().replace(" ", "-")[:50]
        cursor = conn.execute(
            "INSERT INTO companies (name, slug) VALUES (?, ?)", (name, slug)
        )
        conn.commit()
        return cls.find_by_id(conn, cursor.lastrowid)

    @classmethod
    def find_by_id(cls, conn, company_id):
        row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
        if not row:
            return None
        return cls(**dict(row))

    @classmethod
    def list_all(cls, conn):
        rows = conn.execute("SELECT * FROM companies").fetchall()
        return [cls(**dict(r)) for r in rows]


class Session:
    """Session model — JWT token storage for revocation."""
    TABLE = "sessions"

    def __init__(self, id=None, user_id=None, token="", expires_at=None, created_at=None):
        self.id = id
        self.user_id = user_id
        self.token = token
        self.expires_at = expires_at
        self.created_at = created_at or datetime.utcnow().isoformat()

    @classmethod
    def create_table(cls, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT UNIQUE NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

    @classmethod
    def create(cls, conn, user_id, token, expires_at):
        conn.execute(
            "INSERT INTO sessions (user_id, token, expires_at) VALUES (?, ?, ?)",
            (user_id, token, expires_at.isoformat())
        )
        conn.commit()

    @classmethod
    def find_by_token(cls, conn, token):
        row = conn.execute(
            "SELECT * FROM sessions WHERE token = ? AND expires_at > ?",
            (token, datetime.utcnow().isoformat())
        ).fetchone()
        if not row:
            return None
        return cls(**dict(row))

    @classmethod
    def revoke(cls, conn, token):
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()

    @classmethod
    def revoke_all_for_user(cls, conn, user_id):
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.commit()
