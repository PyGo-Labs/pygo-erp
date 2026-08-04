"""PyGo ERP entry point — PyGo runtime client.

Connects to the Go supervisor via UDS and serves handlers
registered in the transpiled gen_py.py.
"""
import sys
import os

# Ensure framework root is in PYTHONPATH (set by pygo dev)
framework_root = os.environ.get("PYGO_HOME", ".")
if framework_root not in sys.path:
    sys.path.insert(0, framework_root)

# Ensure .pygo-gen is in path for gen_py.py
gen_dir = os.path.join(os.path.dirname(__file__), ".pygo-gen")
if os.path.isdir(gen_dir) and gen_dir not in sys.path:
    sys.path.insert(0, gen_dir)

# Import generated handlers — this registers HANDLERS dict
from gen_py import *  # noqa: F401,F403

# Import pyclient and start serving
from core.runtime.pyclient import main, HANDLERS

if __name__ == "__main__":
    if not HANDLERS:
        print("pygo: no handlers registered in gen_py.py", file=sys.stderr)
        sys.exit(1)
    print(f"pygo: {len(HANDLERS)} handlers registered: {list(HANDLERS.keys())}", file=sys.stderr)
    main()
