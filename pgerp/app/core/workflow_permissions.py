"""PyGo ERP V2.0 — Workflow engine + granular permissions."""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "app"))

from core.registry import register


def get_db():
    import sqlite3
    db_path = os.environ.get("PYGO_DB", "/tmp/pgerp.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# --- Workflow States ---

@register("core.workflow.states.list")
def workflow_states_list(entity_type=None, **kwargs):
    """List workflow states."""
    db = get_db()
    query = "SELECT * FROM workflow_states"
    params = []
    if entity_type:
        query += " WHERE entity_type = ?"
        params.append(entity_type)
    query += " ORDER BY entity_type, sort_order"
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]


@register("core.workflow.states.create")
def workflow_states_create(name=None, entity_type=None, sort_order=0, is_initial=False, is_final=False, **kwargs):
    """Create a workflow state."""
    if not name or not entity_type:
        return {"error": "name and entity_type required"}
    
    db = get_db()
    cursor = db.execute(
        """INSERT INTO workflow_states (name, entity_type, sort_order, is_initial, is_final, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (name, entity_type, sort_order, 1 if is_initial else 0, 1 if is_final else 0, datetime.utcnow().isoformat())
    )
    db.commit()
    
    return {"id": cursor.lastrowid, "name": name, "entity_type": entity_type}


# --- Workflow Transitions ---

@register("core.workflow.transitions.list")
def workflow_transitions_list(entity_type=None, **kwargs):
    """List workflow transitions."""
    db = get_db()
    query = """
        SELECT t.*, 
               s1.name as from_state_name, 
               s2.name as to_state_name
        FROM workflow_transitions t
        JOIN workflow_states s1 ON t.from_state_id = s1.id
        JOIN workflow_states s2 ON t.to_state_id = s2.id
    """
    params = []
    if entity_type:
        query += " WHERE s1.entity_type = ?"
        params.append(entity_type)
    query += " ORDER BY t.created_at"
    
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]


@register("core.workflow.transitions.create")
def workflow_transitions_create(name=None, from_state_id=None, to_state_id=None, condition=None, **kwargs):
    """Create a workflow transition."""
    if not name or not from_state_id or not to_state_id:
        return {"error": "name, from_state_id, to_state_id required"}
    
    db = get_db()
    cursor = db.execute(
        """INSERT INTO workflow_transitions (name, from_state_id, to_state_id, condition_expr, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (name, from_state_id, to_state_id, condition, datetime.utcnow().isoformat())
    )
    db.commit()
    
    return {"id": cursor.lastrowid, "name": name, "from_state_id": from_state_id, "to_state_id": to_state_id}


# --- Workflow History ---

@register("core.workflow.history.list")
def workflow_history_list(entity_type=None, entity_id=None, **kwargs):
    """List workflow history."""
    db = get_db()
    query = """
        SELECT h.*, 
               s1.name as from_state_name, 
               s2.name as to_state_name,
               u.full_name as user_name
        FROM workflow_history h
        JOIN workflow_states s1 ON h.from_state_id = s1.id
        JOIN workflow_states s2 ON h.to_state_id = s2.id
        LEFT JOIN users u ON h.user_id = u.id
    """
    filters = []
    params = []
    if entity_type:
        filters.append("h.entity_type = ?")
        params.append(entity_type)
    if entity_id:
        filters.append("h.entity_id = ?")
        params.append(entity_id)
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY h.created_at DESC LIMIT 100"
    
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]


