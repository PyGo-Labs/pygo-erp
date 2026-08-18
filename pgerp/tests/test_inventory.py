"""Tests for Inventory module."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


class TestWarehouse:
    def test_warehouse_fields(self):
        from core.inventory import warehouses_create
        assert callable(warehouses_create)
    
    def test_stock_transfer_requires_params(self):
        from core.inventory import stock_transfer
        result = stock_transfer()
        assert "error" in result
    
    def test_stock_adjust_requires_params(self):
        from core.inventory import stock_adjust
        result = stock_adjust()
        assert "error" in result


class TestCategories:
    def test_create_category(self):
        from core.inventory import categories_create
        assert callable(categories_create)


class TestStockAlerts:
    def test_alerts_returns_list(self):
        from core.inventory import stock_alerts
        result = stock_alerts()
        assert isinstance(result, list)


class TestMovements:
    def test_movements_returns_list(self):
        from core.inventory import stock_movements
        result = stock_movements()
        assert isinstance(result, list)
