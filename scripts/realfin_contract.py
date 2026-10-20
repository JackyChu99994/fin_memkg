"""Pinned, on-demand RealFin task definitions; official files stay in ignored local data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "market" / "benchmark"
COMMIT = "3491965a26bd25798677f89cddfa0f12dc01ce32"
SHA256 = "f6671317c619e141c84fe65f48b98443ccb67677bac34592be9d1d24eb0a30d1"
URL = f"https://raw.githubusercontent.com/JinyiHan99/GA-Technical-Report/{COMMIT}/datasets/realfin_benchmark/tasks_finance.jsonl"
REVIEWED_GRADERS = {"task_01_macd_rsi_filter", "task_36_intraday_anomaly"}


def fetch_contracts(cache_dir: Path = CACHE_DIR) -> dict:
    """Explicit network action, never triggered implicitly during an offline evaluation."""
    with urllib.request.urlopen(URL, timeout=20) as response:
        content = response.read()
    if hashlib.sha256(content).hexdigest() != SHA256:
        raise ValueError("Official task file hash differs from the reviewed version")
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    temporary = cache_dir / "tasks_finance.jsonl.tmp"
    temporary.write_bytes(content)
    os.replace(temporary, cache_dir / "tasks_finance.jsonl")
    source = {"commit": COMMIT, "url": URL, "sha256": SHA256, "task_count": 40}
    (cache_dir / "source.json").write_text(json.dumps(source, indent=2), encoding="utf-8")
    return source


def load_tasks(cache_dir: Path = CACHE_DIR) -> list[dict]:
    path = Path(cache_dir) / "tasks_finance.jsonl"
    if not path.exists():
        raise FileNotFoundError("Run python scripts/realfin_contract.py --fetch once before evaluation")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != SHA256:
        raise ValueError("Task file changed: refusing unreviewed grading code")
    return [json.loads(line) for line in content.decode("utf-8").splitlines() if line.strip()]


def load_task(task_id: str, cache_dir: Path = CACHE_DIR) -> dict:
    return next(task for task in load_tasks(cache_dir) if task["id"] == task_id)


def grade_task(task_id: str, transcript: list, workspace_path: str | Path,
               cache_dir: Path = CACHE_DIR) -> dict:
    """Run only the two manually inspected graders from an exact hash-pinned file."""
    if task_id not in REVIEWED_GRADERS:
        raise ValueError("Only the task_01 and task_36 official grading functions were reviewed")
    task = load_task(task_id, cache_dir)
    namespace: dict = {}
    exec(compile(task["automated_checks"], f"official:{COMMIT}:{task_id}", "exec"), namespace)
    scores = namespace["grade"](transcript, str(Path(workspace_path).resolve()))
    return {
        "task_id": task_id, "commit": COMMIT, "task_file_sha256": SHA256,
        "scores": scores,
        "automated_mean": sum(scores.values()) / len(scores) if scores else None,
        "official_weights": task["grading_weights"],
        "llm_judge": "NOT_RUN",
        "overall_score": None,
        "note": "Mean of automated checks only; not a complete hybrid benchmark score.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    if args.fetch:
        print(json.dumps(fetch_contracts(), indent=2))
    else:
        print(json.dumps({"commit": COMMIT, "tasks": len(load_tasks())}, indent=2))


if __name__ == "__main__":
    main()
