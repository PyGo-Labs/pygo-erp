"""Tests for D2 wired into the real sales and purchase flow.

Reservations and lots are only useful if the actual documents use them, so
these tests go through sales_orders_confirm / deliver and receipts_create
rather than calling the reservation API directly.
"""
import pytest


@pytest.fixture
def customer(db_conn):
    db_conn.execute("INSERT INTO clientes (nombre, email) VALUES ('Cliente', 'c@x.com')")
    db_conn.commit()
    return 1


class TestConfirmReservesAndBackorders:
    def test_confirm_reserves_available_stock(self, seed_commercial, customer,
                                             make_product, make_warehouse, make_stock):
        from core.sales import sales_orders_create, sales_orders_confirm
        from core.reservations import stock_availability
        pid, wid = make_product(), make_warehouse()
        make_stock(pid, wid, 100)

        order = sales_orders_create(cliente_id=customer, items=[
            {"producto_id": pid, "quantity": 40, "price": 100}])
        r = sales_orders_confirm(order_id=order["id"])
        assert r["confirmed"] is True
        assert r.get("reserved"), "confirming must reserve the promised goods"

        a = stock_availability(producto_id=pid, warehouse_id=wid)
        assert a["on_hand"] == 100.0, "reserving does not move physical stock"
        assert a["reserved"] == 40.0
        assert a["available"] == 60.0

    def test_shortfall_becomes_a_backorder(self, seed_commercial, customer,
                                          make_product, make_warehouse, make_stock):
        from core.sales import sales_orders_create, sales_orders_confirm
        from core.reservations import backorders_list
        pid, wid = make_product(), make_warehouse()
        make_stock(pid, wid, 50)

        order = sales_orders_create(cliente_id=customer, items=[
            {"producto_id": pid, "quantity": 80, "price": 100}])
        r = sales_orders_confirm(order_id=order["id"])
        assert r["reserved"][0]["quantity"] == 50.0
        assert r["backordered"][0]["quantity"] == 30.0

        bos = backorders_list(status="pending")
        assert len(bos) == 1
        assert float(bos[0]["quantity_pending"]) == 30.0
        assert float(bos[0]["quantity_ordered"]) == 80.0

    def test_second_order_cannot_take_reserved_stock(self, seed_commercial, customer,
                                                     make_product, make_warehouse,
                                                     make_stock):
        """The real-world failure this prevents: selling the same units twice."""
        from core.sales import sales_orders_create, sales_orders_confirm
        pid, wid = make_product(), make_warehouse()
        make_stock(pid, wid, 50)

        first = sales_orders_create(cliente_id=customer, items=[
            {"producto_id": pid, "quantity": 50, "price": 100}])
        sales_orders_confirm(order_id=first["id"])

        second = sales_orders_create(cliente_id=customer, items=[
            {"producto_id": pid, "quantity": 20, "price": 100}])
        r = sales_orders_confirm(order_id=second["id"])
        assert not r.get("reserved"), "nothing is available to reserve"
        assert r["backordered"][0]["quantity"] == 20.0

    def test_order_without_stock_is_fully_backordered(self, seed_commercial, customer,
                                                     make_product):
        from core.sales import sales_orders_create, sales_orders_confirm
        pid = make_product()
        order = sales_orders_create(cliente_id=customer, items=[
            {"producto_id": pid, "quantity": 15, "price": 100}])
        r = sales_orders_confirm(order_id=order["id"])
        assert r["backordered"][0]["quantity"] == 15.0


class TestDeliveryClosesReservations:
    def test_delivery_fulfills_the_reservation(self, seed_commercial, customer,
                                              make_product, make_warehouse,
                                              make_stock):
        from core.sales import (sales_orders_create, sales_orders_confirm,
                                sales_orders_deliver)
        from core.reservations import reservations_list
        pid, wid = make_product(), make_warehouse()
        make_stock(pid, wid, 100)

        order = sales_orders_create(cliente_id=customer, items=[
            {"producto_id": pid, "quantity": 30, "price": 100}])
        sales_orders_confirm(order_id=order["id"])
        assert len(reservations_list(document_type="sales_order",
                                     document_id=order["id"], status="active")) == 1

        sales_orders_deliver(order_id=order["id"])
        assert reservations_list(document_type="sales_order",
                                 document_id=order["id"], status="active") == []
        assert len(reservations_list(document_type="sales_order",
                                     document_id=order["id"],
                                     status="fulfilled")) == 1

    def test_available_recovers_after_delivery(self, seed_commercial, customer,
                                               make_product, make_warehouse,
                                               make_stock):
        """Stock left the building: on hand drops and the reservation clears."""
        from core.sales import (sales_orders_create, sales_orders_confirm,
                                sales_orders_deliver)
        from core.reservations import stock_availability
        pid, wid = make_product(), make_warehouse()
        make_stock(pid, wid, 100)

        order = sales_orders_create(cliente_id=customer, items=[
            {"producto_id": pid, "quantity": 30, "price": 100}])
        sales_orders_confirm(order_id=order["id"])
        sales_orders_deliver(order_id=order["id"])

        a = stock_availability(producto_id=pid, warehouse_id=wid)
        assert a["on_hand"] == 70.0
        assert a["reserved"] == 0.0
        assert a["available"] == 70.0


