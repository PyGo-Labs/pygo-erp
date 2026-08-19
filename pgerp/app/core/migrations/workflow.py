"""PyGo ERP V2.0 — Migrations for Workflow + Permissions."""
from core.orm.migrations import Migration, migration


@migration("024_create_workflow_states")
class CreateWorkflowStates(Migration):
    def up(self, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workflow_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                is_initial INTEGER DEFAULT 0,
                is_final INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    
    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS workflow_states")
        conn.commit()


@migration("025_create_workflow_transitions")
class CreateWorkflowTransitions(Migration):
    def up(self, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workflow_transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                from_state_id INTEGER NOT NULL,
                to_state_id INTEGER NOT NULL,
                condition_expr TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    
    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS workflow_transitions")
        conn.commit()


@migration("026_create_workflow_entity_states")
class CreateWorkflowEntityStates(Migration):
    def up(self, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workflow_entity_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                state_id INTEGER NOT NULL,
                updated_at TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(entity_type, entity_id)
            )
        """)
        conn.commit()
    
    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS workflow_entity_states")
        conn.commit()


@migration("027_create_workflow_history")
class CreateWorkflowHistory(Migration):
    def up(self, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workflow_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                from_state_id INTEGER NOT NULL,
                to_state_id INTEGER NOT NULL,
                transition_id INTEGER,
                user_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    
    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS workflow_history")
        conn.commit()


@migration("028_create_permissions")
class CreatePermissions(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                module TEXT NOT NULL,
                action TEXT NOT NULL,
                field TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS user_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                permission_id INTEGER NOT NULL,
                UNIQUE(user_id, permission_id)
            );
        """)
        conn.commit()
    
    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS permissions;
            DROP TABLE IF EXISTS user_permissions;
        """)
        conn.commit()


@migration("029_seed_permissions")
class SeedPermissions(Migration):
    def up(self, conn):
        if conn.execute("SELECT COUNT(*) FROM permissions").fetchone()[0] > 0:
            return
        
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
            conn.execute(
                "INSERT INTO permissions (name, module, action, field) VALUES (?, ?, ?, ?)",
                (name, module, action, field)
            )
        conn.commit()
    
    def down(self, conn):
        conn.execute("DELETE FROM permissions")
        conn.commit()
