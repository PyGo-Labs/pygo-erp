"""Tests for D3 credit limits and line discounts."""
import pytest


@pytest.fixture
def customer(db_conn):
    db_conn.execute("INSERT INTO clientes (nombre, email) VALUES ('Cliente', 'c@x.com')")
    db_conn.commit()
    return 1


@pytest.fixture
def stocked(make_product, make_warehouse, make_stock):
    pid, wid = make_product("D3-1", "Producto", 100, 60), make_warehouse()
    make_stock(pid, wid, 500)
    return {"producto_id": pid, "warehouse_id": wid}


class TestCreditLimitConfig:
    def test_requires_customer(self):
        from core.credit import credit_set_limit
        assert "error" in credit_set_limit(credit_limit=1000)

    def test_requires_something_to_set(self, customer):
        from core.credit import credit_set_limit
        assert "error" in credit_set_limit(cliente_id=customer)

    def test_negative_limit_rejected(self, customer):
        from core.credit import credit_set_limit
        assert "error" in credit_set_limit(cliente_id=customer, credit_limit=-5)

    def test_unknown_customer_rejected(self):
        from core.credit import credit_set_limit
        assert "error" in credit_set_limit(cliente_id=9999, credit_limit=100)

    def test_limit_is_stored(self, customer):
        from core.credit import credit_set_limit
        r = credit_set_limit(cliente_id=customer, credit_limit=2000)
        assert r["credit_limit"] == 2000.0
        assert r["credit_hold"] is False

    def test_hold_is_stored(self, customer):
        from core.credit import credit_set_limit
        r = credit_set_limit(cliente_id=customer, credit_hold=1)
        assert r["credit_hold"] is True


class TestCreditExposure:
    def test_zero_exposure_on_a_new_customer(self, customer):
        from core.credit import credit_exposure
        e = credit_exposure(cliente_id=customer)
        assert e["exposure"] == 0.0
        assert e["open_invoices"] == 0.0
        assert e["pending_orders"] == 0.0

    def test_unpaid_invoice_counts(self, customer, db_conn):
        from core.credit import credit_exposure
        db_conn.execute(
            "INSERT INTO facturas (cliente_id, total, amount_paid) VALUES (?, 1000, 300)",
            (customer,))
        db_conn.commit()
        e = credit_exposure(cliente_id=customer)
        assert e["open_invoices"] == 700.0
        assert e["exposure"] == 700.0

    def test_confirmed_order_counts_as_commitment(self, seed_commercial, customer,
                                                  stocked):
        from core.sales import sales_orders_create, sales_orders_confirm
        from core.credit import credit_exposure
        order = sales_orders_create(cliente_id=customer, items=[
            {"producto_id": stocked["producto_id"], "quantity": 5, "price": 100}])
        sales_orders_confirm(order_id=order["id"])
        e = credit_exposure(cliente_id=customer)
        assert e["pending_orders"] == 580.0, "500 + 16% tax"

    def test_draft_order_does_not_count(self, seed_commercial, customer, stocked):
        from core.sales import sales_orders_create
        from core.credit import credit_exposure
        sales_orders_create(cliente_id=customer, items=[
            {"producto_id": stocked["producto_id"], "quantity": 5, "price": 100}])
        assert credit_exposure(cliente_id=customer)["pending_orders"] == 0.0

    def test_utilisation_is_reported(self, customer, db_conn):
        from core.credit import credit_set_limit, credit_exposure
        credit_set_limit(cliente_id=customer, credit_limit=2000)
        db_conn.execute(
            "INSERT INTO facturas (cliente_id, total, amount_paid) VALUES (?, 500, 0)",
            (customer,))
        db_conn.commit()
        e = credit_exposure(cliente_id=customer)
        assert e["available"] == 1500.0
        assert e["utilisation_pct"] == 25.0

    def test_open_credit_note_reduces_exposure(self, customer, db_conn):
        from core.credit import credit_exposure
        db_conn.execute(
            "INSERT INTO facturas (cliente_id, total, amount_paid) VALUES (?, 1000, 0)",
            (customer,))
        db_conn.execute(
            "INSERT INTO credit_notes (cliente_id, amount, applied_amount, status) "
            "VALUES (?, 400, 0, 'open')", (customer,))
        db_conn.commit()
        e = credit_exposure(cliente_id=customer)
        assert e["open_credit_notes"] == 400.0
        assert e["exposure"] == 600.0

    def test_portfolio_flags_customers_over_limit(self, customer, db_conn):
        from core.credit import credit_set_limit, credit_exposure
        credit_set_limit(cliente_id=customer, credit_limit=500)
        db_conn.execute(
            "INSERT INTO facturas (cliente_id, total, amount_paid) VALUES (?, 900, 0)",
            (customer,))
        db_conn.commit()
        portfolio = credit_exposure()
        assert portfolio["over_limit_count"] == 1
        target = next(c for c in portfolio["customers"] if c["cliente_id"] == customer)
        assert target["over_limit"] is True


