"""Tests for D1: inventory valuation, period locking, multicurrency.

These cover the gaps that made the numbers wrong rather than merely missing:
COGS was invented, "closed" periods were only a label, and FX differences
were never recorded.
"""
import pytest


class TestFifoValuation:
    def test_layers_accumulate_value(self, make_product, make_warehouse):
        from core.valuation import get_db, add_layer, stock_value
        pid, wid = make_product(cost=0), make_warehouse()
        db = get_db()
        add_layer(db, pid, wid, 100, 10)
        add_layer(db, pid, wid, 100, 14)
        db.commit()
        qty, value = stock_value(db, pid)
        db.close()
        assert qty == 200.0
        assert value == 2400.0

    def test_fifo_consumes_oldest_first(self, make_product, make_warehouse):
        from core.valuation import get_db, add_layer, consume_layers
        pid, wid = make_product(cost=0), make_warehouse()
        db = get_db()
        add_layer(db, pid, wid, 100, 10)
        add_layer(db, pid, wid, 100, 14)
        result = consume_layers(db, pid, wid, 150)
        db.commit()
        db.close()
        # 100 @ 10 + 50 @ 14 = 1700
        assert result["total_cost"] == 1700.0
        assert result["method"] == "fifo"
        assert result["uncosted_quantity"] == 0.0
        assert len(result["consumed"]) == 2

    def test_remaining_value_after_consumption(self, make_product, make_warehouse):
        from core.valuation import get_db, add_layer, consume_layers, stock_value
        pid, wid = make_product(cost=0), make_warehouse()
        db = get_db()
        add_layer(db, pid, wid, 100, 10)
        add_layer(db, pid, wid, 100, 14)
        consume_layers(db, pid, wid, 150)
        db.commit()
        qty, value = stock_value(db, pid)
        db.close()
        assert qty == 50.0
        assert value == 700.0, "only the 14-cost layer should remain"

    def test_average_method_prices_at_weighted_average(self, make_product,
                                                       make_warehouse, db_conn):
        from core.valuation import get_db, add_layer, consume_layers
        pid, wid = make_product(cost=0), make_warehouse()
        db_conn.execute("UPDATE productos SET costing_method = 'average' WHERE id = ?",
                        (pid,))
        db_conn.commit()

        db = get_db()
        add_layer(db, pid, wid, 100, 10)
        add_layer(db, pid, wid, 100, 20)
        result = consume_layers(db, pid, wid, 150)
        db.commit()
        db.close()
        # weighted average is 15, so 150 x 15 = 2250
        assert result["method"] == "average"
        assert result["total_cost"] == 2250.0

    def test_standard_method_uses_product_cost(self, make_product, make_warehouse,
                                               db_conn):
        from core.valuation import get_db, add_layer, consume_layers
        pid, wid = make_product(cost=7), make_warehouse()
        db_conn.execute("UPDATE productos SET costing_method = 'standard' WHERE id = ?",
                        (pid,))
        db_conn.commit()

        db = get_db()
        add_layer(db, pid, wid, 100, 99)  # layer cost is ignored
        result = consume_layers(db, pid, wid, 10)
        db.commit()
        db.close()
        assert result["method"] == "standard"
        assert result["total_cost"] == 70.0

    def test_consuming_more_than_available_reports_uncosted(self, make_product,
                                                           make_warehouse):
        """Never silently invent cost: report the shortfall explicitly."""
        from core.valuation import get_db, add_layer, consume_layers
        pid, wid = make_product(cost=5), make_warehouse()
        db = get_db()
        add_layer(db, pid, wid, 10, 10)
        result = consume_layers(db, pid, wid, 30)
        db.commit()
        db.close()
        assert result["uncosted_quantity"] == 20.0
        # 10 @ 10 from the layer + 20 @ 5 fallback
        assert result["total_cost"] == 200.0

    def test_average_cost_is_recomputed(self, make_product, make_warehouse, db_conn):
        from core.valuation import get_db, add_layer
        pid, wid = make_product(cost=0), make_warehouse()
        db = get_db()
        add_layer(db, pid, wid, 100, 10)
        add_layer(db, pid, wid, 100, 20)
        db.commit()
        db.close()
        avg = db_conn.execute("SELECT average_cost FROM productos WHERE id = ?",
                              (pid,)).fetchone()["average_cost"]
        assert float(avg) == 15.0


