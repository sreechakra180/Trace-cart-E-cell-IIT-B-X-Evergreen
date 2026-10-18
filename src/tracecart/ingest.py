"""Ingestion + validation + clock alignment.

Loads JSONL streams of raw events (visual, scan, heartbeat) and:
- parses/aligns timestamps
- validates against schema
- attaches data-quality flags
- never raises on malformed rows (flags instead)

Returns typed events + data-quality log.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple, Union

from .schema import (
    FeedHeartbeat,
    ReasonCode,
    TransactionScanEvent,
    VisualTransferEvent,
)
from .timeutil import parse_iso8601_to_utc, apply_clock_offset
from .config import Config


def _safe_json_loads(line: str) -> Optional[Dict]:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def ingest_visual_events(
    path: str | Path, cfg: Config
) -> Tuple[List[VisualTransferEvent], List[Dict]]:
    """Load visual events JSONL → typed VisualTransferEvent + quality log."""
    events: List[VisualTransferEvent] = []
    log: List[Dict] = []
    with open(path, encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            obj = _safe_json_loads(raw.strip())
            if obj is None:
                log.append(
                    {
                        "file": path,
                        "line": lineno,
                        "error": "JSON decode failure",
                        "raw": raw[:200],
                    }
                )
                continue

            try:
                # Expect VisualTransferEvent-compatible dict
                evt = VisualTransferEvent(**obj)
                events.append(evt)
            except Exception as exc:  # pydantic.ValidationError or others
                log.append(
                    {
                        "file": path,
                        "line": lineno,
                        "error": f"Validation failure: {exc}",
                        "raw": json.dumps(obj)[:200],
                    }
                )
                # Do NOT raise — keep processing
    return events, log


def ingest_scan_events(
    path: str | Path, cfg: Config
) -> Tuple[List[TransactionScanEvent], List[Dict]]:
    """Load transaction scan events JSONL → typed + quality log."""
    events: List[TransactionScanEvent] = []
    log: List[Dict] = []
    with open(path, encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            obj = _safe_json_loads(raw.strip())
            if obj is None:
                log.append(
                    {
                        "file": path,
                        "line": lineno,
                        "error": "JSON decode failure",
                        "raw": raw[:200],
                    }
                )
                continue

            try:
                # Parse t_scan if present and valid ISO-8601 with tz
                t_scan_raw = obj.get("t_scan")
                if isinstance(t_scan_raw, str):
                    try:
                        obj["t_scan"] = parse_iso8601_to_utc(t_scan_raw)
                    except ValueError:
                        obj["t_scan"] = None
                        obj.setdefault("quality_flags", []).append(
                            ReasonCode.TS_INVALID
                        )
                        if ":" not in t_scan_raw and "T" not in t_scan_raw:
                            obj["quality_flags"].append(ReasonCode.TS_NAIVE)
                elif t_scan_raw is not None:
                    obj["t_scan"] = float(t_scan_raw)
                else:
                    obj["t_scan"] = None

                evt = TransactionScanEvent(**obj)
                events.append(evt)
            except Exception as exc:
                log.append(
                    {
                        "file": path,
                        "line": lineno,
                        "error": f"Validation failure: {exc}",
                        "raw": json.dumps(obj)[:200],
                    }
                )
    return events, log


def ingest_heartbeats(
    path: str | Path, cfg: Config
) -> Tuple[List[FeedHeartbeat], List[Dict]]:
    """Load feed heartbeats JSONL → typed + quality log."""
    hbs: List[FeedHeartbeat] = []
    log: List[Dict] = []
    with open(path, encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            obj = _safe_json_loads(raw.strip())
            if obj is None:
                log.append(
                    {
                        "file": path,
                        "line": lineno,
                        "error": "JSON decode failure",
                        "raw": raw[:200],
                    }
                )
                continue
            try:
                hb = FeedHeartbeat(**obj)
                hbs.append(hb)
            except Exception as exc:
                log.append(
                    {
                        "file": path,
                        "line": lineno,
                        "error": f"Validation failure: {exc}",
                        "raw": json.dumps(obj)[:200],
                    }
                )
    return hbs, log