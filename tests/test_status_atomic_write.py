"""Status updates survive brief Windows read locks and retain hard failures."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import stage3_jobs as jobs


def test_transient_status_lock_keeps_atomic_updates(tmp_path):
    original = Path.replace
    attempts = []
    def replace(source, target):
        attempts.append(source)
        if len(attempts) < 3:
            raise PermissionError("brief reader lock")
        return original(source, target)
    with patch.object(Path, "replace", autospec=True, side_effect=replace), patch.object(jobs.time, "sleep"):
        jobs._write_status(tmp_path, {"state": "completed"})
    assert len(attempts) == 3
    assert json.loads((tmp_path / "status.json").read_text()) == {"state": "completed"}


def test_permanent_status_failure_is_not_swallowed(tmp_path):
    with patch.object(Path, "replace", side_effect=PermissionError("persistent lock")) as replace, patch.object(jobs.time, "sleep"):
        with pytest.raises(PermissionError):
            jobs._write_status(tmp_path, {"state": "completed"})
    assert replace.call_count == 6
    assert not (tmp_path / "status.json").exists()