class TestValuationHandlers:
    def test_add_layer_requires_fields(self):
        from core.valuation_handlers import valuation_add_layer
        assert "error" in valuation_add_layer(producto_id=1)

    def test_negative_quantity_rejected(self, make_product, make_warehouse):
        from core.valuation_handlers import valuation_add_layer
        pid, wid = make_product(), make_warehouse()
        assert "error" in valuation_add_layer(producto_id=pid, warehouse_id=wid,
                                             quantity=-5, unit_cost=10)

    def test_set_method_validates(self, make_product):
        from core.valuation_handlers import valuation_set_method
        pid = make_product()
        assert "error" in valuation_set_method(producto_id=pid, method="telepathy")
        ok = valuation_set_method(producto_id=pid, method="average")
        assert ok["costing_method"] == "average"

    def test_cogs_report_totals_outbound_entries(self, make_product, make_warehouse):
        from core.valuation import get_db, add_layer, consume_layers
        from core.valuation_handlers import valuation_cogs
        pid, wid = make_product(cost=0), make_warehouse()
        db = get_db()
        add_layer(db, pid, wid, 100, 10)
        consume_layers(db, pid, wid, 40, source_type="sales_order", source_id=1)
        db.commit()
        db.close()

        report = valuation_cogs()
        assert report["total_cogs"] == 400.0
        assert report["by_product"][0]["producto_id"] == pid


class TestPurchaseAndSaleValuation:
    def test_receipt_creates_layer_at_purchase_price(self, seed_commercial,
                                                    make_product, make_warehouse,
                                                    db_conn):
        from core.purchasing_suppliers import suppliers_create
        from core.purchasing_rfq import rfq_create, rfq_quotes_add, rfq_award
        from core.purchasing_receipts import receipts_create
        pid, wid = make_product(cost=0), make_warehouse()
        sup = suppliers_create(name="Prov", country="MX")
        rfq = rfq_create(lines=[{"producto_id": pid, "qty": 500}])
        quote = rfq_quotes_add(rfq_id=rfq["id"], supplier_id=sup["id"],
                               lines=[{"producto_id": pid, "qty": 500, "unit_price": 3.5}])
        award = rfq_award(quote_id=quote["quote_id"])
        receipts_create(purchase_order_id=award["purchase_order_id"], warehouse_id=wid,
                        lines=[{"producto_id": pid, "qty_received": 500}])

        layer = db_conn.execute(
            "SELECT * FROM stock_layers WHERE producto_id = ? ORDER BY id DESC LIMIT 1",
            (pid,)).fetchone()
        assert layer is not None, "a receipt must create a cost layer"
        assert float(layer["unit_cost"]) == 3.5
        assert float(layer["remaining"]) == 500.0
        assert layer["source_type"] == "purchase_receipt"

    def test_delivery_reports_real_cogs(self, seed_commercial, make_product,
                                        make_warehouse, make_stock, db_conn):
        from core.valuation import get_db, add_layer
        from core.sales import sales_orders_create, sales_orders_confirm, sales_orders_deliver
        pid, wid = make_product(cost=0), make_warehouse()
        make_stock(pid, wid, 200)

        db = get_db()
        add_layer(db, pid, wid, 200, 3.5)
        db.commit()
        db.close()

        db_conn.execute("INSERT INTO clientes (nombre) VALUES ('Cliente')")
        db_conn.commit()
        order = sales_orders_create(cliente_id=1, items=[
            {"producto_id": pid, "quantity": 200, "price": 5}])
        sales_orders_confirm(order_id=order["id"])
        result = sales_orders_deliver(order_id=order["id"])

        assert result["delivered"] is True
        assert result["cogs"] == 700.0, "200 units at a real cost of 3.5"


