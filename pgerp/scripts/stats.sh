#!/usr/bin/env bash
# Print current PyGo ERP totals (handlers, routes, migrations, modules)
cd /home/hermesuser/pygo-erp/pgerp || exit 1
echo "handlers:   $(grep -rho '@register("[^"]*"' app/core/ app/modules/ | wc -l)"
echo "go routes:  $(grep -c 'r.Handle(' app/web/main.go)"
python3 - <<'PY'
import sqlite3
c = sqlite3.connect('/tmp/pgerp.db')
def q(sql):
    try:
        return c.execute(sql).fetchone()[0]
    except Exception:
        return 'n/a'
print("core migrations:  ", q("SELECT COUNT(*) FROM _migrations"))
print("module migrations:", q("SELECT COUNT(*) FROM module_migrations"))
print("taxes:            ", q("SELECT COUNT(*) FROM taxes"))
print("modules:          ", q("SELECT COUNT(*) FROM modules"))
print("installed modules:", q("SELECT COUNT(*) FROM modules WHERE state='installed'"))
print("hooks active:     ", q("SELECT COUNT(*) FROM module_hooks WHERE is_active=1"))
PY
