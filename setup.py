#!/usr/bin/env python3
"""AMT Chat — Python setup script.

Usage:
    python setup.py

Creates backend/.venv and installs requirements.txt into it.

Notes on robustness:
- On corporate machines with Windows Defender Application Control (WDAC)
  enabled, `venv.create(..., with_pip=True)` fails because Python 3.12+
  implements it via `python -m ensurepip` which spawns a child process
  that WDAC blocks (WinError 4551). We work around this by creating the
  venv without pip and then installing pip manually from the
  `ensurepip._bundled` wheel shipped with the Python distribution.
- The bundled-wheel install does NOT call `ensurepip` — it runs pip's
  `runpy` entry point directly, so WDAC-managed machines can still
  bootstrap pip.
"""
import importlib.resources
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import venv

ROOT = pathlib.Path(__file__).parent
VENV = ROOT / "backend" / ".venv"
REQ = ROOT / "requirements.txt"


def _scripts_dir() -> pathlib.Path:
    return VENV / ("Scripts" if sys.platform == "win32" else "bin")


def _venv_python() -> pathlib.Path:
    return _scripts_dir() / ("python.exe" if sys.platform == "win32" else "python3")


def _venv_pip() -> pathlib.Path:
    return _scripts_dir() / ("pip.exe" if sys.platform == "win32" else "pip")


def _pip_wheel_path() -> "pathlib.Path | None":
    """Return the path to the pip wheel bundled with this Python install.

    Returns None when the wheel cannot be located (e.g. system Python
    distribution without ensurepip._bundled).
    """
    try:
        bundled = importlib.resources.files("ensurepip").joinpath("_bundled")
    except (ModuleNotFoundError, OSError):
        return None
    candidates = sorted(bundled.glob("pip-*.whl"))
    return candidates[-1] if candidates else None


def _install_pip_into_venv() -> None:
    """Bootstrap pip into the freshly created venv.

    Strategy (most to least preferred):
    1. Run the venv's own `python -m ensurepip` — works on unmanaged
       machines; on WDAC-managed machines this is the one that fails
       with WinError 4551, so we only use it as a probe.
    2. If that fails, install pip directly from the bundled wheel using
       the venv's python. This does not invoke `ensurepip` and does not
       spawn a child process that WDAC can block, so it works on the
       same managed machines.
    """
    # 1) Probe ensurepip — most systems are fine.
    try:
        subprocess.run(
            [str(_venv_python()), "-m", "ensurepip", "--upgrade", "--default-pip"],
            check=True,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        print("pip installed via ensurepip")
        return
    except subprocess.CalledProcessError as e:
        print(
            f"[setup.py] ensurepip failed (exit {e.returncode}). "
            f"Trying bundled wheel install (WDAC-safe path).",
            file=sys.stderr,
        )
        if e.stderr:
            for line in e.stderr.strip().splitlines()[-5:]:
                print(f"  {line}", file=sys.stderr)

    # 2) Install pip from the bundled wheel directly.
    wheel = _pip_wheel_path()
    if wheel is None:
        raise RuntimeError(
            "ensurepip failed AND no bundled pip wheel was found in the "
            "Python distribution. Cannot bootstrap pip. "
            "Fix: install a full Python 3.12+ from python.org (the "
            "standard installer includes ensurepip._bundled)."
        )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        tmp_wheel = tmp_path / wheel.name
        shutil.copy2(wheel, tmp_wheel)

        pip_exe = _venv_pip()
        if pip_exe.exists():
            # A previous partial run already produced a pip.exe — reuse it.
            subprocess.check_call(
                [
                    str(pip_exe),
                    "install",
                    "--no-cache-dir",
                    "--no-index",
                    "--find-links",
                    str(tmp_path),
                    str(tmp_wheel),
                ]
            )
        else:
            # No pip.exe yet — bootstrap it from the wheel using the
            # venv's own python interpreter, without calling ensurepip.
            code = (
                "import runpy, sys\n"
                f"sys.path.insert(0, r'{tmp_path}')\n"
                "sys.argv = ['pip', 'install', '--no-cache-dir', '--no-index',\n"
                f"            '--find-links', r'{tmp_path}',\n"
                f"            r'{tmp_wheel.name}', 'pip']\n"
                "runpy.run_module('pip', run_name='__main__', alter_sys=True)\n"
            )
            subprocess.check_call(
                [str(_venv_python()), "-W", "ignore", "-c", code],
                env=os.environ.copy(),
            )
    print(f"pip installed from bundled wheel: {wheel.name}")


def main():
    ver = sys.version_info
    print(f"Python {ver.major}.{ver.minor}.{ver.micro}")
    if ver < (3, 12):
        print("ERROR: Python 3.12+ required. Install from https://www.python.org")
        sys.exit(1)

    if not REQ.exists():
        print(f"ERROR: {REQ} not found")
        sys.exit(1)

    pip = _venv_pip()

    if not VENV.exists():
        print(f"Creating venv at {VENV} (without pip — we bootstrap it manually)…")
        # NOTE: with_pip=False on purpose — on WDAC-managed machines
        # Python 3.12+ implements `with_pip=True` via `python -m ensurepip`
        # which spawns a child process that the policy blocks (WinError 4551).
        venv.create(VENV, with_pip=False)
        _install_pip_into_venv()
    elif not pip.exists():
        print("pip missing from existing venv — bootstrapping it…")
        _install_pip_into_venv()

    print("Installing requirements …")
    subprocess.check_call([str(pip), "install", "-r", str(REQ)])

    print("[OK] Python setup complete")
    print(f"  venv: {VENV}")
    print(f"  next: node setup.js  (Node/Electron)")


if __name__ == "__main__":
    main()
