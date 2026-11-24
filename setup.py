#!/usr/bin/env python3
"""AMT Chat — Python setup script.

Usage:
    python setup.py

Creates backend/.venv and installs requirements.txt into it.
"""
import subprocess
import sys
import pathlib
import venv

ROOT = pathlib.Path(__file__).parent
VENV = ROOT / "backend" / ".venv"
REQ = ROOT / "requirements.txt"


def main():
    ver = sys.version_info
    print(f"Python {ver.major}.{ver.minor}.{ver.micro}")
    if ver < (3, 12):
        print("ERROR: Python 3.12+ required. Install from https://www.python.org")
        sys.exit(1)

    if not REQ.exists():
        print(f"ERROR: {REQ} not found")
        sys.exit(1)

    if not VENV.exists():
        print(f"Creating venv at {VENV} …")
        venv.create(VENV, with_pip=True)

    pip = VENV / "Scripts" / "pip.exe"
    print("Installing requirements …")
    subprocess.check_call([str(pip), "install", "-r", str(REQ)])

    print("[OK] Python setup complete")
    print(f"  venv: {VENV}")
    print(f"  next: node setup.js  (Node/Electron)")


if __name__ == "__main__":
    main()
