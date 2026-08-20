"""Regression tests for bugs actually found in production code.

Every test here maps to a real defect that shipped and was fixed. They exist
so the same class of bug cannot come back silently.
"""
import pytest


class TestJournalListSelect:
    """accounting.journal.list had a query starting at 'je.*' with no SELECT,
    so any read of the ledger failed with 'near "je": syntax error'."""

    def test_journal_list_executes(self, seed_accounting):
        from core.accounting import journal_list
        result = journal_list()
        assert not isinstance(result, dict) or "error" not in result, result
        assert isinstance(result, list)

    def test_journal_list_returns_created_entry(self, seed_accounting):
        from core.accounting import journal_create, journal_list
        created = journal_create(
            description="Asiento de prueba",
            date="2026-08-15",
            lines=[{"account_id": 1, "debit": 0, "credit": 500},
                   {"account_id": 2, "debit": 500, "credit": 0}],
        )
        assert "error" not in created, created

        entries = journal_list()
        assert len(entries) == 1
        entry = entries[0]
        assert entry["description"] == "Asiento de prueba"
        # The list must expose the totals the UI reads
        assert float(entry["debit_total"]) == 500.0
        assert float(entry["credit_total"]) == 500.0
        assert len(entry["lines"]) == 2

    def test_journal_list_date_filters_work(self, seed_accounting):
        from core.accounting import journal_create, journal_list
        for d in ("2026-01-10", "2026-06-10"):
            journal_create(description=f"E {d}", date=d,
                           lines=[{"account_id": 1, "debit": 100, "credit": 0},
                                  {"account_id": 2, "debit": 0, "credit": 100}])
        assert len(journal_list()) == 2
        assert len(journal_list(from_date="2026-05-01")) == 1
        assert len(journal_list(to_date="2026-03-01")) == 1


class TestRfqQuantityNotSilentlyDefaulted:
    """rfq.create used float(l.get("qty", 1)) and silently dropped the real
    quantity: asking for 10 units produced a purchase order for 1."""

    def test_qty_is_respected(self, seed_commercial, make_product, db_conn):
        from core.purchasing_rfq import rfq_create
        pid = make_product()
        r = rfq_create(lines=[{"producto_id": pid, "qty": 10}])
        assert "error" not in r, r

        row = db_conn.execute(
            "SELECT qty FROM rfq_lines WHERE rfq_id = ?", (r["id"],)).fetchone()
        assert float(row["qty"]) == 10.0, "the requested quantity must be stored as-is"

    def test_quantity_alias_is_accepted(self, seed_commercial, make_product, db_conn):
        from core.purchasing_rfq import rfq_create
        pid = make_product()
        r = rfq_create(lines=[{"producto_id": pid, "quantity": 7}])
        assert "error" not in r, r
        row = db_conn.execute(
            "SELECT qty FROM rfq_lines WHERE rfq_id = ?", (r["id"],)).fetchone()
        assert float(row["qty"]) == 7.0

    def test_missing_qty_is_an_error_not_a_default_of_one(self, seed_commercial, make_product):
        from core.purchasing_rfq import rfq_create
        pid = make_product()
        r = rfq_create(lines=[{"producto_id": pid}])
        assert "error" in r, "a missing qty must fail loudly, not default to 1"

    def test_zero_qty_rejected(self, seed_commercial, make_product):
        from core.purchasing_rfq import rfq_create
        pid = make_product()
        r = rfq_create(lines=[{"producto_id": pid, "qty": 0}])
        assert "error" in r

    def test_awarded_order_carries_the_real_quantity(self, seed_commercial, make_product):
        """End-to-end: the bug surfaced as a PO for 1 unit instead of 10."""
        from core.purchasing_rfq import rfq_create, rfq_quotes_add, rfq_award
        from core.purchasing_suppliers import suppliers_create
        pid = make_product()
        sup = suppliers_create(name="Proveedor", country="MX")
        rfq = rfq_create(lines=[{"producto_id": pid, "qty": 10}])
        quote = rfq_quotes_add(
            rfq_id=rfq["id"], supplier_id=sup["id"],
            lines=[{"producto_id": pid, "qty": 10, "unit_price": 140}],
        )
        assert float(quote["total"]) == 1400.0, "10 x 140 must be 1400, not 140"

        award = rfq_award(quote_id=quote["quote_id"])
        assert "error" not in award, award
        assert float(award["total"]) == 1400.0

        from core.purchasing_receipts import receipts_pending
        pending = receipts_pending(purchase_order_id=award["purchase_order_id"])
        assert float(pending["lines"][0]["ordered"]) == 10.0


