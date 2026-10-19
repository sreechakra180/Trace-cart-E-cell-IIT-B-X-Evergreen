"""End-to-end pipeline orchestrator.

Pipeline is a library + CLI + HTTP API. The UI is a separate Antigravity
(React/TS) application consuming the API.

pipeline.run(...) is a pure function given typed events — deterministic.
pipeline.run_scenario(...) loads cache/observations + generated scan feed
from disk and runs end-to-end on a scenario.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from .schema import (
    Decision,
    DecisionState,
    FeedHeartbeat,
    TransactionScanEvent,
    VisualTransferEvent,
)
from .config import Config
from .ingest import ingest_scan_events
from .vision.events import extract_transfer_events
from .vision.zones import load_zones
from .policy import evaluate


# ── Pure engine entry point (given typed events) ───────────────────────────


def run(
    visuals: List[VisualTransferEvent],
    feed: List[TransactionScanEvent],
    cfg: Config,
) -> List[Decision]:
    """Run the full reconciliation pipeline on typed events.

    Pure function, deterministic. Groups events by session_id and applies
    policy R01-R40 per session.
    """
    # Group by session
    by_session: Dict[str, List[VisualTransferEvent]] = {}
    for v in visuals:
        by_session.setdefault(v.session_id, []).append(v)

    scans_by_session: Dict[str, List[TransactionScanEvent]] = {}
    for s in feed:
        scans_by_session.setdefault(s.session_id, []).append(s)

    # Merge: every session that has either visuals or scans
    all_sessions = set(by_session.keys()) | set(scans_by_session.keys())

    decisions: List[Decision] = []
    for session_id in sorted(all_sessions):
        session_visuals = by_session.get(session_id, [])
        session_scans = scans_by_session.get(session_id, [])

        if not session_visuals:
            # Orphan scans only (R40 → INFO)
            for s in session_scans:
                decisions.append(_orphan_scan_decision(s, cfg))
            continue

        # Run policy on this session
        session_decisions = evaluate(
            visuals=session_visuals,
            feed=session_scans,
            cfg=cfg,
        )
        decisions.extend(session_decisions)

    return decisions


# ── Disk-based scenario entry point ───────────────────────────────────────


def load_cache_detections(cache_file: str | Path) -> List[dict]:
    """Read raw detection entries from a cache JSONL file.

    Malformed rows are skipped rather than fatal — a detector cache is an
    external artifact and a single corrupt line must not abort the run.
    """
    entries: List[dict] = []
    required = ("frame", "t", "x1", "y1", "x2", "y2", "class_name", "conf", "track_id")
    with open(cache_file, encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and all(k in obj for k in required):
                entries.append(obj)
    return entries


def load_visuals_from_cache(
    cache_file: str | Path,
    cfg: Config,
    clip_start_epoch: float = 0.0,
    session_id: Optional[str] = None,
) -> List[VisualTransferEvent]:
    """Convert a detector cache into typed VisualTransferEvents.

    The cache stores raw per-frame detections (ARCHITECTURE §5 step 3). The
    V3 transfer-event extraction (§5 step 4) is applied here to produce the
    zone-conditioned events the engine consumes.
    """
    from .vision.events import Detection, extract_transfer_events

    entries = load_cache_detections(cache_file)
    detections = [
        Detection(
            frame=int(e["frame"]),
            t=float(e["t"]),
            x1=float(e["x1"]),
            y1=float(e["y1"]),
            x2=float(e["x2"]),
            y2=float(e["y2"]),
            class_name=e["class_name"],
            conf=float(e["conf"]),
            track_id=int(e["track_id"]),
        )
        for e in entries
    ]

    zones = load_zones(cfg.zones_yaml)
    event_dicts = extract_transfer_events(
        detections=detections,
        zones=zones,
        cfg=cfg,
        clip_start_epoch=clip_start_epoch,
        session_id=session_id,
        clip_name=Path(cache_file).stem.replace("obs_", ""),
    )

    visuals: List[VisualTransferEvent] = []
    for event_dict in event_dicts:
        try:
            visuals.append(VisualTransferEvent(**event_dict))
        except Exception:
            # A malformed transfer event is skipped, not fatal.
            continue
    return visuals


def align_clip_start_epoch(feed_events: List[TransactionScanEvent]) -> float:
    """Infer the clip's start epoch so visual and scan clocks share a frame.

    Cached observations store time relative to clip start (frame_idx / fps).
    The feed stores absolute UTC epoch seconds. Aligning the two requires the
    clip's absolute start, which we recover from the earliest scan: the visual
    transfer lands roughly a handling-buffer before the customer scans.

    Returns 0.0 when no valid scan timestamp exists (caller decides fallback).
    """
    scan_times = [s.t_scan for s in feed_events if s.t_scan is not None]
    if not scan_times:
        return 0.0
    return min(scan_times) - 1.5


def run_scenario(
    scenario_id: str,
    cache_file: str | Path,
    feed_file: str | Path,
    cfg: Config,
) -> List[Decision]:
    """Run pipeline on a scenario using cached observations + generated feed.

    This is what `make demo` calls. Reads from committed cache (no torch needed).
    """
    feed_events, _ = ingest_scan_events(feed_file, cfg)
    clip_start_epoch = align_clip_start_epoch(feed_events)

    # The scenario ID doubles as the session key (each scenario = one store visit).
    # Thread it into visual extraction so gate_pair can match visual ↔ scan.
    session_id = scenario_id
    visuals = load_visuals_from_cache(cache_file, cfg, clip_start_epoch, session_id=session_id)
    return run(visuals, feed_events, cfg)


# ── Orphan scan handling (R40 → INFO) ──────────────────────────────────────


def _orphan_scan_decision(scan: TransactionScanEvent, cfg: Config) -> Decision:
    """A scan with no visual transfer → INFO state, not an intervention."""
    decision_id = f"I-{scan.s_id}-v1"
    visual_summary = {
        "s_id": scan.s_id,
        "session_id": scan.session_id,
        "t_scan": scan.t_scan,
        "sku": scan.sku,
        "provenance": scan.provenance.value,
    }
    return Decision(
        decision_id=decision_id,
        version=1,
        supersedes=None,
        unit={"type": "scan_orphan", "s_id": scan.s_id},
        state=DecisionState.INFO,
        rule_id="R40",
        reason_codes=[],
        visual=visual_summary,
        candidates=[],
        association={"selected_s_id": None, "best_cost": None, "margin": None},
        evidence_quality={
            "det_conf": 0.0, "continuity": 0.0, "gap_max_s": 0.0,
            "n_persons": 0, "frame_quality": "n/a", "pass": True, "failed": [],
        },
        timing={"t_ref": scan.t_scan or scan.t_ingest, "grace_s": 0.0,
                "watermark": None, "time_diffs_s": {}},
        warnings=["orphan_scan_no_visual_transfer"],
        recommended_action="No intervention (orphan scan).",
        config_hash=_hash_cfg(cfg),
        code_commit="unversioned",
        human_resolution=None,
    )


def _hash_cfg(cfg: Config) -> str:
    from .policy import cfg_hash
    return cfg_hash(cfg)