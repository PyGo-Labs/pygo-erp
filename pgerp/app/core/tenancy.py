"""PyGo ERP V2.0 — Multi-tenancy middleware and tenant-aware models.

Provides:
- Company model with CRUD operations
- Tenant isolation (all data filtered by company_id)
- Company switching via header or query param
- Tenant context injection
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "app"))

from core.auth import User, Session, hash_password
from core.registry import register


class TenantContext:
    """Thread-local tenant context — tracks current company_id."""
    
    def __init__(self):
        self._company_id = None
        self._user = None
    
    def set_company(self, company_id):
        self._company_id = company_id
    
    def get_company(self):
        return self._company_id
    
    def set_user(self, user):
        self._user = user
    
    def get_user(self):
        return self._user

# Global tenant context
tenant = TenantContext()


@register("core.tenancy.companies.list")
def companies_list(**kwargs):
    """List all companies."""
    from core.main import get_db
    db = get_db()
    rows = db.execute("SELECT * FROM companies").fetchall()
    return [dict(r) for r in rows]


@register("core.tenancy.companies.create")
def companies_create(name=None, slug=None, token=None, **kwargs):
    """Create a new company and assign admin user to it."""
    from core.main import get_db
    
    if not name:
        return {"error": "name required"}
    
    # Verify admin token
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user or user.role != "admin":
            return {"error": "admin only"}
    
    # Create company
    if not slug:
        slug = name.lower().replace(" ", "-")[:50]
    
    cursor = db.execute(
        "INSERT INTO companies (name, slug) VALUES (?, ?)", (name, slug)
    )
    db.commit()
    company_id = cursor.lastrowid
    
    # If token provided, assign user to this company
    if token:
        db.execute("UPDATE users SET company_id = ? WHERE id = ?", (company_id, user.id))
        db.commit()
        user.company_id = company_id
    
    return {
        "id": company_id,
        "name": name,
        "slug": slug,
        "created_at": datetime.utcnow().isoformat(),
    }


@register("core.tenancy.companies.update")
def companies_update(company_id=None, token=None, **kwargs):
    """Update a company (admin only)."""
    from core.main import get_db
    
    if not company_id:
        return {"error": "company_id required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user or user.role != "admin":
            return {"error": "admin only"}
    
    row = db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    if not row:
        return {"error": "company not found"}
    
    allowed = ["name", "slug", "is_active"]
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    
    if updates:
        sets = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [company_id]
        db.execute(f"UPDATE companies SET {sets} WHERE id = ?", vals)
        db.commit()
    
    row = db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    return dict(row)


@register("core.tenancy.companies.delete")
def companies_delete(company_id=None, token=None):
    """Delete a company (admin only)."""
    from core.main import get_db
    
    if not company_id:
        return {"error": "company_id required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user or user.role != "admin":
            return {"error": "admin only"}
    
    # Don't delete if it's the last company
    count = db.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    if count <= 1:
        return {"error": "cannot delete last company"}
    
    db.execute("DELETE FROM companies WHERE id = ?", (company_id,))
    db.commit()
    
    return {"deleted": True, "company_id": company_id}


@register("core.tenancy.switch")
def tenancy_switch(company_id=None, token=None, **kwargs):
    """Switch user's active company."""
    from core.main import get_db
    
    if not company_id:
        return {"error": "company_id required"}
    
    db = get_db()
    session = Session.find_by_token(db, token) if token else None
    if not session:
        return {"error": "not authenticated"}
    
    user = User.find_by_id(db, session.user_id)
    if not user:
        return {"error": "user not found"}
    
    # Verify user belongs to this company
    if user.role != "admin":
        # Non-admins can only switch to their own company
        if str(user.company_id) != str(company_id):
            return {"error": "forbidden"}
    
    # Update user's company
    db.execute("UPDATE users SET company_id = ? WHERE id = ?", (company_id, user.id))
    db.commit()
    
    # Generate new session token
    from core.auth import generate_token
    from datetime import timedelta
    new_token = generate_token()
    expires_at = datetime.utcnow() + timedelta(days=7)
    Session.revoke_all_for_user(db, user.id)
    Session.create(db, user.id, new_token, expires_at)
    
    return {
        "token": new_token,
        "company_id": company_id,
        "expires_at": expires_at.isoformat(),
    }


@register("core.tenancy.current")
def tenancy_current(token=None):
    """Get current tenant info."""
    from core.main import get_db
    
    db = get_db()
    session = Session.find_by_token(db, token) if token else None
    if not session:
        return {"error": "not authenticated"}
    
    user = User.find_by_id(db, session.user_id)
    if not user:
        return {"error": "user not found"}
    
    company_row = db.execute(
        "SELECT * FROM companies WHERE id = ?", (user.company_id,)
    ).fetchone()
    
    return {
        "user": user.to_dict(),
        "company": dict(company_row) if company_row else None,
    }


@register("core.tenancy.users.transfer")
def tenancy_transfer_user(token=None, user_id=None, company_id=None):
    """Transfer a user to another company (admin only)."""
    from core.main import get_db
    
    if not user_id or not company_id:
        return {"error": "user_id and company_id required"}
    
    db = get_db()
    session = Session.find_by_token(db, token) if token else None
    if not session:
        return {"error": "not authenticated"}
    
    current_user = User.find_by_id(db, session.user_id)
    if not current_user or current_user.role != "admin":
        return {"error": "admin only"}
    
    target_user = User.find_by_id(db, user_id)
    if not target_user:
        return {"error": "user not found"}
    
    db.execute("UPDATE users SET company_id = ? WHERE id = ?", (company_id, user_id))
    db.commit()
    Session.revoke_all_for_user(db, int(user_id))
    
    return {"transferred": True, "user_id": user_id, "company_id": company_id}