@register("core.workflow.transition.execute")
def workflow_transition_execute(entity_type=None, entity_id=None, transition_id=None, user_id=None, **kwargs):
    """Execute a workflow transition."""
    if not entity_type or not entity_id or not transition_id:
        return {"error": "entity_type, entity_id, transition_id required"}
    
    db = get_db()
    
    transition = db.execute(
        "SELECT * FROM workflow_transitions WHERE id = ?", (transition_id,)
    ).fetchone()
    if not transition:
        return {"error": "transition not found"}
    
    current = db.execute(
        """SELECT * FROM workflow_entity_states 
           WHERE entity_type = ? AND entity_id = ?""",
        (entity_type, entity_id)
    ).fetchone()
    
    if current and current["state_id"] != transition["from_state_id"]:
        return {"error": f"entity is not in state {transition['from_state_id']}"}
    
    now = datetime.utcnow().isoformat()
    
    if current:
        db.execute(
            "UPDATE workflow_entity_states SET state_id = ?, updated_at = ? WHERE id = ?",
            (transition["to_state_id"], now, current["id"])
        )
    else:
        db.execute(
            "INSERT INTO workflow_entity_states (entity_type, entity_id, state_id, created_at) VALUES (?, ?, ?, ?)",
            (entity_type, entity_id, transition["to_state_id"], now)
        )
    
    db.execute(
        """INSERT INTO workflow_history (entity_type, entity_id, from_state_id, to_state_id, transition_id, user_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (entity_type, entity_id, transition["from_state_id"], transition["to_state_id"], transition_id, user_id, now)
    )
    db.commit()
    
    to_state = db.execute("SELECT name FROM workflow_states WHERE id = ?", (transition["to_state_id"],)).fetchone()
    
    return {
        "success": True,
        "from_state_id": transition["from_state_id"],
        "to_state_id": transition["to_state_id"],
        "to_state_name": to_state["name"] if to_state else "unknown",
    }


# --- Workflow Initialization ---

@register("core.workflow.init_sales_order")
def workflow_init_sales_order(**kwargs):
    """Initialize default workflow for sales orders."""
    db = get_db()
    
    existing = db.execute(
        "SELECT id FROM workflow_states WHERE entity_type = 'sales_order' LIMIT 1"
    ).fetchone()
    if existing:
        return {"message": "already initialized"}
    
    states = [
        ("Borrador", "sales_order", 1, 1, 0),
        ("Confirmado", "sales_order", 2, 0, 0),
        ("Entregado", "sales_order", 3, 0, 0),
        ("Facturado", "sales_order", 4, 0, 1),
        ("Cancelado", "sales_order", 5, 0, 1),
    ]
    
    state_ids = []
    for name, entity, order, is_init, is_final in states:
        cursor = db.execute(
            """INSERT INTO workflow_states (name, entity_type, sort_order, is_initial, is_final, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, entity, order, is_init, is_final, datetime.utcnow().isoformat())
        )
        state_ids.append(cursor.lastrowid)
    
    transitions = [
        ("Confirmar", state_ids[0], state_ids[1], None),
        ("Entregar", state_ids[1], state_ids[2], None),
        ("Facturar", state_ids[2], state_ids[3], None),
        ("Cancelar", state_ids[0], state_ids[4], None),
        ("Cancelar", state_ids[1], state_ids[4], None),
    ]
    
    for name, from_id, to_id, cond in transitions:
        db.execute(
            """INSERT INTO workflow_transitions (name, from_state_id, to_state_id, condition_expr, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (name, from_id, to_id, cond, datetime.utcnow().isoformat())
        )
    
    db.commit()
    return {"message": "sales order workflow initialized", "states": len(states), "transitions": len(transitions)}


# --- Granular Permissions ---

@register("core.permissions.list")
def permissions_list(**kwargs):
    """List all permissions."""
    db = get_db()
    rows = db.execute("SELECT * FROM permissions ORDER BY module, action").fetchall()
    return [dict(r) for r in rows]


@register("core.permissions.create")
def permissions_create(module=None, action=None, field=None, name=None, **kwargs):
    """Create a permission."""
    if not module or not action:
        return {"error": "module and action required"}
    
    db = get_db()
    perm_name = name or f"{module}.{action}{'.' + field if field else ''}"
    
    existing = db.execute(
        "SELECT id FROM permissions WHERE module = ? AND action = ? AND (field = ? OR (field IS NULL AND ? IS NULL))",
        (module, action, field, field)
    ).fetchone()
    
    if existing:
        return {"id": existing["id"], "name": perm_name, "exists": True}
    
    cursor = db.execute(
        "INSERT INTO permissions (name, module, action, field) VALUES (?, ?, ?, ?)",
        (perm_name, module, action, field)
    )
    db.commit()
    
    return {"id": cursor.lastrowid, "name": perm_name}


@register("core.permissions.check")
def permissions_check(user_id=None, module=None, action=None, field=None, **kwargs):
    """Check if a user has a specific permission."""
    if not user_id or not module or not action:
        return {"error": "user_id, module, action required"}
    
    db = get_db()
    
    user = db.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return {"allowed": False, "reason": "user not found"}
    
    if user["role"] == "admin":
        return {"allowed": True, "reason": "admin"}
    
    perm = db.execute(
        """SELECT p.* FROM permissions p
           JOIN user_permissions up ON p.id = up.permission_id
           WHERE up.user_id = ? AND p.module = ? AND p.action = ?
           AND (p.field IS NULL OR p.field = ? OR ? IS NULL)
           LIMIT 1""",
        (user_id, module, action, field, field)
    ).fetchone()
    
    if perm:
        return {"allowed": True, "permission": perm["name"]}
    
    return {"allowed": False, "reason": "no matching permission"}


@register("core.permissions.grant_to_user")
def permissions_grant_to_user(user_id=None, module=None, action=None, field=None, **kwargs):
    """Grant a permission directly to a user."""
    if not user_id or not module or not action:
        return {"error": "user_id, module, action required"}
    
    db = get_db()
    
    perm = db.execute(
        "SELECT id FROM permissions WHERE module = ? AND action = ? AND (field = ? OR (field IS NULL AND ? IS NULL))",
        (module, action, field, field)
    ).fetchone()
    
    if not perm:
        cursor = db.execute(
            "INSERT INTO permissions (name, module, action, field) VALUES (?, ?, ?, ?)",
            (f"{module}.{action}.{field}" if field else f"{module}.{action}", module, action, field)
        )
        perm_id = cursor.lastrowid
    else:
        perm_id = perm["id"]
    
    existing = db.execute(
        "SELECT id FROM user_permissions WHERE user_id = ? AND permission_id = ?",
        (user_id, perm_id)
    ).fetchone()
    
    if not existing:
        db.execute(
            "INSERT INTO user_permissions (user_id, permission_id) VALUES (?, ?)",
            (user_id, perm_id)
        )
        db.commit()
    
    return {"granted": True}


@register("core.permissions.revoke_from_user")
def permissions_revoke_from_user(user_id=None, module=None, action=None, field=None, **kwargs):
    """Revoke a permission from a user."""
    if not user_id or not module or not action:
        return {"error": "user_id, module, action required"}
    
    db = get_db()
    
    perm = db.execute(
        "SELECT id FROM permissions WHERE module = ? AND action = ? AND (field = ? OR (field IS NULL AND ? IS NULL))",
        (module, action, field, field)
    ).fetchone()
    
    if perm:
        db.execute(
            "DELETE FROM user_permissions WHERE user_id = ? AND permission_id = ?",
            (user_id, perm["id"])
        )
        db.commit()
    
    return {"revoked": True}


@register("core.permissions.seed")
def permissions_seed(**kwargs):
    """Seed default permissions."""
    db = get_db()
    
    if db.execute("SELECT COUNT(*) FROM permissions").fetchone()[0] > 0:
        return {"message": "permissions already seeded"}
    
    perms = [
        ("product.list", "product", "list", None),
        ("product.create", "product", "create", None),
        ("product.update", "product", "update", None),
        ("product.delete", "product", "delete", None),
        ("sales_order.list", "sales_order", "list", None),
        ("sales_order.create", "sales_order", "create", None),
        ("sales_order.confirm", "sales_order", "confirm", None),
        ("sales_order.deliver", "sales_order", "deliver", None),
        ("sales_order.invoice", "sales_order", "invoice", None),
        ("sales_order.cancel", "sales_order", "cancel", None),
        ("inventory.list", "inventory", "list", None),
        ("inventory.transfer", "inventory", "transfer", None),
        ("inventory.adjust", "inventory", "adjust", None),
        ("lead.list", "lead", "list", None),
        ("lead.create", "lead", "create", None),
        ("opportunity.list", "opportunity", "list", None),
        ("opportunity.create", "opportunity", "create", None),
        ("accounting.view", "accounting", "view", None),
        ("journal.create", "journal", "create", None),
        ("user.manage", "user", "manage", None),
        ("company.manage", "company", "manage", None),
    ]
    
    for name, module, action, field in perms:
        db.execute(
            "INSERT INTO permissions (name, module, action, field) VALUES (?, ?, ?, ?)",
            (name, module, action, field)
        )
    
    db.commit()
    return {"seeded": len(perms)}