class TestBaseModelIgnoresUnknownKeys:
    """BaseModel.create/update inserted any key blindly, so a transport extra
    such as _path or token crashed the INSERT."""

    def test_create_drops_unknown_keys(self):
        from core.main import Producto
        result = Producto.create(
            codigo="OK-1", nombre="Producto", precio_unitario=50,
            _path="/api/productos", _method="POST", token="abc123",
        )
        assert "error" not in result, result
        assert result["codigo"] == "OK-1"

    def test_update_drops_unknown_keys(self):
        from core.main import Producto
        created = Producto.create(codigo="OK-2", nombre="Antes", precio_unitario=10)
        updated = Producto.update(created["id"], nombre="Despues", token="xyz")
        assert "error" not in updated, updated
        assert updated["nombre"] == "Despues"

    def test_create_with_only_unknown_keys_errors(self):
        from core.main import Producto
        result = Producto.create(token="abc", _path="/x")
        assert "error" in result


class TestTokenReachesSelfAuthenticatingHandlers:
    """Filtering `token` as an internal param broke auth.users.*, which
    receives it as a real argument and returned 'not authenticated'."""

    def test_dispatch_passes_token_when_declared(self):
        import inspect
        from core.auth_handlers import auth_users_list
        sig = inspect.signature(auth_users_list)
        assert "token" in sig.parameters, (
            "auth.users.list must accept token; the dispatcher decides by signature")

    def test_dispatcher_keeps_token_for_declaring_handlers(self):
        """Mirror the dispatcher logic in core.main.handle_request."""
        import inspect

        def declares_token(token=None, other=None):
            return {"got_token": token}

        def no_token(other=None):
            return {"ok": True}

        def kwargs_only(**kwargs):
            return {"got_token": kwargs.get("token")}

        def decide(fn, args):
            filtered = dict(args)
            if "token" in filtered:
                sig = inspect.signature(fn)
                accepts = "token" in sig.parameters or any(
                    p.kind is inspect.Parameter.VAR_KEYWORD
                    for p in sig.parameters.values())
                if not accepts:
                    filtered.pop("token")
            return filtered

        assert decide(declares_token, {"token": "t"}) == {"token": "t"}
        assert decide(kwargs_only, {"token": "t"}) == {"token": "t"}
        assert decide(no_token, {"token": "t"}) == {}


class TestStockMovementSchemaMatch:
    """Purchasing wrote stock movements with columns that do not exist
    (warehouse_id / movement_type) instead of the real schema."""

    def test_movement_columns_are_the_real_ones(self, db_conn):
        cols = {r[1] for r in db_conn.execute("PRAGMA table_info(stock_movements)")}
        assert {"from_warehouse_id", "to_warehouse_id", "type"} <= cols

    def test_receipt_writes_a_valid_movement(self, seed_commercial, make_product,
                                             make_warehouse, db_conn):
        from core.purchasing_suppliers import suppliers_create
        from core.purchasing_rfq import rfq_create, rfq_quotes_add, rfq_award
        from core.purchasing_receipts import receipts_create
        pid = make_product()
        wid = make_warehouse()
        sup = suppliers_create(name="Prov", country="MX")
        rfq = rfq_create(lines=[{"producto_id": pid, "qty": 5}])
        quote = rfq_quotes_add(rfq_id=rfq["id"], supplier_id=sup["id"],
                              lines=[{"producto_id": pid, "qty": 5, "unit_price": 20}])
        award = rfq_award(quote_id=quote["quote_id"])

        result = receipts_create(
            purchase_order_id=award["purchase_order_id"], warehouse_id=wid,
            lines=[{"producto_id": pid, "qty_received": 5}],
        )
        assert "error" not in result, result

        row = db_conn.execute(
            "SELECT type, to_warehouse_id, quantity FROM stock_movements "
            "ORDER BY id DESC LIMIT 1").fetchone()
        assert row["type"] == "purchase"
        assert row["to_warehouse_id"] == wid
        assert float(row["quantity"]) == 5.0


