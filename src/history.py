"""
History storage for completed voice input runs.

The store uses JSONL so appending a new item stays cheap and easy to inspect.
Each line is an independent record; malformed lines are ignored when reading.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.logger import setup_logger
from src.paths import get_project_root

log = setup_logger(__name__)


DEFAULT_HISTORY_PATH = get_project_root() / "data" / "history.jsonl"


@dataclass(frozen=True)
class HistoryEntry:
    """One completed speech-to-text output."""

    id: str
    created_at: str
    raw_text: str
    final_text: str
    duration: float
    api_calls: int
    source: str = "audio"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "id": self.id,
            "created_at": self.created_at,
            "raw_text": self.raw_text,
            "final_text": self.final_text,
            "duration": self.duration,
            "api_calls": self.api_calls,
            "source": self.source,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HistoryEntry":
        """Build an entry from a stored JSON object."""
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex[:12]),
            created_at=str(data.get("created_at") or _now_iso()),
            raw_text=str(data.get("raw_text") or ""),
            final_text=str(data.get("final_text") or ""),
            duration=float(data.get("duration") or 0),
            api_calls=int(data.get("api_calls") or 0),
            source=str(data.get("source") or "audio"),
            metadata=dict(data.get("metadata") or {}),
        )


class HistoryStore:
    """Append-only JSONL history with simple retention."""

    def __init__(
        self,
        path: Path | str | None = None,
        max_entries: int = 100,
        enabled: bool = True,
    ):
        self.path = Path(path) if path else DEFAULT_HISTORY_PATH
        self.max_entries = max(1, int(max_entries or 100))
        self.enabled = bool(enabled)

    @classmethod
    def from_config(cls, history_cfg: dict[str, Any] | None) -> "HistoryStore":
        """Create a store from the normalized history config."""
        history_cfg = history_cfg or {}
        return cls(
            path=history_cfg.get("path") or DEFAULT_HISTORY_PATH,
            max_entries=int(history_cfg.get("max_entries", 100)),
            enabled=history_cfg.get("enabled", True),
        )

    def append(
        self,
        raw_text: str,
        final_text: str,
        duration: float,
        api_calls: int,
        source: str = "audio",
        metadata: dict[str, Any] | None = None,
    ) -> HistoryEntry | None:
        """Append a completed output and return the stored entry."""
        if not self.enabled:
            return None
        if not final_text:
            return None

        entry = HistoryEntry(
            id=uuid.uuid4().hex[:12],
            created_at=_now_iso(),
            raw_text=raw_text or "",
            final_text=final_text,
            duration=float(duration or 0),
            api_calls=int(api_calls or 0),
            source=source or "audio",
            metadata=dict(metadata or {}),
        )

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
            self._prune()
        except OSError as e:
            log.warning("写入历史记录失败: %s", e)
            return None

        return entry

    def list_recent(self, limit: int | None = None) -> list[HistoryEntry]:
        """Return newest entries first."""
        entries = self._read_all()
        entries.reverse()
        if limit is not None:
            return entries[: max(0, int(limit))]
        return entries

    def clear(self) -> bool:
        """Remove all history entries."""
        try:
            if self.path.exists():
                self.path.unlink()
            return True
        except OSError as e:
            log.warning("清空历史记录失败: %s", e)
            return False

    def _read_all(self) -> list[HistoryEntry]:
        if not self.path.exists():
            return []

        entries: list[HistoryEntry] = []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if isinstance(data, dict):
                            entries.append(HistoryEntry.from_dict(data))
                    except (TypeError, ValueError) as e:
                        log.debug("跳过无效历史记录行: %s", e)
        except OSError as e:
            log.warning("读取历史记录失败: %s", e)
        return entries

    def _prune(self):
        entries = self._read_all()
        if len(entries) <= self.max_entries:
            return
        keep = entries[-self.max_entries :]
        with open(self.path, "w", encoding="utf-8") as f:
            for entry in keep:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
