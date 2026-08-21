"""Tests for D3 sales returns and credit notes."""
import pytest


@pytest.fixture
def customer(db_conn):
    db_conn.execute("INSERT INTO clientes (nombre, email) VALUES ('Cliente', 'c@x.com')")
    db_conn.commit()
    return 1


@pytest.fixture
def sold_order(seed_commercial, customer, make_product, make_warehouse, make_stock):
    """A delivered order of 10 units at 100, costed at 60."""
    from core.valuation import get_db, add_layer
    from core.sales import (sales_orders_create, sales_orders_confirm,
                            sales_orders_deliver)
    pid, wid = make_product("D3-1", "Producto", 100, 60), make_warehouse()
    make_stock(pid, wid, 200)
    db = get_db()
    add_layer(db, pid, wid, 200, 60)
    db.commit()

    order = sales_orders_create(cliente_id=customer, items=[
        {"producto_id": pid, "quantity": 10, "price": 100}])
    sales_orders_confirm(order_id=order["id"])
    sales_orders_deliver(order_id=order["id"])
    return {"order_id": order["id"], "producto_id": pid, "warehouse_id": wid}


class TestSalesReturnValidation:
    def test_requires_customer_and_lines(self):
        from core.sales_returns import sales_returns_create
        assert "error" in sales_returns_create(cliente_id=1)
        assert "error" in sales_returns_create(lines=[{"producto_id": 1, "quantity": 1}])

    def test_unknown_customer_rejected(self, make_product):
        from core.sales_returns import sales_returns_create
        r = sales_returns_create(cliente_id=9999,
                                 lines=[{"producto_id": make_product(), "quantity": 1}])
        assert "error" in r

    def test_zero_quantity_rejected(self, customer, make_product):
        from core.sales_returns import sales_returns_create
        r = sales_returns_create(cliente_id=customer,
                                 lines=[{"producto_id": make_product(), "quantity": 0}])
        assert "error" in r

    def test_cannot_return_more_than_sold(self, sold_order, customer):
        """The whole point: a return must be bounded by what shipped."""
        from core.sales_returns import sales_returns_create
        r = sales_returns_create(cliente_id=customer,
                                 sales_order_id=sold_order["order_id"],
                                 lines=[{"producto_id": sold_order["producto_id"],
                                         "quantity": 20}])
        assert "error" in r
        assert r["returnable"] == 10.0

    def test_product_not_in_order_rejected(self, sold_order, customer, make_product):
        from core.sales_returns import sales_returns_create
        other = make_product("OTRO", "Otro", 50, 20)
        r = sales_returns_create(cliente_id=customer,
                                 sales_order_id=sold_order["order_id"],
                                 lines=[{"producto_id": other, "quantity": 1}])
        assert "error" in r
        assert "not in order" in r["error"]

    def test_order_of_another_customer_rejected(self, sold_order, db_conn):
        from core.sales_returns import sales_returns_create
        db_conn.execute("INSERT INTO clientes (nombre) VALUES ('Otro Cliente')")
        db_conn.commit()
        r = sales_returns_create(cliente_id=2, sales_order_id=sold_order["order_id"],
                                 lines=[{"producto_id": sold_order["producto_id"],
                                         "quantity": 1}])
        assert "error" in r

    def test_price_defaults_to_the_sold_price(self, sold_order, customer):
        from core.sales_returns import sales_returns_create
        r = sales_returns_create(cliente_id=customer,
                                 sales_order_id=sold_order["order_id"],
                                 lines=[{"producto_id": sold_order["producto_id"],
                                         "quantity": 4}])
        assert "error" not in r, r
        assert r["total"] == 400.0, "4 units at the order price of 100"

    def test_second_return_respects_the_first(self, sold_order, customer):
        from core.sales_returns import sales_returns_create
        sales_returns_create(cliente_id=customer,
                             sales_order_id=sold_order["order_id"],
                             lines=[{"producto_id": sold_order["producto_id"],
                                     "quantity": 4}])
        r = sales_returns_create(cliente_id=customer,
                                 sales_order_id=sold_order["order_id"],
                                 lines=[{"producto_id": sold_order["producto_id"],
                                         "quantity": 8}])
        assert "error" in r
        assert r["returnable"] == 6.0


