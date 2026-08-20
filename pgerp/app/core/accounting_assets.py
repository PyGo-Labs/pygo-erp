"""PyGo ERP — Fixed assets with depreciation (straight line / declining balance)."""
import os
import sys
from datetime import datetime

base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, base)
sys.path.insert(0, os.path.join(base, "app"))

from core.registry import register


def get_db():
    import sqlite3
    conn = sqlite3.connect(os.environ.get("PYGO_DB", "/tmp/pgerp.db"), timeout=15.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=15000")
    except Exception:
        pass
    return conn


def _add_months(dt, months):
    y = dt.year + (dt.month - 1 + months) // 12
    m = (dt.month - 1 + months) % 12 + 1
    return dt.replace(year=y, month=m, day=1)


@register("core.assets.list")
def assets_list(status=None, **kwargs):
    db = get_db()
    if status:
        rows = db.execute("SELECT * FROM fixed_assets WHERE status = ? ORDER BY id DESC", (status,)).fetchall()
    else:
        rows = db.execute("SELECT * FROM fixed_assets ORDER BY id DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["book_value"] = round(
            float(r["acquisition_cost"] or 0) - float(r["accumulated_depreciation"] or 0), 2
        )
        out.append(d)
    return out


@register("core.assets.create")
def assets_create(
    name=None, code=None, category=None, acquisition_date=None,
    acquisition_cost=None, salvage_value=0, useful_life_months=60,
    method="straight_line", cost_center_id=None, company_id=None, **kwargs
):
    if not name or acquisition_cost is None:
        return {"error": "name and acquisition_cost required"}
    try:
        cost = float(acquisition_cost)
        salvage = float(salvage_value or 0)
        life = int(useful_life_months or 60)
    except (TypeError, ValueError):
        return {"error": "numeric fields invalid"}
    if cost <= 0:
        return {"error": "acquisition_cost must be > 0"}
    if life <= 0:
        return {"error": "useful_life_months must be > 0"}
    if salvage >= cost:
        return {"error": "salvage_value must be < acquisition_cost"}
    if method not in ("straight_line", "declining_balance"):
        return {"error": "method must be straight_line|declining_balance"}

    db = get_db()
    acq = acquisition_date or datetime.utcnow().strftime("%Y-%m-%d")
    cur = db.execute(
        "INSERT INTO fixed_assets (code, name, category, acquisition_date, acquisition_cost, "
        "salvage_value, useful_life_months, method, cost_center_id, company_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (code, name, category, acq, cost, salvage, life, method, cost_center_id, company_id),
    )
    db.commit()
    monthly = (cost - salvage) / life
    return {
        "id": cur.lastrowid, "name": name, "acquisition_cost": cost,
        "useful_life_months": life, "method": method,
        "monthly_depreciation": round(monthly, 2),
    }


@register("core.assets.schedule")
def assets_schedule(asset_id=None, **kwargs):
    """Full depreciation schedule for an asset (computed, not posted)."""
    if not asset_id:
        return {"error": "asset_id required"}
    db = get_db()
    a = db.execute("SELECT * FROM fixed_assets WHERE id = ?", (asset_id,)).fetchone()
    if not a:
        return {"error": "asset not found"}

    cost = float(a["acquisition_cost"] or 0)
    salvage = float(a["salvage_value"] or 0)
    life = int(a["useful_life_months"] or 60)
    depreciable = cost - salvage

    try:
        start = datetime.strptime(str(a["acquisition_date"])[:10], "%Y-%m-%d")
    except Exception:
        start = datetime.utcnow()

    schedule = []
    accumulated = 0.0
    if a["method"] == "declining_balance":
        rate = 2.0 / life  # double declining
        book = cost
        for i in range(life):
            amount = book * rate
            if accumulated + amount > depreciable:
                amount = depreciable - accumulated
            if amount <= 0:
                break
            accumulated += amount
            book = cost - accumulated
            schedule.append({
                "period": _add_months(start, i).strftime("%Y-%m"),
                "amount": round(amount, 2),
                "accumulated": round(accumulated, 2),
                "book_value": round(book, 2),
            })
    else:
        monthly = depreciable / life
        for i in range(life):
            amount = monthly
            if accumulated + amount > depreciable:
                amount = depreciable - accumulated
            accumulated += amount
            schedule.append({
                "period": _add_months(start, i).strftime("%Y-%m"),
                "amount": round(amount, 2),
                "accumulated": round(accumulated, 2),
                "book_value": round(cost - accumulated, 2),
            })

    return {
        "asset_id": asset_id,
        "asset": a["name"],
        "method": a["method"],
        "acquisition_cost": cost,
        "salvage_value": salvage,
        "useful_life_months": life,
        "total_depreciable": round(depreciable, 2),
        "periods": len(schedule),
        "schedule": schedule,
    }


@register("core.assets.depreciate")
def assets_depreciate(asset_id=None, period=None, **kwargs):
    """Post one depreciation period for an asset."""
    if not asset_id:
        return {"error": "asset_id required"}
    db = get_db()
    a = db.execute("SELECT * FROM fixed_assets WHERE id = ?", (asset_id,)).fetchone()
    if not a:
        return {"error": "asset not found"}
    if a["status"] != "active":
        return {"error": f"asset is {a['status']}"}

    period = period or datetime.utcnow().strftime("%Y-%m")
    if db.execute(
        "SELECT 1 FROM depreciation_entries WHERE asset_id = ? AND period = ?",
        (asset_id, period),
    ).fetchone():
        return {"error": f"period {period} already depreciated"}

    cost = float(a["acquisition_cost"] or 0)
    salvage = float(a["salvage_value"] or 0)
    life = int(a["useful_life_months"] or 60)
    accumulated = float(a["accumulated_depreciation"] or 0)
    depreciable = cost - salvage
    remaining = depreciable - accumulated

    if remaining <= 0.01:
        db.execute("UPDATE fixed_assets SET status = 'fully_depreciated' WHERE id = ?", (asset_id,))
        db.commit()
        return {"error": "asset fully depreciated", "asset_id": asset_id}

    if a["method"] == "declining_balance":
        amount = (cost - accumulated) * (2.0 / life)
    else:
        amount = depreciable / life
    amount = min(amount, remaining)

    new_acc = accumulated + amount
    book = cost - new_acc

    try:
        cur = db.execute(
            "INSERT INTO depreciation_entries (asset_id, period, amount, accumulated, book_value, posted) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (asset_id, period, round(amount, 2), round(new_acc, 2), round(book, 2)),
        )
        db.execute(
            "UPDATE fixed_assets SET accumulated_depreciation = ? WHERE id = ?",
            (round(new_acc, 2), asset_id),
        )
        if book <= salvage + 0.01:
            db.execute("UPDATE fixed_assets SET status = 'fully_depreciated' WHERE id = ?", (asset_id,))

        # analytic line if the asset has a cost center
        if a["cost_center_id"]:
            db.execute(
                "INSERT INTO analytic_lines (cost_center_id, amount, entry_date, description) "
                "VALUES (?, ?, ?, ?)",
                (a["cost_center_id"], round(amount, 2), f"{period}-01",
                 f"Depreciation {a['name']} {period}"),
            )
        db.commit()
    except Exception as e:
        db.rollback()
        return {"error": f"depreciation failed: {e}"}
    finally:
        db.close()

    return {
        "entry_id": cur.lastrowid,
        "asset_id": asset_id,
        "asset": a["name"],
        "period": period,
        "amount": round(amount, 2),
        "accumulated": round(new_acc, 2),
        "book_value": round(book, 2),
    }


@register("core.assets.dispose")
def assets_dispose(asset_id=None, disposal_amount=0, disposal_date=None, **kwargs):
    """Dispose of an asset and compute gain/loss."""
    if not asset_id:
        return {"error": "asset_id required"}
    try:
        proceeds = float(disposal_amount or 0)
    except (TypeError, ValueError):
        return {"error": "disposal_amount must be numeric"}

    db = get_db()
    a = db.execute("SELECT * FROM fixed_assets WHERE id = ?", (asset_id,)).fetchone()
    if not a:
        return {"error": "asset not found"}
    if a["status"] == "disposed":
        return {"error": "asset already disposed"}

    cost = float(a["acquisition_cost"] or 0)
    accumulated = float(a["accumulated_depreciation"] or 0)
    book = cost - accumulated
    gain_loss = proceeds - book

    db.execute(
        "UPDATE fixed_assets SET status = 'disposed', disposal_date = ?, disposal_amount = ? WHERE id = ?",
        (disposal_date or datetime.utcnow().strftime("%Y-%m-%d"), proceeds, asset_id),
    )
    db.commit()
    return {
        "asset_id": asset_id,
        "asset": a["name"],
        "acquisition_cost": cost,
        "accumulated_depreciation": round(accumulated, 2),
        "book_value": round(book, 2),
        "disposal_amount": proceeds,
        "gain_loss": round(gain_loss, 2),
        "result": "gain" if gain_loss > 0 else ("loss" if gain_loss < 0 else "break_even"),
    }


@register("core.assets.summary")
def assets_summary(**kwargs):
    """Fixed assets register summary."""
    db = get_db()
    rows = db.execute("SELECT * FROM fixed_assets").fetchall()
    total_cost = sum(float(r["acquisition_cost"] or 0) for r in rows)
    total_dep = sum(float(r["accumulated_depreciation"] or 0) for r in rows)
    by_cat = {}
    for r in rows:
        cat = r["category"] or "Uncategorized"
        if cat not in by_cat:
            by_cat[cat] = {"count": 0, "cost": 0.0, "accumulated": 0.0, "book_value": 0.0}
        by_cat[cat]["count"] += 1
        by_cat[cat]["cost"] += float(r["acquisition_cost"] or 0)
        by_cat[cat]["accumulated"] += float(r["accumulated_depreciation"] or 0)
        by_cat[cat]["book_value"] = round(by_cat[cat]["cost"] - by_cat[cat]["accumulated"], 2)
    for v in by_cat.values():
        v["cost"] = round(v["cost"], 2)
        v["accumulated"] = round(v["accumulated"], 2)
    return {
        "total_assets": len(rows),
        "by_status": {
            s: sum(1 for r in rows if r["status"] == s)
            for s in ("active", "fully_depreciated", "disposed")
        },
        "total_acquisition_cost": round(total_cost, 2),
        "total_accumulated_depreciation": round(total_dep, 2),
        "total_book_value": round(total_cost - total_dep, 2),
        "by_category": by_cat,
    }
