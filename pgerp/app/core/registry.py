"""PyGo ERP V2.0 — Shared handler registry.

This module exists to prevent circular imports.
All modules import HANDLERS and register from here.
"""
HANDLERS = {}

def register(name):
    """Decorator to register a handler by qualified name."""
    def decorator(func):
        HANDLERS[name] = func
        return func
    return decorator
