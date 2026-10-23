"""Run isolation, truthful status reporting and offline-only acceptance jobs."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import stage3_jobs as jobs


def summary(task="task01", scores=None):
    config = jobs.TASKS[task]
    return {"as_of": config["as_of"], "within_timeout": True, "mode": "DAILY_OHLC_APPROX",
            "coverage_complete": True, "elapsed_seconds": 1.5,
            config["grade"]: {"task_id": config["id"], "commit": jobs.COMMIT,
                              "task_file_sha256": jobs.SHA256, "llm_judge": "NOT_RUN",
                              "overall_score": None,
                              "scores": scores if scores is not None else {key: 1.0 for key in config["checks"]}}}


class Stage3JobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.data = Path(self.tmp.name)
        self.contract = patch.object(jobs, "load_task", return_value={})
        self.contract.start()
        self.addCleanup(self.contract.stop)

    def tearDown(self):
        self.assertTrue(self.data.resolve().is_relative_to(Path(__file__).resolve().parent))
        self.tmp.cleanup()

    def write_outputs(self, directory, task="task01", payload=None):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "summary.json").write_text(
            json.dumps(payload if payload is not None else summary(task)), encoding="utf-8")
        (directory / jobs.TASKS[task]["output"]).write_text("真实结果\n", encoding="utf-8")

    def completed(self, command, **kwargs):
        task = "task01" if "validate_task01.py" in command[1] else "task36"
        directory = Path(command[command.index(jobs.TASKS[task]["output_flag"]) + 1])
        self.write_outputs(directory, task)
        return subprocess.CompletedProcess(command, 0, "日志\n", "")

    def test_success_uses_fixed_script_no_shell_and_isolates_baseline(self):
        baseline = self.data / "acceptance" / "task01"
        self.write_outputs(baseline)
        old = (baseline / "summary.json").read_bytes()
        with patch.object(jobs.subprocess, "run", side_effect=self.completed) as run:
            result = jobs.run_acceptance("task01", data_dir=self.data)
        self.assertEqual(result["state"], "completed")
        self.assertTrue(result["automated_checks_passed"])
        self.assertEqual(result["llm_judge"], "NOT_RUN")
        self.assertIsNone(result["overall_score"])
        self.assertEqual(result["output_text"], "真实结果\n")
        self.assertIsNotNone(result["finished_at"])
        self.assertEqual(result["input_snapshot"]["generation"], "legacy")
        self.assertEqual(result["task_contract"]["sha256"], jobs.SHA256)
        self.assertEqual(len(result["summary_sha256"]), 64)
        self.assertEqual((baseline / "summary.json").read_bytes(), old)
        args, kwargs = run.call_args
        self.assertEqual(args[0][0], jobs.sys.executable)
        self.assertEqual(Path(args[0][1]), jobs.ROOT / "scripts" / "validate_task01.py")
        self.assertFalse(kwargs["shell"])
        self.assertEqual(kwargs["timeout"], 300)
        self.assertEqual(kwargs["env"]["PYTHONUTF8"], "1")
        self.assertIn("web_runs", result["output_dir"])
        self.assertEqual(jobs.read_run(Path(result["output_dir"]))["state"], "completed")

    def test_missing_contract_records_failure_without_subprocess_or_fetch(self):
        with patch.object(jobs, "load_task", side_effect=FileNotFoundError("missing pinned task file")), \
                patch.object(jobs.subprocess, "run") as run:
            result = jobs.run_acceptance("task01", data_dir=self.data)
        run.assert_not_called()
        self.assertEqual(result["state"], "failed")
        self.assertFalse(result["automated_checks_passed"])
        self.assertIn("准备步骤", result["error"])
        self.assertIn("missing pinned task file", result["log"])

    def test_invalid_task_and_mode_do_not_create_runs(self):
        for task, mode in (("../other.py", "auto"), ("task36", "strictminute"), ("task01", "daily")):
            with self.assertRaises(ValueError):
                jobs.run_acceptance(task, mode, data_dir=self.data)
        self.assertFalse((self.data / "web_runs").exists())

    def test_timeout_retains_prior_success_and_logs_partial_output(self):
        with patch.object(jobs.subprocess, "run", side_effect=self.completed):
            first = jobs.run_acceptance("task36", data_dir=self.data)
        with patch.object(jobs.subprocess, "run", side_effect=subprocess.TimeoutExpired(
                ["python"], 480, output="部分日志".encode(), stderr=b"timed out")):
            second = jobs.run_acceptance("task36", data_dir=self.data)
        self.assertEqual(second["state"], "timeout")
        self.assertFalse(second["automated_checks_passed"])
        self.assertIn("部分日志", second["log"])
        self.assertNotEqual(first["output_dir"], second["output_dir"])
        self.assertEqual(jobs.read_run(Path(first["output_dir"]))["state"], "completed")
        self.assertEqual([row["state"] for row in jobs.list_runs("task36", data_dir=self.data)],
                         ["timeout", "completed"])

    def test_nonzero_exit_with_summary_is_failed(self):
        def failure(command, **kwargs):
            self.completed(command, **kwargs)
            return subprocess.CompletedProcess(command, 1, "", "source failed")
        with patch.object(jobs.subprocess, "run", side_effect=failure):
            result = jobs.run_acceptance("task01", data_dir=self.data)
        self.assertEqual(result["state"], "failed")
        self.assertIsNotNone(result["summary"])
        self.assertFalse(result["automated_checks_passed"])

    def test_zero_exit_without_summary_is_failed(self):
        with patch.object(jobs.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")):
            result = jobs.run_acceptance("task01", data_dir=self.data)
        self.assertEqual(result["state"], "failed")
        self.assertFalse(result["automated_checks_passed"])
        self.assertIn("summary.json", result["error"])
        self.assertIsNone(result["output_text"])

    def test_valid_empty_output_is_distinct_from_missing_output(self):
        directory = self.data / "acceptance" / "task01"
        self.write_outputs(directory)
        (directory / "result.txt").write_text("", encoding="utf-8")
        result = jobs.read_existing("task01", data_dir=self.data)
        self.assertEqual(result["output_text"], "")

    def test_changed_summary_is_not_a_verified_completed_run(self):
        with patch.object(jobs.subprocess, "run", side_effect=self.completed):
            first = jobs.run_acceptance("task01", data_dir=self.data)
        path = Path(first["output_dir"]) / "summary.json"
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        result = jobs.read_run(Path(first["output_dir"]))
        self.assertEqual(result["state"], "failed")
        self.assertFalse(result["automated_checks_passed"])
        self.assertIn("哈希不一致", result["error"])

    def test_strict_minute_failure_never_invokes_daily(self):
        with patch.object(jobs.subprocess, "run", return_value=subprocess.CompletedProcess(
                [], 1, "", "IntradayCoverageError")) as run:
            result = jobs.run_acceptance("task36", "minute", data_dir=self.data)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][-2:], ["--mode", "minute"])
        self.assertEqual(run.call_args.kwargs["timeout"], 480)
        self.assertIn("未降级", result["error"])

    def test_strict_minute_cannot_accept_a_silent_daily_fallback(self):
        with patch.object(jobs.subprocess, "run", side_effect=self.completed):
            result = jobs.run_acceptance("task36", "minute", data_dir=self.data)
        self.assertEqual(result["state"], "failed")
        self.assertFalse(result["automated_checks_passed"])
        self.assertIn("返回了日线近似", result["error"])

    def test_partial_scores_do_not_mean_all_checks_passed(self):
        directory = self.data / "acceptance" / "task01"
        for scores in ({"file_created": 1.0}, {key: 0.0 for key in jobs.TASKS["task01"]["checks"]}):
            self.write_outputs(directory, payload=summary(scores=scores))
            result = jobs.read_existing("task01", data_dir=self.data)
            self.assertEqual(result["state"], "completed")
            self.assertFalse(result["automated_checks_passed"])

    def test_existing_reports_read_without_running_or_modifying(self):
        self.assertIsNone(jobs.read_existing("task01", data_dir=self.data))
        directory = self.data / "acceptance" / "task01"
        self.write_outputs(directory)
        before = (directory / "summary.json").read_bytes()
        with patch.object(jobs.subprocess, "run") as run:
            result = jobs.read_existing("task01", data_dir=self.data)
        run.assert_not_called()
        self.assertEqual(result["origin"], "existing_report")
        self.assertEqual(result["elapsed_seconds"], 1.5)
        self.assertTrue(result["automated_checks_passed"])
        self.assertEqual(before, (directory / "summary.json").read_bytes())

    def test_wrong_date_or_unpinned_grade_cannot_pass(self):
        directory = self.data / "acceptance" / "task01"
        bad = summary()
        bad["as_of"] = "2026-04-01"
        self.write_outputs(directory, payload=bad)
        self.assertEqual(jobs.read_existing("task01", data_dir=self.data)["state"], "failed")
        bad = summary()
        bad["grading"]["task_file_sha256"] = "unknown"
        self.write_outputs(directory, payload=bad)
        self.assertFalse(jobs.read_existing("task01", data_dir=self.data)["automated_checks_passed"])

    def test_missing_or_corrupt_status_never_becomes_success(self):
        directory = self.data / "web_runs" / "task01-20260101-abc"
        self.write_outputs(directory)
        self.assertEqual(jobs.read_run(directory)["state"], "failed")
        (directory / "status.json").write_text("broken", encoding="utf-8")
        self.assertEqual(jobs.read_run(directory)["state"], "failed")

    def test_list_is_newest_first_and_limited_to_twenty(self):
        for number in range(25):
            directory = self.data / "web_runs" / f"task01-{number:04d}-test"
            directory.mkdir(parents=True)
        rows = jobs.list_runs("task01", data_dir=self.data)
        self.assertEqual(len(rows), 20)
        self.assertTrue(rows[0]["run_id"].startswith("task01-0024"))
        self.assertTrue(rows[-1]["run_id"].startswith("task01-0005"))


if __name__ == "__main__":
    unittest.main()