class TestFiscalPeriodLocking:
    def test_generate_year_creates_twelve(self):
        from core.fiscal_periods import periods_generate_year, periods_list
        r = periods_generate_year(year=2026)
        assert r["count"] == 12
        assert len(periods_list(year=2026)) == 12

    def test_duplicate_period_rejected(self):
        from core.fiscal_periods import periods_create
        assert "error" not in periods_create(year=2026, month=3)
        assert "error" in periods_create(year=2026, month=3)

    def test_invalid_month_rejected(self):
        from core.fiscal_periods import periods_create
        assert "error" in periods_create(year=2026, month=13)

    def test_open_period_allows_posting(self, seed_accounting):
        from core.fiscal_periods import periods_generate_year, periods_check
        from core.accounting import journal_create
        periods_generate_year(year=2026)
        assert periods_check(date="2026-03-15")["allowed"] is True

        r = journal_create(description="Marzo", date="2026-03-15",
                           lines=[{"account_id": 1, "debit": 100, "credit": 0},
                                  {"account_id": 2, "debit": 0, "credit": 100}])
        assert "error" not in r, r

    def test_closed_period_refuses_posting(self, seed_accounting):
        """This is the whole point: 'closed' must mean closed."""
        from core.fiscal_periods import periods_generate_year, periods_close, periods_check
        from core.accounting import journal_create
        periods_generate_year(year=2026)
        closed = periods_close(year=2026, month=3)
        assert closed["closed"] is True

        check = periods_check(date="2026-03-15")
        assert check["allowed"] is False

        r = journal_create(description="Tardio", date="2026-03-20",
                           lines=[{"account_id": 1, "debit": 50, "credit": 0},
                                  {"account_id": 2, "debit": 0, "credit": 50}])
        assert "error" in r
        assert "closed" in r["error"].lower()

    def test_other_periods_stay_open(self, seed_accounting):
        from core.fiscal_periods import periods_generate_year, periods_close
        from core.accounting import journal_create
        periods_generate_year(year=2026)
        periods_close(year=2026, month=3)

        r = journal_create(description="Abril", date="2026-04-05",
                           lines=[{"account_id": 1, "debit": 70, "credit": 0},
                                  {"account_id": 2, "debit": 0, "credit": 70}])
        assert "error" not in r, "closing March must not affect April"

    def test_reopen_restores_posting(self, seed_accounting):
        from core.fiscal_periods import (periods_generate_year, periods_close,
                                         periods_reopen)
        from core.accounting import journal_create
        periods_generate_year(year=2026)
        periods_close(year=2026, month=3)
        periods_reopen(year=2026, month=3)

        r = journal_create(description="Reabierto", date="2026-03-25",
                           lines=[{"account_id": 1, "debit": 30, "credit": 0},
                                  {"account_id": 2, "debit": 0, "credit": 30}])
        assert "error" not in r, r

    def test_double_close_rejected(self):
        from core.fiscal_periods import periods_generate_year, periods_close
        periods_generate_year(year=2026)
        assert "error" not in periods_close(year=2026, month=5)
        assert "error" in periods_close(year=2026, month=5)

    def test_date_without_period_is_allowed(self):
        """Periods are opt-in; an install with none must keep working."""
        from core.fiscal_periods import periods_check
        assert periods_check(date="2099-01-01")["allowed"] is True