class TestCreditCheck:
    def test_requires_customer(self):
        from core.credit import credit_check
        assert "error" in credit_check(amount=100)

    def test_no_limit_means_unlimited(self, customer):
        """Existing installs must not break just because the field appeared."""
        from core.credit import credit_check
        r = credit_check(cliente_id=customer, amount=999999)
        assert r["allowed"] is True
        assert r["reason"] == "no credit limit set"

    def test_within_limit_allowed(self, customer):
        from core.credit import credit_set_limit, credit_check
        credit_set_limit(cliente_id=customer, credit_limit=2000)
        r = credit_check(cliente_id=customer, amount=500)
        assert r["allowed"] is True
        assert r["available"] == 2000.0
        assert r["projected"] == 500.0

    def test_over_limit_refused_with_numbers(self, customer, db_conn):
        from core.credit import credit_set_limit, credit_check
        credit_set_limit(cliente_id=customer, credit_limit=2000)
        db_conn.execute(
            "INSERT INTO facturas (cliente_id, total, amount_paid) VALUES (?, 1500, 0)",
            (customer,))
        db_conn.commit()
        r = credit_check(cliente_id=customer, amount=1000)
        assert r["allowed"] is False
        assert r["exposure"] == 1500.0
        assert r["projected"] == 2500.0
        assert r["over_by"] == 500.0

    def test_exactly_at_the_limit_is_allowed(self, customer):
        from core.credit import credit_set_limit, credit_check
        credit_set_limit(cliente_id=customer, credit_limit=1000)
        assert credit_check(cliente_id=customer, amount=1000)["allowed"] is True

    def test_hold_refuses_everything(self, customer):
        from core.credit import credit_set_limit, credit_check
        credit_set_limit(cliente_id=customer, credit_limit=100000)
        credit_set_limit(cliente_id=customer, credit_hold=1)
        r = credit_check(cliente_id=customer, amount=1)
        assert r["allowed"] is False
        assert "hold" in r["reason"]


class TestCreditBlocksOrders:
    def test_order_over_limit_is_refused(self, seed_commercial, customer, stocked):
        """The check has to bite in the real document, not just in an endpoint."""
        from core.credit import credit_set_limit
        from core.sales import sales_orders_create
        credit_set_limit(cliente_id=customer, credit_limit=2000)
        r = sales_orders_create(cliente_id=customer, items=[
            {"producto_id": stocked["producto_id"], "quantity": 50, "price": 100}])
        assert "error" in r
        assert "credit limit exceeded" in r["error"]
        assert r["credit"]["over_by"] > 0

    def test_order_within_limit_succeeds(self, seed_commercial, customer, stocked):
        from core.credit import credit_set_limit
        from core.sales import sales_orders_create
        credit_set_limit(cliente_id=customer, credit_limit=50000)
        r = sales_orders_create(cliente_id=customer, items=[
            {"producto_id": stocked["producto_id"], "quantity": 50, "price": 100}])
        assert "error" not in r, r

    def test_hold_blocks_any_order(self, seed_commercial, customer, stocked):
        from core.credit import credit_set_limit
        from core.sales import sales_orders_create
        credit_set_limit(cliente_id=customer, credit_hold=1)
        r = sales_orders_create(cliente_id=customer, items=[
            {"producto_id": stocked["producto_id"], "quantity": 1, "price": 100}])
        assert "error" in r
        assert "hold" in r["error"]

    def test_blocked_attempt_is_audited(self, seed_commercial, customer, stocked):
        from core.credit import credit_set_limit, credit_events
        from core.sales import sales_orders_create
        credit_set_limit(cliente_id=customer, credit_limit=100)
        sales_orders_create(cliente_id=customer, items=[
            {"producto_id": stocked["producto_id"], "quantity": 50, "price": 100}])

        events = credit_events(cliente_id=customer, blocked_only=1)
        assert events["count"] >= 1
        assert events["events"][0]["blocked"] is True
        assert events["events"][0]["event_type"] == "order_create"

    def test_second_order_sees_the_first_as_exposure(self, seed_commercial, customer,
                                                    stocked):
        """Two orders that individually fit must not jointly exceed the limit."""
        from core.credit import credit_set_limit
        from core.sales import sales_orders_create, sales_orders_confirm
        credit_set_limit(cliente_id=customer, credit_limit=1500)
        first = sales_orders_create(cliente_id=customer, items=[
            {"producto_id": stocked["producto_id"], "quantity": 10, "price": 100}])
        assert "error" not in first
        sales_orders_confirm(order_id=first["id"])

        second = sales_orders_create(cliente_id=customer, items=[
            {"producto_id": stocked["producto_id"], "quantity": 10, "price": 100}])
        assert "error" in second, "1160 + 1160 exceeds 1500"


