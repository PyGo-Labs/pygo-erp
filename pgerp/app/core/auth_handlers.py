"""PyGo ERP V2.0 — Auth handlers.

Registers auth handlers for the UDS bridge.
"""
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "app"))

from core.auth import User, Company, Session, hash_password, verify_password, generate_token
from core.registry import register


def get_db():
    import sqlite3
    db_path = os.environ.get("PYGO_DB", "/tmp/pgerp.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@register("core.auth.login")
def auth_login(email=None, password=None):
    if not email or not password:
        return {"error": "email and password required"}
    
    db = get_db()
    user = User.authenticate(db, email, password)
    if not user:
        return {"error": "invalid credentials"}
    
    token = generate_token()
    expires_at = datetime.utcnow() + timedelta(days=7)
    Session.create(db, user.id, token, expires_at)
    
    return {"token": token, "user": user.to_dict()}


@register("core.auth.logout")
def auth_logout(token=None):
    if not token:
        return {"error": "token required"}
    db = get_db()
    Session.revoke(db, token)
    return {"success": True}


@register("core.auth.me")
def auth_me(token=None):
    if not token:
        return {"error": "not authenticated"}
    db = get_db()
    session = Session.find_by_token(db, token)
    if not session:
        return {"error": "session expired"}
    user = User.find_by_id(db, session.user_id)
    if not user:
        return {"error": "user not found"}
    return user.to_dict()


@register("core.auth.users.list")
def auth_users_list(token=None):
    db = get_db()
    session = Session.find_by_token(db, token) if token else None
    if not session:
        return {"error": "not authenticated"}
    current_user = User.find_by_id(db, session.user_id)
    if not current_user or current_user.role not in ("admin", "manager"):
        return {"error": "forbidden"}
    users = User.list_all(db, company_id=current_user.company_id)
    return [u.to_dict() for u in users]


@register("core.auth.users.create")
def auth_users_create(token=None, email=None, password=None, full_name="", role="user"):
    db = get_db()
    session = Session.find_by_token(db, token) if token else None
    if not session:
        return {"error": "not authenticated"}
    current_user = User.find_by_id(db, session.user_id)
    if not current_user or current_user.role != "admin":
        return {"error": "admin only"}
    if not email or not password:
        return {"error": "email and password required"}
    existing = User.find_by_email(db, email)
    if existing:
        return {"error": "email already exists"}
    new_user = User.create(db, email, password, full_name, role, company_id=current_user.company_id)
    return new_user.to_dict()


@register("core.auth.users.update")
def auth_users_update(token=None, user_id=None, **kwargs):
    db = get_db()
    session = Session.find_by_token(db, token) if token else None
    if not session:
        return {"error": "not authenticated"}
    current_user = User.find_by_id(db, session.user_id)
    if not current_user or current_user.role != "admin":
        return {"error": "admin only"}
    if not user_id:
        return {"error": "user_id required"}
    user = User.find_by_id(db, user_id)
    if not user:
        return {"error": "user not found"}
    allowed = ["full_name", "role", "is_active"]
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if updates:
        sets = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [user_id]
        db.execute(f"UPDATE users SET {sets} WHERE id = ?", vals)
        db.commit()
    return User.find_by_id(db, user_id).to_dict()


@register("core.auth.users.delete")
def auth_users_delete(token=None, user_id=None):
    db = get_db()
    session = Session.find_by_token(db, token) if token else None
    if not session:
        return {"error": "not authenticated"}
    current_user = User.find_by_id(db, session.user_id)
    if not current_user or current_user.role != "admin":
        return {"error": "admin only"}
    if not user_id:
        return {"error": "user_id required"}
    if str(current_user.id) == str(user_id):
        return {"error": "cannot delete yourself"}
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    Session.revoke_all_for_user(db, int(user_id))
    return {"deleted": True, "user_id": user_id}
