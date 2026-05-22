"""Small opt-in JSONL traces for hard-to-reproduce UI state bugs."""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone

from src.paths import get_project_root


def trace_floating_state(event: str, **fields) -> None:
    """Append one floating-control debug event when VOX_FLOATING_TRACE=1."""
    if os.environ.get("VOX_FLOATING_TRACE") != "1":
        return

    try:
        data_dir = get_project_root() / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir / "floating_state_debug.jsonl"
        thread = threading.current_thread()
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "mono": round(time.monotonic(), 6),
            "pid": os.getpid(),
            "thread": thread.name,
            "thread_id": threading.get_ident(),
            "event": event,
            **fields,
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass
