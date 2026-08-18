"""Tests for CRM module."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


class TestLeads:
    def test_create_requires_name(self):
        from core.crm import leads_create
        result = leads_create()
        assert "error" in result
    
    def test_list_returns_list(self):
        from core.crm import leads_list
        result = leads_list()
        assert isinstance(result, list)


class TestOpportunities:
    def test_create_requires_name(self):
        from core.crm import opportunities_create
        result = opportunities_create()
        assert "error" in result
    
    def test_pipeline_summary(self):
        from core.crm import pipeline_summary
        result = pipeline_summary()
        assert isinstance(result, list)


class TestFunnel:
    def test_funnel_returns_dict(self):
        from core.crm import pipeline_funnel
        result = pipeline_funnel()
        assert "totals" in result
        assert "leads_by_status" in result
