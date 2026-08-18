"""Tests for Sales module."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


class TestSalesOrders:
    def test_create_requires_cliente(self):
        from core.sales import sales_orders_create
        result = sales_orders_create()
        assert "error" in result
    
    def test_create_requires_items(self):
        from core.sales import sales_orders_create
        result = sales_orders_create(cliente_id=1)
        assert "error" in result
    
    def test_list_returns_list(self):
        from core.sales import sales_orders_list
        result = sales_orders_list()
        assert isinstance(result, list)


class TestPurchaseOrders:
    def test_create_requires_items(self):
        from core.sales import purchase_orders_create
        result = purchase_orders_create()
        assert "error" in result


class TestSummary:
    def test_summary_returns_dict(self):
        from core.sales import sales_summary
        result = sales_summary()
        assert "total_sales" in result
        assert "total_orders" in result