class TestSalesReturnReceipt:
    def _draft(self, sold_order, customer, qty=4, restock=1):
        from core.sales_returns import sales_returns_create
        return sales_returns_create(cliente_id=customer,
                                    sales_order_id=sold_order["order_id"],
                                    warehouse_id=sold_order["warehouse_id"],
                                    restock=restock,
                                    lines=[{"producto_id": sold_order["producto_id"],
                                            "quantity": qty}])

    def test_receive_puts_stock_back(self, sold_order, customer, db_conn):
        from core.sales_returns import sales_returns_receive
        ret = self._draft(sold_order, customer)
        before = db_conn.execute(
            "SELECT quantity FROM stock WHERE producto_id = ? AND warehouse_id = ?",
            (sold_order["producto_id"], sold_order["warehouse_id"])).fetchone()["quantity"]

        r = sales_returns_receive(return_id=ret["id"])
        assert r["received"] is True

        after = db_conn.execute(
            "SELECT quantity FROM stock WHERE producto_id = ? AND warehouse_id = ?",
            (sold_order["producto_id"], sold_order["warehouse_id"])).fetchone()["quantity"]
        assert float(after) == float(before) + 4.0

    def test_receive_restores_cost_to_inventory(self, sold_order, customer):
        """COGS must be reversed, not left overstated."""
        from core.sales_returns import sales_returns_receive
        ret = self._draft(sold_order, customer)
        r = sales_returns_receive(return_id=ret["id"])
        assert r["value_returned_to_inventory"] == 240.0, "4 units at a real cost of 60"

    def test_no_restock_leaves_stock_alone(self, sold_order, customer, db_conn):
        from core.sales_returns import sales_returns_receive
        ret = self._draft(sold_order, customer, restock=0)
        before = db_conn.execute(
            "SELECT quantity FROM stock WHERE producto_id = ?",
            (sold_order["producto_id"],)).fetchone()["quantity"]
        r = sales_returns_receive(return_id=ret["id"])
        after = db_conn.execute(
            "SELECT quantity FROM stock WHERE producto_id = ?",
            (sold_order["producto_id"],)).fetchone()["quantity"]
        assert float(after) == float(before), "scrapped goods do not re-enter stock"
        assert r["restock"] is False

    def test_cannot_receive_twice(self, sold_order, customer):
        from core.sales_returns import sales_returns_receive
        ret = self._draft(sold_order, customer)
        sales_returns_receive(return_id=ret["id"])
        assert "error" in sales_returns_receive(return_id=ret["id"])

    def test_unknown_return_errors(self):
        from core.sales_returns import sales_returns_receive
        assert "error" in sales_returns_receive(return_id=9999)


