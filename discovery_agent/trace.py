"""Append-only JSONL trace of every LLM call, tool call and HTTP request in a run.

The trace is evidence: the instructor scorer reads it to check guardrails, and you
read it to find out why the agent did what it did.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path


class Trace:
    def __init__(self, path: Path | None):
        self.path = path
        self._lock = threading.Lock()
        self.totals = {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0,
                       "cache_read_input_tokens": 0, "tool_calls": 0, "tool_errors": 0,
                       "http_requests": 0, "http_refused": 0}
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    def event(self, kind: str, **data) -> None:
        record = {"ts": round(time.time(), 3), "kind": kind, **data}
        with self._lock:
            if kind == "llm_call":
                self.totals["llm_calls"] += 1
                for key in ("input_tokens", "output_tokens", "cache_read_input_tokens"):
                    self.totals[key] += int(data.get(key) or 0)
            elif kind == "tool_call":
                self.totals["tool_calls"] += 1
                if not data.get("ok", True):
                    self.totals["tool_errors"] += 1
            elif kind == "http":
                if data.get("refused"):
                    self.totals["http_refused"] += 1
                elif not data.get("from_cache"):
                    self.totals["http_requests"] += 1
            if self.path is not None:
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, default=str) + "\n")
