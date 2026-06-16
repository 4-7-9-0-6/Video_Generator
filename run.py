#!/usr/bin/env python3
"""ToonForge one-command launcher.

Frees the ports, starts the backend (FastAPI/uvicorn) + frontend (Next.js), waits for both to be
healthy, opens the browser, and shuts BOTH down cleanly on Ctrl+C — no orphan processes left
serving on a socket. Pure stdlib, cross-platform (Windows / macOS / Linux).

    python run.py                 # start everything, open the browser
    python run.py --no-browser    # don't open the browser
    python run.py --backend-port 8001
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
IS_WIN = os.name == "nt"
FRONTEND_PORT = 3000   # the frontend's package.json dev script binds 3000

# The Windows console defaults to cp1252, which can't encode emoji/box chars and would crash
# print(). Switch our streams to UTF-8 (errors='replace' so it can never raise).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 — non-reconfigurable stream: fall through
        pass


def _venv_python() -> str:
    cand = BACKEND / ".venv" / ("Scripts/python.exe" if IS_WIN else "bin/python")
    return str(cand) if cand.exists() else sys.executable


def _pids_on_port(port: int) -> set[int]:
    pids: set[int] = set()
    try:
        if IS_WIN:
            # decode with errors='ignore' — netstat output can contain bytes the cp1252 default
            # can't decode (e.g. 0x90), which would otherwise crash the reader thread
            out = subprocess.run(["netstat", "-ano"], capture_output=True,
                                 text=True, errors="ignore").stdout
            for line in out.splitlines():
                if f":{port} " in line and "LISTENING" in line.upper():
                    tail = line.split()[-1]
                    if tail.isdigit():
                        pids.add(int(tail))
        else:
            out = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                                 capture_output=True, text=True, errors="ignore").stdout
            pids = {int(x) for x in out.split() if x.isdigit()}
    except Exception:  # noqa: BLE001 — tool missing / odd output: treat as nothing to kill
        pass
    return pids


def _kill(pid: int) -> None:
    try:
        if IS_WIN:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
        else:
            os.kill(pid, signal.SIGKILL)
    except Exception:  # noqa: BLE001
        pass


def _kill_uvicorn_orphans() -> None:
    """Windows fallback: an orphaned `uvicorn --reload` child can keep serving on an inherited
    socket while netstat reports a *dead* parent PID, so killing the netstat PID doesn't free it.
    Sweep python processes that are running OUR backend (matched by command line)."""
    if not IS_WIN:
        return
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
          "Where-Object { $_.CommandLine -match 'uvicorn|app.main' } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True)
    except Exception:  # noqa: BLE001
        pass


def free_port(port: int, label: str) -> None:
    for _ in range(4):
        pids = _pids_on_port(port)
        if not pids:
            return
        print(f"  freeing :{port} ({label}) — stopping {sorted(pids)}")
        for pid in pids:
            _kill(pid)
        time.sleep(0.7)
    if _pids_on_port(port):
        _kill_uvicorn_orphans()
        time.sleep(0.7)
    if _pids_on_port(port):
        print(f"  ⚠️  :{port} is still in use — close it manually (or reboot) and retry.")


def wait_healthy(url: str, timeout: float = 45.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status < 500:
                    return True
        except Exception:  # noqa: BLE001 — not up yet
            time.sleep(0.6)
    return False


def _spawn(args, cwd: Path, env: dict | None = None, shell: bool = False) -> subprocess.Popen:
    kw: dict = {"cwd": str(cwd), "env": env}
    if IS_WIN:
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP   # isolate from our Ctrl+C
    else:
        kw["start_new_session"] = True                              # own process group
    return subprocess.Popen(args, shell=shell, **kw)


def start_backend(port: int) -> subprocess.Popen:
    # no --reload: it spawns a child that can orphan onto the socket on Windows
    return _spawn([_venv_python(), "-m", "uvicorn", "app.main:app",
                   "--host", "127.0.0.1", "--port", str(port)],
                  cwd=BACKEND, env={**os.environ})


def start_frontend(backend_port: int) -> subprocess.Popen:
    env = {**os.environ, "NEXT_PUBLIC_API_BASE": f"http://localhost:{backend_port}"}
    if IS_WIN:
        return _spawn("npm run dev", cwd=FRONTEND, env=env, shell=True)   # npm is a .cmd
    return _spawn(["npm", "run", "dev"], cwd=FRONTEND, env=env)


def stop(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        if IS_WIN:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:  # noqa: BLE001
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Run ToonForge (backend + frontend) with one command.")
    ap.add_argument("--backend-port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()

    if not (FRONTEND / "node_modules").exists():
        print("❌ frontend/node_modules missing — run `npm install` in frontend/ first.")
        return 1
    if not (BACKEND / ".venv").exists():
        print("⚠️  backend/.venv missing — using system Python (deps may be absent).")

    print("🎬 ToonForge launcher\n  freeing ports…")
    free_port(a.backend_port, "backend")
    free_port(FRONTEND_PORT, "frontend")

    print("  starting backend + frontend…")
    be = start_backend(a.backend_port)
    fe = start_frontend(a.backend_port)

    backend_url = f"http://127.0.0.1:{a.backend_port}"
    frontend_url = f"http://localhost:{FRONTEND_PORT}"
    print("  waiting for backend…", "ready ✅" if wait_healthy(backend_url + "/health")
          else "TIMEOUT ⚠️  (check the log above)")
    print("  waiting for frontend…", "ready ✅" if wait_healthy(frontend_url)
          else "still compiling… (it'll come up shortly)")

    print(f"\n  ✅ ToonForge is up →  {frontend_url}")
    print(f"     backend API     →  {backend_url}")
    print("  Press Ctrl+C to stop both cleanly.\n")
    if not a.no_browser:
        try:
            webbrowser.open(frontend_url)
        except Exception:  # noqa: BLE001
            pass

    try:
        while True:
            if be.poll() is not None:
                print("⚠️  backend process exited — stopping.")
                break
            if fe.poll() is not None:
                print("⚠️  frontend process exited — stopping.")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  stopping…")
    finally:
        stop(fe)
        stop(be)
        print("  stopped. 👋")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