class TestCreditNoteIssuance:
    def _received(self, sold_order, customer, qty=4):
        from core.sales_returns import sales_returns_create, sales_returns_receive
        ret = sales_returns_create(cliente_id=customer,
                                   sales_order_id=sold_order["order_id"],
                                   warehouse_id=sold_order["warehouse_id"],
                                   lines=[{"producto_id": sold_order["producto_id"],
                                           "quantity": qty}])
        sales_returns_receive(return_id=ret["id"])
        return ret

    def test_credit_requires_receipt_first(self, sold_order, customer):
        from core.sales_returns import sales_returns_create, sales_returns_credit
        ret = sales_returns_create(cliente_id=customer,
                                   sales_order_id=sold_order["order_id"],
                                   lines=[{"producto_id": sold_order["producto_id"],
                                           "quantity": 2}])
        r = sales_returns_credit(return_id=ret["id"])
        assert "error" in r
        assert "receive the goods first" in r["error"]

    def test_credit_note_matches_the_return_value(self, sold_order, customer):
        from core.sales_returns import sales_returns_credit
        ret = self._received(sold_order, customer)
        r = sales_returns_credit(return_id=ret["id"])
        assert r["credited"] is True
        assert r["amount"] == 400.0
        assert r["status"] == "open"
        assert r["folio"]

    def test_cannot_credit_twice(self, sold_order, customer):
        from core.sales_returns import sales_returns_credit
        ret = self._received(sold_order, customer)
        sales_returns_credit(return_id=ret["id"])
        assert "error" in sales_returns_credit(return_id=ret["id"])

    def test_credited_return_cannot_be_cancelled(self, sold_order, customer):
        from core.sales_returns import sales_returns_credit, sales_returns_cancel
        ret = self._received(sold_order, customer)
        sales_returns_credit(return_id=ret["id"])
        assert "error" in sales_returns_cancel(return_id=ret["id"])

    def test_draft_return_can_be_cancelled(self, sold_order, customer):
        from core.sales_returns import sales_returns_create, sales_returns_cancel
        ret = sales_returns_create(cliente_id=customer,
                                   sales_order_id=sold_order["order_id"],
                                   lines=[{"producto_id": sold_order["producto_id"],
                                           "quantity": 1}])
        assert sales_returns_cancel(return_id=ret["id"])["cancelled"] is True

    def test_cancelled_return_frees_the_quantity(self, sold_order, customer):
        """A cancelled return must not keep consuming the returnable amount."""
        from core.sales_returns import sales_returns_create, sales_returns_cancel
        first = sales_returns_create(cliente_id=customer,
                                     sales_order_id=sold_order["order_id"],
                                     lines=[{"producto_id": sold_order["producto_id"],
                                             "quantity": 10}])
        sales_returns_cancel(return_id=first["id"])
        second = sales_returns_create(cliente_id=customer,
                                      sales_order_id=sold_order["order_id"],
                                      lines=[{"producto_id": sold_order["producto_id"],
                                              "quantity": 10}])
        assert "error" not in second, second


class TestReturnNetsOffCogs:
    """A return has to reduce cost of sales, or COGS stays overstated."""

    def test_income_statement_nets_the_returned_cost(self, sold_order, customer):
        from core.sales_returns import (sales_returns_create, sales_returns_receive)
        from core.accounting import income_statement
        before = income_statement()["cogs"]
        assert before == 600.0, "10 units at a cost of 60"

        ret = sales_returns_create(cliente_id=customer,
                                   sales_order_id=sold_order["order_id"],
                                   warehouse_id=sold_order["warehouse_id"],
                                   lines=[{"producto_id": sold_order["producto_id"],
                                           "quantity": 4}])
        sales_returns_receive(return_id=ret["id"])

        after = income_statement()["cogs"]
        assert after == 360.0, "600 less the 240 that came back"

    def test_cogs_report_shows_gross_and_net(self, sold_order, customer):
        from core.sales_returns import sales_returns_create, sales_returns_receive
        from core.valuation_handlers import valuation_cogs
        ret = sales_returns_create(cliente_id=customer,
                                   sales_order_id=sold_order["order_id"],
                                   warehouse_id=sold_order["warehouse_id"],
                                   lines=[{"producto_id": sold_order["producto_id"],
                                           "quantity": 4}])
        sales_returns_receive(return_id=ret["id"])

        r = valuation_cogs()
        assert r["gross_cogs"] == 600.0
        assert r["returned_cost"] == 240.0
        assert r["total_cogs"] == 360.0

    def test_scrapped_return_does_not_reduce_cogs(self, sold_order, customer):
        """Goods that were not restocked stay as a cost of the period."""
        from core.sales_returns import sales_returns_create, sales_returns_receive
        from core.accounting import income_statement
        ret = sales_returns_create(cliente_id=customer,
                                   sales_order_id=sold_order["order_id"],
                                   warehouse_id=sold_order["warehouse_id"],
                                   restock=0,
                                   lines=[{"producto_id": sold_order["producto_id"],
                                           "quantity": 4}])
        sales_returns_receive(return_id=ret["id"])
        assert income_statement()["cogs"] == 600.0