class TestReceiptCreatesLots:
    def _award_po(self, pid, qty=60, price=200):
        from core.purchasing_suppliers import suppliers_create
        from core.purchasing_rfq import rfq_create, rfq_quotes_add, rfq_award
        sup = suppliers_create(name="Farma", country="MX")
        rfq = rfq_create(lines=[{"producto_id": pid, "qty": qty}])
        quote = rfq_quotes_add(rfq_id=rfq["id"], supplier_id=sup["id"],
                               lines=[{"producto_id": pid, "qty": qty,
                                       "unit_price": price}])
        return rfq_award(quote_id=quote["quote_id"])

    def test_receipt_registers_lot_with_expiry(self, seed_commercial, make_product,
                                               make_warehouse):
        from core.lots import lots_set_tracking, lots_list
        from core.purchasing_receipts import receipts_create
        pid, wid = make_product("MED-9", "Vacuna", 500, 0), make_warehouse()
        lots_set_tracking(producto_id=pid, tracking="lot")
        award = self._award_po(pid)

        receipts_create(purchase_order_id=award["purchase_order_id"], warehouse_id=wid,
                        lines=[{"producto_id": pid, "qty_received": 60,
                                "lot_code": "LOTE-A", "expiry_date": "2026-10-15"}])

        lots = lots_list(producto_id=pid, only_available=1)
        assert len(lots) == 1
        assert lots[0]["lot_code"] == "LOTE-A"
        assert lots[0]["expiry_date"] == "2026-10-15"
        assert float(lots[0]["quantity"]) == 60.0

    def test_untracked_product_gets_no_lot(self, seed_commercial, make_product,
                                          make_warehouse, db_conn):
        from core.purchasing_receipts import receipts_create
        pid, wid = make_product(), make_warehouse()
        award = self._award_po(pid)
        receipts_create(purchase_order_id=award["purchase_order_id"], warehouse_id=wid,
                        lines=[{"producto_id": pid, "qty_received": 60}])
        n = db_conn.execute("SELECT COUNT(*) FROM lots WHERE producto_id = ?",
                            (pid,)).fetchone()[0]
        assert n == 0, "tracking is opt-in"

    def test_full_cycle_purchase_to_sale_traceability(self, seed_commercial, customer,
                                                     make_product, make_warehouse,
                                                     make_stock):
        """Buy a lot, sell part of it, and be able to prove where it went."""
        from core.lots import lots_set_tracking, lots_trace
        from core.purchasing_receipts import receipts_create
        from core.sales import (sales_orders_create, sales_orders_confirm,
                                sales_orders_deliver)
        pid, wid = make_product("MED-9", "Vacuna", 500, 0), make_warehouse()
        lots_set_tracking(producto_id=pid, tracking="lot")
        award = self._award_po(pid, qty=60, price=200)
        receipts_create(purchase_order_id=award["purchase_order_id"], warehouse_id=wid,
                        lines=[{"producto_id": pid, "qty_received": 60,
                                "lot_code": "LOTE-A", "expiry_date": "2026-10-15"}])

        order = sales_orders_create(cliente_id=customer, items=[
            {"producto_id": pid, "quantity": 25, "price": 500}])
        sales_orders_confirm(order_id=order["id"])
        result = sales_orders_deliver(order_id=order["id"])

        # Cost came from the real purchase price: 25 x 200
        assert result["cogs"] == 5000.0
        assert result["lots_issued"][0]["lot_code"] == "LOTE-A"
        assert result["lots_issued"][0]["quantity"] == 25.0

        trace = lots_trace(producto_id=pid, lot_code="LOTE-A")
        assert trace["total_received"] == 60.0
        assert trace["total_issued"] == 25.0
        assert trace["on_hand"] == 35.0
        directions = [(m["direction"], m["source_type"]) for m in trace["movements"]]
        assert ("in", "purchase_receipt") in directions
        assert ("out", "sales_order") in directions
