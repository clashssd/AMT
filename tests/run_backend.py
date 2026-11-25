"""Run the AMT backend as a live server for security auditing.

Usage:
    python tests/run_backend.py
    python tests/run_backend.py --port 8000
"""
import argparse
import os
import sys

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, os.path.abspath(BACKEND_DIR))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    import uvicorn
    import main  # noqa: F401  (the actual FastAPI app)
    uvicorn.run(main.app, host=args.host, port=args.port, log_level="warning")

if __name__ == "__main__":
    main()