class TestPurchaseOrderPartialStatus:
    """purchase_orders.status had a CHECK constraint that rejected
    'partially_received', so partial receipts failed."""

    def test_partially_received_is_allowed(self, seed_commercial, make_product,
                                           make_warehouse):
        from core.purchasing_suppliers import suppliers_create
        from core.purchasing_rfq import rfq_create, rfq_quotes_add, rfq_award
        from core.purchasing_receipts import receipts_create
        pid = make_product()
        wid = make_warehouse()
        sup = suppliers_create(name="Prov", country="MX")
        rfq = rfq_create(lines=[{"producto_id": pid, "qty": 100}])
        quote = rfq_quotes_add(rfq_id=rfq["id"], supplier_id=sup["id"],
                             lines=[{"producto_id": pid, "qty": 100, "unit_price": 10}])
        award = rfq_award(quote_id=quote["quote_id"])

        partial = receipts_create(
            purchase_order_id=award["purchase_order_id"], warehouse_id=wid,
            lines=[{"producto_id": pid, "qty_received": 40}],
        )
        assert "error" not in partial, partial
        assert partial["purchase_order_status"] == "partially_received"

        rest = receipts_create(
            purchase_order_id=award["purchase_order_id"], warehouse_id=wid,
            lines=[{"producto_id": pid, "qty_received": 60}],
        )
        assert rest["purchase_order_status"] == "received"

    def test_over_receipt_rejected(self, seed_commercial, make_product, make_warehouse):
        from core.purchasing_suppliers import suppliers_create
        from core.purchasing_rfq import rfq_create, rfq_quotes_add, rfq_award
        from core.purchasing_receipts import receipts_create
        pid = make_product()
        wid = make_warehouse()
        sup = suppliers_create(name="Prov", country="MX")
        rfq = rfq_create(lines=[{"producto_id": pid, "qty": 10}])
        quote = rfq_quotes_add(rfq_id=rfq["id"], supplier_id=sup["id"],
                             lines=[{"producto_id": pid, "qty": 10, "unit_price": 10}])
        award = rfq_award(quote_id=quote["quote_id"])
        result = receipts_create(
            purchase_order_id=award["purchase_order_id"], warehouse_id=wid,
            lines=[{"producto_id": pid, "qty_received": 999}],
        )
        assert "error" in result


class TestHandlersAreReachable:
    """Several handlers existed in Python with no Go route, so they were
    unreachable from outside (accounting core, users management)."""

    ROUTES_FILE = "app/web/main.go"

    def _routes(self):
        import os
        path = os.path.join(os.path.dirname(__file__), "..", self.ROUTES_FILE)
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    @pytest.mark.parametrize("handler", [
        "core.accounting.accounts.list",
        "core.accounting.accounts.create",
        "core.accounting.journal.list",
        "core.accounting.journal.create",
        "core.accounting.trial_balance",
        "core.accounting.income_statement",
        "core.accounting.balance_sheet",
        "core.auth.users.list",
        "core.auth.users.create",
    ])
    def test_handler_has_a_route(self, handler):
        assert handler in self._routes(), f"{handler} has no HTTP route"
