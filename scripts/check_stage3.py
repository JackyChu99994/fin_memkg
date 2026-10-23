"""Run all offline regressions in an isolated copy so mock responses cannot pollute demo memory."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    started = time.perf_counter()
    isolated = ROOT / "workspace" / f"stage3-regression-{uuid.uuid4().hex[:10]}"
    isolated.mkdir(parents=True)
    paths = list(ROOT.glob("*.py"))
    for folder in ("ga_core", "scripts", "tests"):
        paths += list((ROOT / folder).rglob("*.py"))
    tracked_memory = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "memory"], cwd=ROOT
    ).decode("utf-8").split("\0")
    paths += [ROOT / relative for relative in tracked_memory if relative]
    for source in paths:
        destination = isolated / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    runner = isolated / "_offline_regression.py"
    runner.write_text(
        "import pathlib, socket, tempfile, pytest\n"
        "_original_connect = socket.socket.connect\n"
        "def local_connect(sock, address):\n"
        "    if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1', 'localhost'):\n"
        "        return _original_connect(sock, address)\n"
        "    raise OSError('external network disabled by offline regression runner')\n"
        "if __name__ == '__main__':\n"
        "    tempfile.tempdir = str(pathlib.Path.cwd() / 'tests')\n"
        "    socket.socket.connect = local_connect\n"
        "    raise SystemExit(pytest.main(['-q', '-p', 'no:cacheprovider', '--tb=short', 'tests']))\n",
        encoding="utf-8",
    )
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, "-B", str(runner)], cwd=isolated,
                            env=env, text=True, encoding="utf-8", errors="replace",
                            capture_output=True, timeout=180)
    output = ROOT / "data" / "market" / "acceptance"
    output.mkdir(parents=True, exist_ok=True)
    log = result.stdout + result.stderr
    (output / "regression.txt").write_text(log, encoding="utf-8")
    summary = {"exit_code": result.returncode, "isolated_directory": str(isolated.relative_to(ROOT)),
               "elapsed_seconds": round(time.perf_counter() - started, 3),
               "network": "external connections disabled; loopback allowed for UI tests",
               "live_llm_calls": 0,
               "test_log": "data/market/acceptance/regression.txt"}
    (output / "regression.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(log)
    print(json.dumps(summary, indent=2))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
