"""Package task-two evidence and source code through an explicit secret-free allowlist."""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import zipfile
from pathlib import Path

from experiments.common import ROOT, REPO, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Use a new package path")
    run = args.run.resolve()
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    candidates = [run / name for name in ("manifest.json", "records.jsonl", "summary.json", "episodes.jsonl", "comparison.csv")]
    candidates.append(run.with_suffix(".plan.json"))
    candidates += [Path(path) for path in manifest["input_sha256"]]
    corpus_parent = next(Path(path).parent for path in manifest["input_sha256"] if Path(path).name == "corpus.jsonl")
    candidates.append(corpus_parent / "annotation-user-reviewed-v1-manifest.json")
    for path in candidates:
        if not path.is_file():
            raise ValueError("Required evidence file is missing")
        if str(path) in manifest["input_sha256"] and sha256(path) != manifest["input_sha256"][str(path)]:
            raise ValueError("Input changed after experiment; do not package a mismatched reference")
    for name in ("config.py", "pipeline.py", "store.py", "l0_rules.py", "l1_router.py", "l4_archive.py", "market_bridge.py", "thesis_scope.py", "evidence_retrieval.py", "requirements.txt"):
        candidates.append(ROOT / name)
    candidates += sorted((ROOT / "experiments").glob("*.py"))
    candidates += [ROOT / "tests" / name for name in ("test_stage5_evaluation.py", "test_rag_comparison.py")]
    candidates += [ROOT / "memory" / "L1_concept_index.json"]
    candidates += [ROOT / "docs" / name for name in ("stage5-rag-protocol.md", "stage5-rag-results.md", "stage5-user-review-status.md")]
    secrets = []
    for config in (ROOT / ".env", REPO / ".env"):
        if config.exists():
            for line in config.read_text(encoding="utf-8-sig").splitlines():
                if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    if any(word in key.upper() for word in ("KEY", "TOKEN", "PASSWORD", "SECRET")):
                        value = value.strip().strip("\"'")
                        if len(value) >= 8:
                            secrets.append(value.encode())
    entries = []
    for path in sorted(set(p.resolve() for p in candidates)):
        if not path.is_relative_to(REPO.resolve()) or path.name.startswith(".env"):
            raise ValueError("Package candidates must remain inside the repository and exclude environment files")
        content = path.read_bytes()
        if any(secret in content for secret in secrets):
            raise ValueError("Secret material detected in package candidate")
        entries.append((path, "fin_memkg/" + path.relative_to(REPO.resolve()).as_posix(), content))
    versions = {name: importlib.metadata.version(name) for name in ("openai", "pandas", "networkx", "numpy", "pytest", "akshare")}
    receipt = {"python": platform.python_version(), "packages": versions,
        "contents": {name: hashlib.sha256(content).hexdigest() for _, name, content in entries},
        "environment_files_included": False, "local_secret_value_scan_passed": True}
    readme = """# Fin-MemKG task-two reproduction packet

This packet contains source code, the reviewed extraction reference, raw news
excerpts with attribution, derived comparison questions, and saved model outputs.
The source news is provider excerpts, not verified full articles. Keep attribution
when sharing with the course team. No API keys, environment files, virtual
environment, or large market snapshots are included.

The packet contains the evaluation source and its focused tests, rather than
the entire original graphical demonstration. Overlay it on the project repository
to reproduce the full module regression suite.

Read fin_memkg/modules/l0l4-memory/docs/stage5-rag-results.md first, followed by
stage5-rag-protocol.md. Package hashes and runtime versions are in receipt.json.

To reproduce the analysis of saved outputs, install the module requirements,
pytest and pyarrow in Python 3.11, then run experiments.report_rag with the saved
run directory. To rerun live inference, configure QWEN_API_KEY in your local
environment and follow the protocol, using a new output directory. Original
manifests preserve the original machine's paths; locate their corresponding
relative files inside this packet rather than treating those paths as portable.

There are five unique evidence-consistency episodes and three repeats, not
fifteen independent financial events. No improved trading returns, general
memory advantage, or full official RealFin evaluation is claimed.
"""
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.md", readme)
        archive.writestr("receipt.json", json.dumps(receipt, indent=2))
        for _, name, content in entries:
            archive.writestr(name, content)
    with zipfile.ZipFile(args.out) as archive:
        assert archive.testzip() is None
        assert not any(Path(name).name.startswith(".env") for name in archive.namelist())
    print(json.dumps({"package": str(args.out), "files": len(entries) + 2, "bytes": args.out.stat().st_size, "secret_scan_passed": True}))


if __name__ == "__main__":
    main()