class TestLineDiscounts:
    def test_discount_reduces_the_subtotal(self, seed_commercial, customer, stocked):
        from core.sales import sales_orders_create
        r = sales_orders_create(cliente_id=customer, items=[
            {"producto_id": stocked["producto_id"], "quantity": 10, "price": 100,
             "discount_pct": 20}])
        assert r["gross_subtotal"] == 1000.0
        assert r["discount_total"] == 200.0
        assert r["subtotal"] == 800.0
        assert r["total"] == 928.0, "800 + 16% tax"

    def test_legacy_discount_key_still_works(self, seed_commercial, customer, stocked):
        from core.sales import sales_orders_create
        r = sales_orders_create(cliente_id=customer, items=[
            {"producto_id": stocked["producto_id"], "quantity": 10, "price": 100,
             "discount": 10}])
        assert r["subtotal"] == 900.0

    def test_discount_above_100_rejected(self, seed_commercial, customer, stocked):
        from core.sales import sales_orders_create
        r = sales_orders_create(cliente_id=customer, items=[
            {"producto_id": stocked["producto_id"], "quantity": 1, "price": 100,
             "discount_pct": 150}])
        assert "error" in r

    def test_negative_discount_rejected(self, seed_commercial, customer, stocked):
        from core.sales import sales_orders_create
        r = sales_orders_create(cliente_id=customer, items=[
            {"producto_id": stocked["producto_id"], "quantity": 1, "price": 100,
             "discount_pct": -10}])
        assert "error" in r

    def test_only_the_discounted_line_is_affected(self, seed_commercial, customer,
                                                  stocked):
        from core.sales import sales_orders_create
        r = sales_orders_create(cliente_id=customer, items=[
            {"producto_id": stocked["producto_id"], "quantity": 5, "price": 100,
             "discount_pct": 10},
            {"producto_id": stocked["producto_id"], "quantity": 5, "price": 100}])
        assert r["gross_subtotal"] == 1000.0
        assert r["discount_total"] == 50.0
        assert r["subtotal"] == 950.0

    def test_no_discount_leaves_totals_untouched(self, seed_commercial, customer,
                                                stocked):
        from core.sales import sales_orders_create
        r = sales_orders_create(cliente_id=customer, items=[
            {"producto_id": stocked["producto_id"], "quantity": 10, "price": 100}])
        assert r["discount_total"] == 0.0
        assert r["subtotal"] == r["gross_subtotal"] == 1000.0

    def test_discount_is_persisted_on_the_line(self, seed_commercial, customer,
                                              stocked, db_conn):
        from core.sales import sales_orders_create
        order = sales_orders_create(cliente_id=customer, items=[
            {"producto_id": stocked["producto_id"], "quantity": 4, "price": 250,
             "discount_pct": 25}])
        line = db_conn.execute(
            "SELECT discount, discount_pct, line_total FROM sales_order_items "
            "WHERE order_id = ?", (order["id"],)).fetchone()
        assert float(line["discount"]) == 25.0
        assert float(line["discount_pct"]) == 25.0
        assert float(line["line_total"]) == 750.0, "1000 less 25%"

    def test_full_discount_gives_a_free_line(self, seed_commercial, customer, stocked):
        from core.sales import sales_orders_create
        r = sales_orders_create(cliente_id=customer, items=[
            {"producto_id": stocked["producto_id"], "quantity": 2, "price": 100,
             "discount_pct": 100}])
        assert r["subtotal"] == 0.0
        assert r["discount_total"] == 200.0

    def test_discount_lowers_credit_consumption(self, seed_commercial, customer,
                                                stocked):
        """A discounted order must consume less credit, not the gross amount."""
        from core.credit import credit_set_limit
        from core.sales import sales_orders_create
        credit_set_limit(cliente_id=customer, credit_limit=1000)
        r = sales_orders_create(cliente_id=customer, items=[
            {"producto_id": stocked["producto_id"], "quantity": 10, "price": 100,
             "discount_pct": 50}])
        assert "error" not in r, "580 fits in 1000 even though gross is 1000"
        assert r["total"] == 580.0
