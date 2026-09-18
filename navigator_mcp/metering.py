"""Purely local usage stats.

Principles
----------
* **Local only** — counters are stored in a JSON file under the Navigator
  workspace. No URLs, page content, or any other data are ever recorded.
* **For you, not for billing** — this exists so ``usage_report`` can show you
  your own tool usage patterns. Disable with ``NAVIGATOR_STATS=false``.
* **Atomic writes** — stats survive crashes; failed writes never break tools.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CLEAN = lambda obj: obj  # noqa: E731  (kept: no-op sanitizer hook)


class UsageMeter:
    """Thread-safe, process-wide local usage counter store."""

    def __init__(self, path: Path, enabled: bool = True) -> None:
        self.path = Path(path)
        self.enabled = enabled
        self._lock = threading.Lock()
        self._data: dict[str, Any] = self._load()

    # ------------------------------------------------------------------ persistence

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._fresh()
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                return self._fresh()
            data.setdefault("tools", {})
            data.setdefault("days", {})
            data.setdefault("totals", {})
            return data
        except (OSError, json.JSONDecodeError):
            return self._fresh()

    @staticmethod
    def _fresh() -> dict[str, Any]:
        return {
            "schema": 1,
            "install_id": os.urandom(8).hex(),
            "created_at": time.time(),
            "tools": {},   # tool name -> cumulative count
            "days": {},    # YYYY-MM-DD (UTC) -> {tool: count}
            "totals": {    # cumulative aggregates
                "tool_calls": 0,
                "snapshots": 0,
                "snapshot_chars": 0,
                "navigations": 0,
                "captcha_solves": 0,
                "errors": 0,
            },
        }

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=1)
        os.replace(tmp, self.path)

    # ------------------------------------------------------------------ API

    def record(
        self,
        tool: str,
        *,
        ok: bool = True,
        snapshot_chars: int = 0,
        navigation: bool = False,
        captcha: bool = False,
    ) -> None:
        """Record one tool invocation."""
        if not self.enabled:
            return
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._lock:
            self._data["tools"][tool] = self._data["tools"].get(tool, 0) + 1
            day_bucket = self._data["days"].setdefault(day, {})
            day_bucket[tool] = day_bucket.get(tool, 0) + 1
            totals = self._data["totals"]
            totals["tool_calls"] += 1
            if not ok:
                totals["errors"] += 1
            if snapshot_chars:
                totals["snapshots"] += 1
                totals["snapshot_chars"] += snapshot_chars
            if navigation:
                totals["navigations"] += 1
            if captcha:
                totals["captcha_solves"] += 1
            try:
                self._save()
            except OSError:
                pass  # stats must never break a tool call

    def report(self) -> dict[str, Any]:
        """Return an anonymized usage summary (safe to expose to the LLM)."""
        with self._lock:
            return json.loads(json.dumps(self._data))

    def daily_aggregate(self) -> dict[str, Any]:
        """Today's usage aggregate (used by usage_report summaries)."""
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._lock:
            return {
                "day": day,
                "install_id": self._data.get("install_id"),
                "tools": dict(self._data["days"].get(day, {})),
                "totals": dict(self._data["totals"]),
            }
