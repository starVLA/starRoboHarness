"""Append-only JSONL traces with a verifiable SHA-256 chain."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .contracts import ContractError

GENESIS = "0" * 64


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


class ChainedJsonlTrace:
    """Durable event log that exposes accidental edits or missing events."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rows = self.read_all()
        self.sequence = len(rows)
        self.previous_sha256 = rows[-1]["sha256"] if rows else GENESIS

    def append(self, event: str, payload: Any) -> dict[str, Any]:
        if not isinstance(event, str) or not event:
            raise ContractError("trace event name is required")
        body = {
            "sequence": self.sequence,
            "event": event,
            "previous_sha256": self.previous_sha256,
            "payload": payload,
        }
        row = dict(body, sha256=hashlib.sha256(_canonical(body)).hexdigest())
        encoded = _canonical(row) + b"\n"
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            remaining = memoryview(encoded)
            while remaining:
                written = os.write(descriptor, remaining)
                if written == 0:
                    raise OSError("trace write returned zero bytes")
                remaining = remaining[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self.sequence += 1
        self.previous_sha256 = row["sha256"]
        return row

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = []
        previous = GENESIS
        with self.path.open(encoding="utf-8") as stream:
            for sequence, line in enumerate(stream):
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ContractError(f"invalid trace JSON at line {sequence + 1}") from error
                keys = ("sequence", "event", "previous_sha256", "payload")
                body = {key: row.get(key) for key in keys}
                digest = hashlib.sha256(_canonical(body)).hexdigest()
                if row.get("sequence") != sequence or row.get("previous_sha256") != previous:
                    raise ContractError(f"broken trace chain at line {sequence + 1}")
                if row.get("sha256") != digest:
                    raise ContractError(f"trace digest mismatch at line {sequence + 1}")
                rows.append(row)
                previous = digest
        return rows
