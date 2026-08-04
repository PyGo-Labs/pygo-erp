"""PyGo ERP entry point — loads transpiled code and serves routes."""

import asyncio
import sys
import os

# Ensure generated files are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".pygo-gen"))
sys.path.insert(0, os.path.dirname(__file__))

from gen_py import *  # noqa: F401,F403 — transpiled models
from core.runtime import Server, Router

def main():
    """Entry point for pygo dev."""
    server = Server()
    server.router.register_routes()
    server.serve(host="127.0.0.1", port=8080)

if __name__ == "__main__":
    main()
