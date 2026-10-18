"""Timestamp-only baseline (B1).

Per ARCHITECTURE §10:
  - For each visual event (same session), take the nearest UNUSED scan by
    |t_scan - t_ref| within W_base.
  - Greedy in time order.
  - No zone/product/quality; outputs MATCHED or REVIEW only (no ABSTAIN).
  - Also reports a variant with W_base = 10 s.

Same inputs, same scorer as TraceCart.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .schema import CandidateLink, Decision, DecisionState, ReasonCode
from .config import Config


@dataclass
class BaselineResult:
    decisions: List[Decision]


def _nearest_unused(
    v,
    scans: List,
    used: set,
    w_base: float,
) -> Optional[Tuple[object, float]]:
    """Find nearest unused scan by |t_scan - t_ref| within w_base."""
    best: Optional[Tuple[object, float]] = None
    best_d = float("inf")
    for s in scans:
        if s.s_id in used:
            continue
        if s.t_scan is None:
            continue
        d = abs(s.t_scan - v.t_ref)
        if d <= w_base and d < best_d:
            best = (s, d)
            best_d = d
    return best


def run_baseline(
    visuals: List,
    feed: List,
    cfg: Config,
    w_base: float = 5.0,
) -> List[Decision]:
    """Run timestamp-only baseline. Returns decisions (MATCHED or REVIEW only)."""
    decisions: List[Decision] = []
    used: set = set()

    for v in visuals:
        # Skip if ts_invalid
        if ReasonCode.TS_INVALID in v.quality_flags:
            decisions.append(_make_baseline_decision(v, None, DecisionState.REVIEW, "B01"))
            continue

        match = _nearest_unused(v, feed, used, w_base)
        if match is not None:
            s, d = match
            used.add(s.s_id)
            decisions.append(_make_baseline_decision(v, s, DecisionState.MATCHED, "B01"))
        else:
            decisions.append(_make_baseline_decision(v, None, DecisionState.REVIEW, "B01"))

    return decisions


def _make_baseline_decision(v, selected_scan, state: DecisionState, rule_id: str) -> Decision:
    from .policy import cfg_hash, _time_diffs

    decision_id = f"B-{v.v_id}-v1"
    visual_summary = {
        "v_id": v.v_id,
        "session_id": v.session_id,
        "store_zone": v.store_zone,
        "t_pick": v.t_pick,
        "t_bag": v.t_bag,
        "t_ref": v.t_ref,
        "track_id": v.track_id,
        "det_conf_median": v.det_conf_median,
        "track_continuity": v.track_continuity,
        "cls_votes": v.cls_votes,
        "provenance": v.provenance.value if hasattr(v.provenance, "value") else str(v.provenance),
    }

    candidates = []
    if selected_scan is not None:
        candidates.append({
            "v_id": v.v_id,
            "s_id": selected_scan.s_id,
            "slot": 1,
            "gate_pass": True,
            "cost": abs(selected_scan.t_scan - v.t_ref),
            "selected": True,
            "margin": None,
            "T": abs(selected_scan.t_scan - v.t_ref),
            "Z": 0.0,
            "S": 0.0,
            "F": 0.0,
        })

    action_map = {
        DecisionState.MATCHED: "No action.",
        DecisionState.REVIEW: (
            "A visual event was observed in the configured zone. "
            "No compatible scan event was identified within the configured matching "
            "constraints. Observation quality passed the configured review gate, so "
            "human verification is recommended. This does not establish intent."
        ),
        DecisionState.ABSTAIN: "No alert. Insufficient/ambiguous evidence: <reasons>. "
                               "Optional alternative verification only if store policy allows.",
    }

    timing = {
        "t_ref": v.t_ref,
        "grace_s": 20.0,
        "watermark": None,
        "time_diffs_s": _time_diffs(v.t_ref, None, selected_scan),
    }

    return Decision(
        decision_id=decision_id,
        version=1,
        supersedes=None,
        unit={"type": "visual_transfer", "v_id": v.v_id},
        state=state,
        rule_id=rule_id,
        reason_codes=[],
        visual=visual_summary,
        candidates=candidates,
        association={"selected_s_id": selected_scan.s_id if selected_scan else None,
                     "best_cost": abs(selected_scan.t_scan - v.t_ref) if selected_scan else None,
                     "margin": None},
        evidence_quality={
            "det_conf": v.det_conf_median,
            "continuity": v.track_continuity,
            "gap_max_s": v.gap_max_s,
            "n_persons": v.n_persons_max,
            "frame_quality": "ok",
            "pass": True,
            "failed": [],
        },
        timing=timing,
        warnings=["baseline_timestamp_only"],
        recommended_action=action_map.get(state, ""),
        config_hash="sha256:baseline",
        code_commit="unversioned",
        human_resolution=None,
    )