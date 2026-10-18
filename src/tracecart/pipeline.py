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
from .ingest import ingest_scan_events, ingest_visual_events
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


def run_scenario(
    scenario_id: str,
    cache_file: str | Path,
    feed_file: str | Path,
    cfg: Config,
) -> List[Decision]:
    """Run pipeline on a scenario using cached observations + generated feed.

    This is what `make demo` calls. Reads from committed cache (no torch needed).
    """
    visuals, _ = ingest_visual_events(cache_file, cfg)
    feed, _ = ingest_scan_events(feed_file, cfg)
    return run(visuals, feed, cfg)


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