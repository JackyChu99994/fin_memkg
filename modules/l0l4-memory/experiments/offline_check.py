"""Run the module's regression suite without external network access or demo writes."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="fin-memkg-stage5-") as directory:
        isolated = Path(directory)
        for source in ROOT.glob("*.py"):
            shutil.copy2(source, isolated / source.name)
        for name in ("tests", "experiments"):
            shutil.copytree(ROOT / name, isolated / name, ignore=shutil.ignore_patterns("__pycache__"))
        (isolated / "memory").mkdir()
        shutil.copy2(ROOT / "memory" / "L1_concept_index.json", isolated / "memory" / "L1_concept_index.json")
        runner = isolated / "_runner.py"
        runner.write_text("import socket, pytest\n"
                          "def deny(*args, **kwargs):\n    raise OSError('External network disabled for regression')\n"
                          "socket.socket.connect = deny\n"
                          "raise SystemExit(pytest.main(['-q', '-p', 'no:cacheprovider', 'tests']))\n", encoding="utf-8")
        result = subprocess.run([sys.executable, str(runner)], cwd=isolated,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}, timeout=180)
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
