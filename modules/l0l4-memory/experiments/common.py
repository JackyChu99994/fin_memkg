"""Evaluation primitives with explicit provenance and failure accounting."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def read_jsonl(path):
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate document IDs in {path}")
    return rows


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def manifest(paths, **metadata):
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO, text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    # A dirty checkout needs source hashes as well as a base commit identifier.
    sources = sorted((ROOT / "experiments").glob("*.py"))
    sources += sorted(ROOT.glob("*.py"))
    return {"created_at": now(), "commit": commit, "dirty_checkout": dirty,
            "source_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in sources},
            "input_sha256": {str(Path(p).resolve()): sha256(p) for p in paths}, **metadata}


def reviewed_labels(corpus, labels, *, allow_draft=False):
    docs = {row["id"]: row for row in corpus}
    result = {}
    for row in labels:
        if row["id"] not in docs:
            raise ValueError(f"Label has no matching document: {row['id']}")
        expected = hashlib.sha256(docs[row["id"]]["text"].encode()).hexdigest()
        if row.get("text_sha256") != expected:
            raise ValueError(f"Annotation text hash mismatch: {row['id']}")
        if not allow_draft and (row.get("review_status") != "reviewed" or not row.get("reviewer", "").strip()):
            raise ValueError(f"Human review required: {row['id']}; use --allow-draft only for development")
        if not isinstance(row.get("events"), list):
            raise ValueError(f"Missing events list: {row['id']}")
        result[row["id"]] = row
    if set(result) != set(docs):
        raise ValueError("Every corpus document needs exactly one annotation")
    return result


def normalize(value):
    return re.sub(r"\s+", "", str(value)).casefold()


def strict_events(raw):
    text = raw.strip()
    if text.startswith("```json") and text.endswith("```"):
        text = text[7:-3].strip()
    payload = json.loads(text)
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise ValueError("Expected a JSON object with an events list")
    if not all(isinstance(event, dict) for event in payload["events"]):
        raise ValueError("Each event must be a JSON object")
    return payload["events"]


def event_sets(events):
    entities, relations, states = set(), set(), set()
    for event in events:
        source, target = normalize(event["source"]), normalize(event["target"])
        stype, ttype = event.get("source_type", "公司"), event.get("target_type", "公司")
        relation = event["relation"]
        entities.update(((source, stype), (target, ttype)))
        relations.add((source, relation, target))
        states.add((source, relation, target, event.get("status", "发酵中")))
    return {"entities": entities, "relations": relations, "states": states}


def counts(predicted, expected):
    return {"tp": len(predicted & expected), "fp": len(predicted - expected), "fn": len(expected - predicted)}


def prf(tp, fp, fn):
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def extraction_summary(records):
    scores = {}
    for kind in ("entities", "relations", "states"):
        totals = Counter()
        for row in records:
            totals.update(row["counts"][kind])
        scores[kind] = prf(**{key: totals[key] for key in ("tp", "fp", "fn")})
    return {"documents": len(records), "failures": sum(r["status"] != "ok" for r in records),
            "exact_document_accuracy": sum(r["status"] == "ok" and r["exact"] for r in records) / len(records) if records else None,
            "micro": scores,
            "rejected_events": sum(len(r.get("rejected", [])) for r in records),
            "input_tokens": sum(r.get("usage", {}).get("input_tokens", 0) for r in records),
            "output_tokens": sum(r.get("usage", {}).get("output_tokens", 0) for r in records)}


def tokens(text):
    # Character bigrams also support Chinese; these are sparse lexical vectors.
    text = normalize(text)
    return Counter(text[i:i + 2] for i in range(max(0, len(text) - 1)))


def retrieve(query, documents, k=3):
    if k < 1:
        raise ValueError("top-k must be positive")
    vectors = [tokens(doc["text"]) for doc in documents]
    document_frequency = Counter(term for vector in vectors for term in vector)
    idf = {term: math.log((len(vectors) + 1) / (freq + 1)) + 1 for term, freq in document_frequency.items()}
    q = {term: count * idf.get(term, 1.0) for term, count in tokens(query).items()}
    qnorm = math.sqrt(sum(value * value for value in q.values()))
    scored = []
    for doc, vector in zip(documents, vectors):
        v = {term: count * idf[term] for term, count in vector.items()}
        norm = math.sqrt(sum(value * value for value in v.values()))
        score = sum(value * q.get(term, 0) for term, value in v.items()) / (norm * qnorm) if norm and qnorm else 0.0
        scored.append((score, doc["id"], doc))
    return [doc for _, _, doc in sorted(scored, key=lambda item: (-item[0], item[1]))[:k]]


class LiveClient:
    """One provider/model per run. No hidden retry, model switch, or rule fallback."""

    def __init__(self, provider="qwen", model=None):
        # Load the module dotenv, then the repository dotenv, without overwriting env.
        for path in (ROOT / ".env", REPO / ".env"):
            if path.exists():
                for line in path.read_text(encoding="utf-8").splitlines():
                    if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
        prefix = {"qwen": "QWEN", "deepseek": "DEEPSEEK"}[provider]
        key = os.environ.get(prefix + "_API_KEY", "")
        if not key:
            raise ValueError(f"Configure {prefix}_API_KEY in a local .env; no API request was made")
        self.model = model or os.environ.get(prefix + "_MODEL", "qwen-plus" if provider == "qwen" else "deepseek-chat")
        self.base_url = os.environ.get(prefix + "_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1" if provider == "qwen" else "https://api.deepseek.com/v1")
        from openai import OpenAI
        self.client = OpenAI(api_key=key, base_url=self.base_url, timeout=60, max_retries=0)
        self.calls = []

    def chat(self, system, prompt):
        call = {"prompt_sha256": hashlib.sha256((system + "\n" + prompt).encode()).hexdigest(),
                "input_chars": len(system) + len(prompt), "status": "started", "usage": {}}
        self.calls.append(call)
        try:
            response = self.client.chat.completions.create(model=self.model, temperature=0,
                max_tokens=2000, messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}])
            if response.usage:
                call["usage"] = {"input_tokens": response.usage.prompt_tokens, "output_tokens": response.usage.completion_tokens}
            call["response_id"] = response.id
            call["response_model"] = getattr(response, "model", None)
            if response.choices[0].finish_reason != "stop":
                raise ValueError(f"Incomplete output: {response.choices[0].finish_reason}")
            text = response.choices[0].message.content or ""
            call.update(status="ok", raw=text)
            return text
        except Exception as exc:
            # Do not put request headers or credential-bearing URLs in logs.
            call.update(status="failed", error_type=type(exc).__name__)
            raise


def save_run(directory, records, summary, run_manifest):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    write_jsonl(directory / "records.jsonl", records)
    for name, value in (("summary.json", summary), ("manifest.json", run_manifest)):
        (directory / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return directory