class TestMulticurrency:
    def test_base_currency_rate_is_one(self, db_conn):
        from core.multicurrency import fx_rate, get_db, base_currency
        db = get_db()
        base = base_currency(db)
        db.close()
        assert fx_rate(currency=base)["rate"] == 1.0

    def test_rate_lookup_joins_currency_code(self, db_conn):
        """exchange_rates stores currency_id, not the code."""
        from core.multicurrency import fx_rate
        cur = db_conn.execute(
            "SELECT id, code FROM currencies WHERE is_base = 0 LIMIT 1").fetchone()
        if not cur:
            pytest.skip("no non-base currency seeded")
        db_conn.execute(
            "INSERT INTO exchange_rates (currency_id, rate, date) VALUES (?, ?, ?)",
            (cur["id"], 17.5, "2099-01-01"))
        db_conn.commit()

        r = fx_rate(currency=cur["code"])
        assert r["rate"] == 17.5, "the join must resolve the code to currency_id"

    def test_convert_requires_arguments(self):
        from core.multicurrency import fx_convert
        assert "error" in fx_convert(amount=100, from_currency="USD")

    def test_conversion_goes_through_base(self, db_conn):
        from core.multicurrency import fx_convert
        cur = db_conn.execute(
            "SELECT id, code FROM currencies WHERE is_base = 0 LIMIT 1").fetchone()
        if not cur:
            pytest.skip("no non-base currency seeded")
        db_conn.execute(
            "INSERT INTO exchange_rates (currency_id, rate, date) VALUES (?, ?, ?)",
            (cur["id"], 20.0, "2099-01-01"))
        db_conn.commit()

        r = fx_convert(amount=100, from_currency=cur["code"],
                       to_currency=r_base(db_conn))
        assert r["amount_base"] == 2000.0
        assert r["result"] == 2000.0

    def test_gain_is_recorded(self, db_conn):
        from core.multicurrency import fx_record_difference
        db_conn.execute("INSERT INTO clientes (nombre) VALUES ('Cliente')")
        db_conn.execute(
            "INSERT INTO facturas (cliente_id, total, currency, exchange_rate) "
            "VALUES (1, 10000, 'USD', 17.5)")
        db_conn.commit()

        r = fx_record_difference(document_type="invoice", document_id=1,
                                 amount_currency=10000, payment_rate=18.10)
        assert r["recorded"] is True
        assert r["gain_or_loss"] == "gain"
        assert r["difference_base"] == 6000.0

    def test_loss_is_recorded(self, db_conn):
        from core.multicurrency import fx_record_difference
        db_conn.execute("INSERT INTO clientes (nombre) VALUES ('Cliente')")
        db_conn.execute(
            "INSERT INTO facturas (cliente_id, total, currency, exchange_rate) "
            "VALUES (1, 5000, 'USD', 17.5)")
        db_conn.commit()

        r = fx_record_difference(document_type="invoice", document_id=1,
                                 amount_currency=5000, payment_rate=17.0)
        assert r["gain_or_loss"] == "loss"
        assert r["difference_base"] == -2500.0

    def test_same_rate_records_nothing(self, db_conn):
        from core.multicurrency import fx_record_difference
        db_conn.execute("INSERT INTO clientes (nombre) VALUES ('Cliente')")
        db_conn.execute(
            "INSERT INTO facturas (cliente_id, total, currency, exchange_rate) "
            "VALUES (1, 1000, 'USD', 17.5)")
        db_conn.commit()

        r = fx_record_difference(document_type="invoice", document_id=1,
                                 amount_currency=1000, payment_rate=17.5)
        assert r["recorded"] is False

    def test_differences_report_nets_gain_and_loss(self, db_conn):
        from core.multicurrency import fx_record_difference, fx_differences
        db_conn.execute("INSERT INTO clientes (nombre) VALUES ('Cliente')")
        db_conn.execute(
            "INSERT INTO facturas (cliente_id, total, currency, exchange_rate) "
            "VALUES (1, 10000, 'USD', 17.5)")
        db_conn.execute(
            "INSERT INTO facturas (cliente_id, total, currency, exchange_rate) "
            "VALUES (1, 5000, 'USD', 17.5)")
        db_conn.commit()
        fx_record_difference(document_type="invoice", document_id=1,
                             amount_currency=10000, payment_rate=18.10)
        fx_record_difference(document_type="invoice", document_id=2,
                             amount_currency=5000, payment_rate=17.0)

        rep = fx_differences()
        assert rep["total_gain"] == 6000.0
        assert rep["total_loss"] == -2500.0
        assert rep["net_effect"] == 3500.0

    def test_document_rate_is_stamped(self, db_conn):
        from core.multicurrency import fx_set_document_rate
        db_conn.execute("INSERT INTO clientes (nombre) VALUES ('Cliente')")
        db_conn.execute("INSERT INTO facturas (cliente_id, total) VALUES (1, 1000)")
        db_conn.commit()

        r = fx_set_document_rate(document_type="invoice", document_id=1,
                                 currency="USD", exchange_rate=17.5)
        assert r["currency"] == "USD"
        row = db_conn.execute(
            "SELECT currency, exchange_rate FROM facturas WHERE id = 1").fetchone()
        assert row["currency"] == "USD"
        assert float(row["exchange_rate"]) == 17.5

    def test_unknown_document_type_rejected(self):
        from core.multicurrency import fx_set_document_rate
        r = fx_set_document_rate(document_type="unicorn", document_id=1)
        assert "error" in r
        assert "allowed" in r

    def test_exposure_groups_open_balances(self, db_conn):
        from core.multicurrency import fx_exposure
        db_conn.execute("INSERT INTO clientes (nombre) VALUES ('Cliente')")
        db_conn.execute(
            "INSERT INTO facturas (cliente_id, total, amount_paid, currency) "
            "VALUES (1, 10000, 2000, 'USD')")
        db_conn.commit()

        exp = fx_exposure()
        usd = next((c for c in exp["by_currency"] if c["currency"] == "USD"), None)
        assert usd is not None
        assert usd["open_balance"] == 8000.0


