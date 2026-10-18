"""Timestamp utilities: parsing, alignment, clock offsets.

All internal times are UTC epoch seconds (float).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Tuple

import pytz


def parse_iso8601_to_utc(ts: str) -> float:
    """Parse ISO-8601 string (with timezone) to UTC epoch seconds.

    Naive strings → ts_invalid flag unless assume_tz is set in config.
    """
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        # Try common formats
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%d %H:%M:%S.%f%z",
        ):
            try:
                dt = datetime.strptime(ts, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Unrecognised timestamp format: {ts}")

    if dt.tzinfo is None:
        raise ValueError("Timestamp lacks timezone info (naive)")
    return dt.timestamp()


def utc_now() -> float:
    """Current UTC epoch seconds."""
    return datetime.now(timezone.utc).timestamp()


def apply_clock_offset(t_local: float, offset_s: float) -> float:
    """Apply clock offset once at ingestion (source-local → UTC)."""
    return t_local + offset_s


def clip_time_to_utc(
    clip_start_epoch: float, frame_idx: int, fps: float
) -> Tuple[float, bool]:
    """Convert (clip_start, frame_idx, fps) → UTC epoch seconds + fps_unreliable flag."""
    if fps <= 0:
        return clip_start_epoch + frame_idx / 30.0, True  # fallback fps
    t = clip_start_epoch + frame_idx / fps
    unreliable = fps == 0.0  # metadata zero or VFR detected heuristically
    return t, unreliable