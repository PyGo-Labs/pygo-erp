"""PyGo ERP — Relax purchase_orders.status CHECK to allow partial receipts.

SQLite cannot ALTER a CHECK constraint, so the table is rebuilt preserving
whatever columns actually exist (schema has drifted across migrations).
"""
from core.orm.migrations import Migration, migration


@migration("040_relax_po_status_check")
class RelaxPoStatusCheck(Migration):
    def up(self, conn):
        info = conn.execute("PRAGMA table_info(purchase_orders)").fetchall()
        if not info:
            return

        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='purchase_orders'"
        ).fetchone()
        current_sql = (row[0] or "") if row else ""

        # Already permissive -> nothing to do
        if "partially_received" in current_sql:
            return

        # Rebuild using the real column list, dropping the CHECK on status
        defs = []
        names = []
        for c in info:
            cname = c[1]
            ctype = c[2] or "TEXT"
            names.append(cname)
            if cname == "id":
                defs.append("id INTEGER PRIMARY KEY AUTOINCREMENT")
            elif cname == "status":
                defs.append(
                    "status TEXT DEFAULT 'draft' CHECK (status IN "
                    "('draft','confirmed','partially_received','received','cancelled'))"
                )
            elif cname == "created_at":
                defs.append("created_at TEXT DEFAULT (datetime('now'))")
            else:
                default = ""
                if ctype.upper() in ("REAL", "INTEGER") and c[4] is not None:
                    default = f" DEFAULT {c[4]}"
                elif c[4] is not None:
                    default = f" DEFAULT {c[4]}"
                defs.append(f"{cname} {ctype}{default}")

        collist = ", ".join(names)
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute(f"CREATE TABLE purchase_orders_new ({', '.join(defs)})")
        conn.execute(
            f"INSERT INTO purchase_orders_new ({collist}) SELECT {collist} FROM purchase_orders"
        )
        conn.execute("DROP TABLE purchase_orders")
        conn.execute("ALTER TABLE purchase_orders_new RENAME TO purchase_orders")
        conn.execute("PRAGMA foreign_keys=ON")

    def down(self, conn):
        pass