class TestStatementsUseRealCost:
    """The whole point of D1: the statements must stop ignoring inventory cost."""

    def test_income_statement_reports_cogs_and_margin(self, seed_accounting,
                                                      make_product, make_warehouse):
        from core.valuation import get_db, add_layer, consume_layers
        from core.accounting import income_statement, journal_create
        pid, wid = make_product(cost=0), make_warehouse()

        db = get_db()
        add_layer(db, pid, wid, 100, 6)
        consume_layers(db, pid, wid, 100, source_type="sales_order", source_id=1)
        db.commit()
        db.close()

        # Post revenue of 1000 against a revenue account
        rev = None
        from core.accounting import accounts_list
        for a in accounts_list():
            if a["type"] == "revenue":
                rev = a["id"]
                break
        asset = next(a["id"] for a in accounts_list() if a["type"] == "asset")
        journal_create(description="Venta", date="2026-06-01",
                       lines=[{"account_id": asset, "debit": 1000, "credit": 0},
                              {"account_id": rev, "debit": 0, "credit": 1000}])

        stmt = income_statement()
        assert stmt["cogs"] == 600.0, "cost must come from the consumed layers"
        assert stmt["gross_profit"] == 400.0
        assert stmt["gross_margin_pct"] == 40.0

    def test_balance_sheet_carries_inventory_value(self, seed_accounting,
                                                   make_product, make_warehouse):
        from core.valuation import get_db, add_layer
        from core.accounting import balance_sheet
        pid, wid = make_product(cost=0), make_warehouse()
        db = get_db()
        add_layer(db, pid, wid, 50, 8)
        db.commit()
        db.close()

        bs = balance_sheet()
        assert bs["inventory_value"] == 400.0
        assert bs["assets_including_inventory"] == round(bs["assets"] + 400.0, 2)


def r_base(db_conn):
    row = db_conn.execute(
        "SELECT code FROM currencies WHERE is_base = 1 LIMIT 1").fetchone()
    return row["code"] if row else "USD"
