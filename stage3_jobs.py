"""Run the two fixed offline acceptance scripts without replacing baseline reports."""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys
import time
import uuid

import market_snapshot as ms
from scripts.realfin_contract import COMMIT, SHA256, load_task

ROOT = Path(__file__).resolve().parent
SHANGHAI = timezone(timedelta(hours=8))
TASKS = {
    "task01": {"id": "task_01_macd_rsi_filter", "script": "validate_task01.py",
               "as_of": "2026-03-31", "timeout": 300, "output": "result.txt",
               "grade": "grading", "output_flag": "--output-dir",
               "checks": {"file_created", "valid_codes", "count_limit", "data_fetched",
                          "macd_computed", "rsi_computed", "ma_computed"}},
    "task36": {"id": "task_36_intraday_anomaly", "script": "validate_task36.py",
               "as_of": "2024-08-22", "timeout": 480, "output": "intraday_signal.txt",
               "grade": "official_automated_grade", "output_flag": "--out-dir",
               "checks": {"file_created", "anomaly_type", "intraday_attempted",
                          "closing_position", "continuation_field"}},
}


def _config(task: str) -> dict:
    if task not in TASKS:
        raise ValueError("task must be task01 or task36")
    return TASKS[task]


def _write_status(directory: Path, status: dict) -> None:
    temporary = directory / "status.json.tmp"
    temporary.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(directory / "status.json")


def _text(value) -> str:
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else (value or "")


def _summary_error(summary: dict | None, config: dict) -> str | None:
    if not isinstance(summary, dict) or not summary:
        return "未生成有效的 summary.json；不能认定验收完成。"
    if summary.get("as_of") != config["as_of"]:
        return "结果基准日与固定题目不一致。"
    grade = summary.get(config["grade"])
    if not isinstance(grade, dict):
        return "结果缺少官方自动评分记录。"
    if (grade.get("task_id") != config["id"] or grade.get("commit") != COMMIT
            or grade.get("task_file_sha256") != SHA256):
        return "评分版本与固定题目不一致。"
    if grade.get("llm_judge") != "NOT_RUN" or grade.get("overall_score") is not None:
        return "该页面仅展示自动检查；结果包含不适用的完整评分声明。"
    if summary.get("within_timeout") is not True:
        return "验收结果未确认在题目时限内完成。"
    if config["id"] == TASKS["task01"]["id"] and summary.get("coverage_complete") is not True:
        return "日线股票覆盖不完整；不能认定验收完成。"
    return None


def _read(directory: Path, task: str, status: dict) -> dict:
    config = _config(task)
    errors, summary, output, summary_hash = [], None, None, None
    try:
        content = (directory / "summary.json").read_bytes()
        summary_hash = hashlib.sha256(content).hexdigest()
        summary = json.loads(content.decode("utf-8"))
        if not isinstance(summary, dict):
            summary = None
        expected_hash = status.get("summary_sha256")
        if expected_hash and summary_hash != expected_hash:
            errors.append("验收摘要与运行完成时的哈希不一致，文件可能已被修改。")
    except (OSError, ValueError) as exc:
        errors.append(f"无法读取验收摘要：{exc}")
    try:
        output = (directory / config["output"]).read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        errors.append(f"无法读取结果文件：{exc}")
    validation_error = _summary_error(summary, config)
    if validation_error:
        errors.append(validation_error)
    if task == "task36" and summary:
        actual_mode = summary.get("mode")
        if actual_mode not in {"MINUTE_30", "DAILY_OHLC_APPROX"}:
            errors.append("task_36 结果缺少真实分钟或日线近似的明确标记。")
        elif status.get("mode") == "minute" and actual_mode != "MINUTE_30":
            errors.append("严格分钟模式返回了日线近似；不能认定验收完成。")
        elif status.get("mode") == "daily" and actual_mode != "DAILY_OHLC_APPROX":
            errors.append("结果与请求的日线近似模式不一致。")
    state = status.get("state", "failed")
    if state not in {"completed", "failed", "timeout"}:
        state = "failed"
        errors.append("运行状态无效。")
    if state == "completed" and (status.get("returncode") != 0 or errors):
        state = "failed"
        if status.get("returncode") != 0:
            errors.append("验收进程未正常退出。")
    grade = summary.get(config["grade"], {}) if summary else {}
    scores = grade.get("scores", {}) if isinstance(grade, dict) else {}
    checks_passed = (
        state == "completed" and isinstance(scores, dict)
        and set(scores) == config["checks"]
        and all(isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value) and value == 1 for value in scores.values())
    )
    try:
        log = (directory / "run.log").read_text(encoding="utf-8")
    except (OSError, ValueError):
        log = ""
    return {
        **status, "task": task, "run_id": status.get("run_id", directory.name),
        "state": state, "output_dir": str(directory.resolve()),
        "summary": summary, "output_text": output, "log": log,
        "error": status.get("error") or ("；".join(errors) if errors else None),
        "started_at": status.get("started_at"),
        "finished_at": status.get("finished_at"),
        "elapsed_seconds": status.get("elapsed_seconds"),
        "input_snapshot": status.get("input_snapshot"),
        "task_contract": status.get("task_contract", {
            "task_id": config["id"], "commit": COMMIT, "sha256": SHA256}),
        "summary_sha256": summary_hash,
        "automated_checks_passed": bool(checks_passed),
        "llm_judge": "NOT_RUN", "overall_score": None,
    }


