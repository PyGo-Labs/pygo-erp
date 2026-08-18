"""Tests for Reports module."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


class TestDashboard:
    def test_returns_dict(self):
        from core.reports import reports_dashboard
        result = reports_dashboard()
        assert isinstance(result, dict)
        assert "inventory" in result
        assert "sales" in result
        assert "financial" in result
        assert "crm" in result
        assert "projects" in result


class TestSalesReports:
    def test_by_period(self):
        from core.reports import sales_by_period
        result = sales_by_period()
        assert isinstance(result, list)
    
    def test_top_products(self):
        from core.reports import top_products
        result = top_products()
        assert isinstance(result, list)


class TestExport:
    def test_export_requires_type(self):
        from core.reports import report_export
        result = report_export()
        assert "error" in result
    
    def test_export_full(self):
        from core.reports import report_export
        result = report_export(report_type="full")
        assert "data" in result