class TestCreditNoteApplication:
    @pytest.fixture
    def note_and_invoice(self, sold_order, customer, db_conn):
        from core.sales_returns import (sales_returns_create, sales_returns_receive,
                                        sales_returns_credit)
        ret = sales_returns_create(cliente_id=customer,
                                   sales_order_id=sold_order["order_id"],
                                   warehouse_id=sold_order["warehouse_id"],
                                   lines=[{"producto_id": sold_order["producto_id"],
                                           "quantity": 4}])
        sales_returns_receive(return_id=ret["id"])
        note = sales_returns_credit(return_id=ret["id"])

        db_conn.execute(
            "INSERT INTO facturas (cliente_id, total, amount_paid) VALUES (?, 1000, 0)",
            (customer,))
        db_conn.commit()
        invoice_id = db_conn.execute(
            "SELECT id FROM facturas ORDER BY id DESC LIMIT 1").fetchone()["id"]
        return {"note_id": note["credit_note_id"], "invoice_id": invoice_id}

    def test_requires_both_ids(self):
        from core.sales_returns import credit_notes_apply
        assert "error" in credit_notes_apply(credit_note_id=1)

    def test_partial_application_leaves_a_remainder(self, note_and_invoice):
        from core.sales_returns import credit_notes_apply
        r = credit_notes_apply(credit_note_id=note_and_invoice["note_id"],
                               invoice_id=note_and_invoice["invoice_id"],
                               amount=320)
        assert r["applied"] is True
        assert r["amount_applied"] == 320.0
        assert r["credit_note_remaining"] == 80.0
        assert r["credit_note_status"] == "partially_applied"
        assert r["invoice_due_after"] == 680.0

    def test_over_application_rejected(self, note_and_invoice):
        from core.sales_returns import credit_notes_apply
        r = credit_notes_apply(credit_note_id=note_and_invoice["note_id"],
                               invoice_id=note_and_invoice["invoice_id"],
                               amount=9999)
        assert "error" in r

    def test_full_application_closes_the_note(self, note_and_invoice):
        from core.sales_returns import credit_notes_apply, credit_notes_list
        credit_notes_apply(credit_note_id=note_and_invoice["note_id"],
                           invoice_id=note_and_invoice["invoice_id"], amount=400)
        note = credit_notes_list()[0]
        assert note["status"] == "applied"
        assert note["remaining"] == 0.0

    def test_default_amount_uses_what_fits(self, note_and_invoice):
        from core.sales_returns import credit_notes_apply
        r = credit_notes_apply(credit_note_id=note_and_invoice["note_id"],
                               invoice_id=note_and_invoice["invoice_id"])
        assert r["amount_applied"] == 400.0, "min(note remaining, invoice due)"

    def test_invoice_of_another_customer_rejected(self, note_and_invoice, db_conn):
        from core.sales_returns import credit_notes_apply
        db_conn.execute("INSERT INTO clientes (nombre) VALUES ('Otro')")
        db_conn.execute("INSERT INTO facturas (cliente_id, total) VALUES (2, 500)")
        db_conn.commit()
        other = db_conn.execute(
            "SELECT id FROM facturas ORDER BY id DESC LIMIT 1").fetchone()["id"]
        r = credit_notes_apply(credit_note_id=note_and_invoice["note_id"],
                               invoice_id=other, amount=100)
        assert "error" in r
        assert "different customer" in r["error"]

    def test_applied_note_cannot_be_cancelled(self, note_and_invoice):
        from core.sales_returns import credit_notes_apply, credit_notes_cancel
        credit_notes_apply(credit_note_id=note_and_invoice["note_id"],
                           invoice_id=note_and_invoice["invoice_id"], amount=100)
        r = credit_notes_cancel(credit_note_id=note_and_invoice["note_id"])
        assert "error" in r

    def test_unapplied_note_can_be_cancelled(self, note_and_invoice):
        from core.sales_returns import credit_notes_cancel
        assert credit_notes_cancel(
            credit_note_id=note_and_invoice["note_id"])["cancelled"] is True

    def test_settled_invoice_rejects_more_credit(self, note_and_invoice, db_conn):
        from core.sales_returns import credit_notes_apply
        db_conn.execute("UPDATE facturas SET amount_paid = total WHERE id = ?",
                        (note_and_invoice["invoice_id"],))
        db_conn.commit()
        r = credit_notes_apply(credit_note_id=note_and_invoice["note_id"],
                               invoice_id=note_and_invoice["invoice_id"], amount=10)
        assert "error" in r
        assert "already settled" in r["error"]