def read_run(run_dir: Path) -> dict:
    """Read one saved run; a missing/corrupt status can never become a success."""
    directory = Path(run_dir)
    task = directory.name.split("-", 1)[0]
    _config(task)
    try:
        status = json.loads((directory / "status.json").read_text(encoding="utf-8"))
        if not isinstance(status, dict) or status.get("task") != task:
            raise ValueError("status/task mismatch")
    except (OSError, ValueError) as exc:
        status = {"state": "failed", "error": f"无法读取运行状态：{exc}"}
    return _read(directory, task, status)


def list_runs(task: str, *, data_dir: Path = ms.DATA_DIR) -> list[dict]:
    """Newest first, at most 20 runs. Read-only; never reruns a validator."""
    _config(task)
    directory = Path(data_dir) / "web_runs"
    paths = sorted((path for path in directory.glob(f"{task}-*") if path.is_dir()), reverse=True)
    return [read_run(path) for path in paths[:20]]


def read_existing(task: str, *, data_dir: Path = ms.DATA_DIR) -> dict | None:
    """Read the original acceptance report, without modifying or claiming a new run."""
    _config(task)
    directory = Path(data_dir) / "acceptance" / task
    if not directory.exists():
        return None
    status = {"task": task, "run_id": f"existing-{task}", "state": "completed",
              "returncode": 0, "started_at": None, "elapsed_seconds": None,
              "finished_at": None, "input_snapshot": None,
              "error": None, "origin": "existing_report"}
    result = _read(directory, task, status)
    if result["summary"]:
        result["elapsed_seconds"] = result["summary"].get("elapsed_seconds")
    return result


def run_acceptance(task: str, mode: str = "auto", *, data_dir: Path = ms.DATA_DIR) -> dict:
    """Run a fixed offline script synchronously with a hard subprocess timeout.

    completed means the process and its artifacts completed successfully. It does
    not mean every automatic check passed, nor that a hybrid LLM judge was run.
    """
    config = _config(task)
    if mode not in {"auto", "minute", "daily"} or (task == "task01" and mode != "auto"):
        raise ValueError("task36 mode must be auto/minute/daily; task01 only accepts auto")
    data_dir = Path(data_dir).resolve()
    now = datetime.now(SHANGHAI)
    run_id = f"{task}-{now.strftime('%Y%m%dT%H%M%S%f')}-{uuid.uuid4().hex[:8]}"
    directory = data_dir / "web_runs" / run_id
    directory.mkdir(parents=True)
    status = {"task": task, "mode": mode, "run_id": run_id, "state": "failed",
              "output_dir": str(directory), "started_at": now.isoformat(timespec="seconds"),
              "elapsed_seconds": None, "finished_at": None, "returncode": None,
              "input_snapshot": None, "summary_sha256": None,
              "task_contract": {"task_id": config["id"], "commit": COMMIT, "sha256": SHA256},
              "error": "尚未记录完成结果；若运行被中断，可查看日志并重新运行。"}
    _write_status(directory, status)
    started, log = time.perf_counter(), ""
    try:
        # The fixed scripts use the repository's pinned local contract cache.
        # Never fetch it, run a shell, download market data, or invoke a model here.
        load_task(config["id"])
        paths = ms.snapshot_paths(data_dir)
        generation = paths["bars"].parent.relative_to(data_dir).as_posix()
        status["input_snapshot"] = {
            "generation": "legacy" if generation == "." else generation,
            "meta_sha256": (hashlib.sha256(paths["meta"].read_bytes()).hexdigest()
                            if paths["meta"].exists() else None),
            "captured_at": datetime.now(SHANGHAI).isoformat(timespec="seconds"),
        }
        command = [sys.executable, str(ROOT / "scripts" / config["script"]),
                   "--data-dir", str(data_dir), config["output_flag"], str(directory)]
        if task == "task36":
            command += ["--mode", mode]
        completed = subprocess.run(
            command, cwd=ROOT, shell=False, timeout=config["timeout"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
        log = _text(completed.stdout) + _text(completed.stderr)
        status["returncode"] = completed.returncode
        status["state"] = "completed" if completed.returncode == 0 else "failed"
        status["error"] = None if completed.returncode == 0 else (
            "严格分钟验收失败；未降级为日线近似。所需历史分钟缓存或其校验未满足要求。"
            if task == "task36" and mode == "minute"
            else f"验收进程退出码为 {completed.returncode}；请查看运行日志。"
        )
    except subprocess.TimeoutExpired as exc:
        log = _text(exc.stdout) + _text(exc.stderr)
        status.update(state="timeout", error=f"验收超过 {config['timeout']} 秒，已终止本次进程；此前结果保留。")
    except FileNotFoundError as exc:
        status["error"] = "缺少本地题目文件、解释器或脚本；请先完成交接文档中的准备步骤。"
        log = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        status["error"] = f"验收未完成：{type(exc).__name__}: {exc}"
        log = status["error"]
    status["elapsed_seconds"] = round(time.perf_counter() - started, 4)
    status["finished_at"] = datetime.now(SHANGHAI).isoformat(timespec="seconds")
    summary_path = directory / "summary.json"
    if summary_path.exists():
        status["summary_sha256"] = hashlib.sha256(summary_path.read_bytes()).hexdigest()
    (directory / "run.log").write_text(log, encoding="utf-8")
    result = _read(directory, task, status)
    status.update(state=result["state"], error=result["error"])
    _write_status(directory, status)
    return _read(directory, task, status)
