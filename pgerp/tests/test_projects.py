"""Tests for Projects module."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


class TestProjects:
    def test_create_requires_name(self):
        from core.projects import projects_create
        result = projects_create()
        assert "error" in result
    
    def test_list_returns_list(self):
        from core.projects import projects_list
        result = projects_list()
        assert isinstance(result, list)


class TestTasks:
    def test_create_requires_project_and_title(self):
        from core.projects import tasks_create
        result = tasks_create()
        assert "error" in result
    
    def test_complete_requires_task_id(self):
        from core.projects import tasks_complete
        result = tasks_complete()
        assert "error" in result


class TestTimesheets:
    def test_create_requires_task_and_hours(self):
        from core.projects import timesheets_create
        result = timesheets_create()
        assert "error" in result


class TestDashboard:
    def test_dashboard_returns_dict(self):
        from core.projects import projects_dashboard
        result = projects_dashboard()
        assert "total_projects" in result
        assert "total_tasks" in result
