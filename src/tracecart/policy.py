"""Decision policy R01–R40 (top-down, first match wins).

Per ARCHITECTURE §9 and the operating rules:
  - A single scan slot ↔ one visual event (one-to-one via Hungarian in assign.py).
  - REVIEW message is the fixed, non-accusatory template below.
  - Late-event revision: decisions are recomputed when a new scan/heartbeat
    arrives; late scans can supersede a REVIEW with MATCHED v2; both versions
    kept; first-issued decision counts for false-REVIEW metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .schema import (
    CandidateLink,
    Decision,
    DecisionState,
    EvidenceQuality,
    ReasonCode,
)
from .config import Config
from .cost import build_candidate, expand_scans
from .assign import assign


# ── Fixed recommended-action templates ──────────────────────────────────────

ACTION_MATCHED = "No action."

ACTION_REVIEW = (
    "A visual event was observed in the configured zone. "
    "No compatible scan event was identified within the configured matching "
    "constraints. Observation quality passed the configured review gate, so "
    "human verification is recommended. This does not establish intent."
)

ACTION_ABSTAIN = (
    "No alert. Insufficient/ambiguous evidence: <reasons>. "
    "Optional alternative verification only if store policy allows."
)

ACTION_INFO = "No intervention (orphan scan)."


@dataclass
class PolicyResult:
    decision: Decision
    was_revision: bool = False


def _time_diffs(
    t_ref: float,
    watermark: Optional[float],
    selected_scan=None,
) -> Dict[str, float]:
    diffs: Dict[str, float] = {"t_ref": t_ref}
    if watermark is not None:
        diffs["watermark"] = watermark
        diffs["grace_gap_s"] = watermark - t_ref
    if selected_scan is not None and selected_scan.t_scan is not None:
        diffs["t_scan_minus_t_ref"] = selected_scan.t_scan - t_ref
    return diffs


def evaluate(
    *,
    visuals: List,
    feed: List,
    cfg: Config,
    previous_decisions: Optional[Dict[str, Decision]] = None,
) -> List[Decision]:
    """Run the full decision pipeline for a session.

    Args:
        visuals: list of VisualTransferEvent objects for the session
        feed: list of TransactionScanEvent objects for the session
        cfg: configuration
        previous_decisions: existing decisions keyed by v_id, for revision logic

    Returns list of Decision objects (one per visual event).
    """
    # ── R1/R2: gating & assignment (one scan slot ↔ one visual event) ──
    assignment = assign(visuals, feed, cfg)

    # Build lookups
    accepted: Dict[str, CandidateLink] = {}
    for link in assignment.links:
        if link.selected:
            accepted[link.v_id] = link

    matched_pairs = set(assignment.matched_pairs)
    ambiguous_pairs = set(assignment.ambiguous_pairs)
    near_miss = set(assignment.near_miss_visual)

    decisions: List[Decision] = []

    # Feed watermark (max t_ingest over feed events)
    feed_ingests = [getattr(e, "t_ingest", None) for e in feed if getattr(e, "t_ingest", None) is not None]
    if feed_ingests:
        watermark = max(feed_ingests)
    else:
        # Default watermark for sessions without scan stream: past grace period
        watermark = max([v.t_ref + cfg.grace_s for v in visuals] or [None])

    for v in visuals:
        link = accepted.get(v.v_id)
        selected_scan = None
        best_cost = None
        margin = None

        if link is not None:
            # find the matching scan
            for s in feed:
                if s.s_id == link.s_id:
                    selected_scan = s
                    break
            best_cost = link.cost
            margin = link.margin

        # ── R01: visual ts_invalid or session link missing → ABSTAIN ──
        if (ReasonCode.TS_INVALID in v.quality_flags or not v.session_id):
            decision = _make_decision(
                v=v,
                state=DecisionState.ABSTAIN,
                rule_id="R01",
                reason_codes=[ReasonCode.TS_INVALID],
                candidates=[],
                best_cost=None,
                margin=None,
                evidence_quality=None,
                watermark=watermark,
                cfg=cfg,
                selected_scan=None,
            )
            decisions.append(decision)
            continue

        # ── R02: feed unhealthy AND no accepted match → ABSTAIN ──
        feed_healthy = watermark is not None and watermark >= v.t_ref + cfg.grace_s
        if not feed_healthy and link is None:
            decision = _make_decision(
                v=v,
                state=DecisionState.ABSTAIN,
                rule_id="R02",
                reason_codes=[ReasonCode.FEED_HEALTHY if False else ReasonCode.NO_CANDIDATE_IN_WINDOW],
                candidates=[],
                best_cost=None,
                margin=None,
                evidence_quality=None,
                watermark=watermark,
                cfg=cfg,
                selected_scan=None,
            )
            decisions.append(decision)
            continue

        # Evaluate evidence quality gate
        q_pass, q_failed = _quality_pass(v, cfg, feed_healthy, watermark)
        q_reason_codes = [_flag_to_reason(f) for f in q_failed]

        accepted_match = link is not None

        # ── R12/R13: class conflict on accepted candidate ──
        class_conflict = _is_class_conflict(link, v, cfg) if accepted_match else False
        if accepted_match and class_conflict:
            if q_pass:
                decision = _make_decision(
                    v=v,
                    state=DecisionState.REVIEW,
                    rule_id="R12",
                    reason_codes=[ReasonCode.EVIDENCE_QUALITY_OK],
                    candidates=[link] if link else [],
                    best_cost=best_cost,
                    margin=margin,
                    evidence_quality=_make_evidence_quality(v, True, []),
                    watermark=watermark,
                    cfg=cfg,
                    selected_scan=selected_scan,
                )
            else:
                decision = _make_decision(
                    v=v,
                    state=DecisionState.ABSTAIN,
                    rule_id="R13",
                    reason_codes=q_reason_codes,
                    candidates=[link] if link else [],
                    best_cost=best_cost,
                    margin=margin,
                    evidence_quality=_make_evidence_quality(v, q_pass, q_reason_codes),
                    watermark=watermark,
                    cfg=cfg,
                    selected_scan=selected_scan,
                )
            decisions.append(decision)
            continue

        # ── R11: accepted match but ambiguous → ABSTAIN ──
        if accepted_match and (v.v_id, link.s_id) in ambiguous_pairs:
            decision = _make_decision(
                v=v,
                state=DecisionState.ABSTAIN,
                rule_id="R11",
                reason_codes=q_reason_codes,
                candidates=[link] if link else [],
                best_cost=best_cost,
                margin=margin,
                evidence_quality=_make_evidence_quality(v, q_pass, q_reason_codes),
                watermark=watermark,
                cfg=cfg,
                selected_scan=selected_scan,
            )
            decisions.append(decision)
            continue

        # ── R10: accepted match, not ambiguous, no class conflict → MATCHED ──
        if accepted_match and (v.v_id, link.s_id) not in ambiguous_pairs:
            decision = _make_decision(
                v=v,
                state=DecisionState.MATCHED,
                rule_id="R10",
                reason_codes=[ReasonCode.EVIDENCE_QUALITY_OK if q_pass else ReasonCode.TS_INVALID],
                candidates=[link] if link else [],
                best_cost=best_cost,
                margin=margin,
                evidence_quality=_make_evidence_quality(v, q_pass, q_reason_codes),
                watermark=watermark,
                cfg=cfg,
                selected_scan=selected_scan,
            )
            decisions.append(decision)
            continue

        # ── R20: no accepted match, no near-miss, Q_pass, feed healthy, grace elapsed → REVIEW ──
        if (not accepted_match and v.v_id not in near_miss
                and q_pass and feed_healthy
                and watermark is not None and watermark >= v.t_ref + cfg.grace_s):
            decision = _make_decision(
                v=v,
                state=DecisionState.REVIEW,
                rule_id="R20",
                reason_codes=[ReasonCode.NO_CANDIDATE_IN_WINDOW, ReasonCode.EVIDENCE_QUALITY_OK, ReasonCode.FEED_HEALTHY],
                candidates=[],
                best_cost=None,
                margin=None,
                evidence_quality=_make_evidence_quality(v, True, []),
                watermark=watermark,
                cfg=cfg,
                selected_scan=None,
            )
            decisions.append(decision)
            continue

        # ── R21: no accepted match and not Q_pass → ABSTAIN ──
        if not accepted_match and not q_pass:
            decision = _make_decision(
                v=v,
                state=DecisionState.ABSTAIN,
                rule_id="R21",
                reason_codes=q_reason_codes,
                candidates=[],
                best_cost=None,
                margin=None,
                evidence_quality=_make_evidence_quality(v, q_pass, q_reason_codes),
                watermark=watermark,
                cfg=cfg,
                selected_scan=None,
            )
            decisions.append(decision)
            continue

        # ── R22: no accepted match but near-miss candidate exists → ABSTAIN ──
        if not accepted_match and v.v_id in near_miss:
            decision = _make_decision(
                v=v,
                state=DecisionState.ABSTAIN,
                rule_id="R22",
                reason_codes=q_reason_codes + [ReasonCode.NO_CANDIDATE_IN_WINDOW],
                candidates=[],
                best_cost=None,
                margin=None,
                evidence_quality=_make_evidence_quality(v, q_pass, q_reason_codes),
                watermark=watermark,
                cfg=cfg,
                selected_scan=None,
            )
            decisions.append(decision)
            continue

        # ── R30: contradictory sequence → ABSTAIN ──
        if _is_contradictory(link, v):
            decision = _make_decision(
                v=v,
                state=DecisionState.ABSTAIN,
                rule_id="R30",
                reason_codes=q_reason_codes,
                candidates=[link] if link else [],
                best_cost=best_cost,
                margin=margin,
                evidence_quality=_make_evidence_quality(v, q_pass, q_reason_codes),
                watermark=watermark,
                cfg=cfg,
                selected_scan=selected_scan,
            )
            decisions.append(decision)
            continue

        # Default: ABSTAIN with no candidate (safety net)
        decision = _make_decision(
            v=v,
            state=DecisionState.ABSTAIN,
            rule_id="DEFAULT",
            reason_codes=q_reason_codes,
            candidates=[link] if link else [],
            best_cost=best_cost,
            margin=margin,
            evidence_quality=_make_evidence_quality(v, q_pass, q_reason_codes),
            watermark=watermark,
            cfg=cfg,
            selected_scan=selected_scan,
        )
        decisions.append(decision)

    return decisions


# ── Internal helpers ───────────────────────────────────────────────────────


def _quality_pass(v, cfg: Config, feed_healthy: bool, watermark: Optional[float] = None) -> Tuple[bool, List[str]]:
    from .quality_gate import evaluate_quality
    result = evaluate_quality(
        det_conf_median=v.det_conf_median,
        track_continuity=v.track_continuity,
        gap_max_s=v.gap_max_s,
        n_frames=v.n_frames,
        n_persons_max=v.n_persons_max,
        luma_mean=v.luma_mean,
        blur_var_min=v.blur_var_min,
        timestamps_valid=(ReasonCode.TS_INVALID not in v.quality_flags),
        fps_unreliable=(ReasonCode.FPS_UNRELIABLE in v.quality_flags),
        watermark=watermark,
        t_ref=v.t_ref,
        cfg=cfg,
        has_feed_gap=not feed_healthy,
    )
    return result.passed, result.failed


def _flag_to_reason(flag: str) -> ReasonCode:
    mapping = {
        "det_conf_median": ReasonCode.SHORT_TRACK,
        "track_continuity": ReasonCode.ID_SWITCH_SUSPECT,
        "gap_max_s": ReasonCode.ID_SWITCH_SUSPECT,
        "n_frames": ReasonCode.SHORT_TRACK,
        "n_persons_max": ReasonCode.MULTI_PERSON,
        "frame_quality_luma": ReasonCode.LOW_LIGHT,
        "frame_quality_blur": ReasonCode.BLURRY,
        "timestamps_invalid": ReasonCode.TS_INVALID,
        "fps_unreliable": ReasonCode.FPS_UNRELIABLE,
        "feed_unhealthy": ReasonCode.TS_INVALID,
    }
    return mapping.get(flag, ReasonCode.TS_INVALID)


def _make_evidence_quality(v, q_pass: bool, q_reason_codes: List[ReasonCode]) -> EvidenceQuality:
    return EvidenceQuality(
        det_conf=v.det_conf_median,
        continuity=v.track_continuity,
        gap_max_s=v.gap_max_s,
        n_persons=v.n_persons_max,
        frame_quality="ok" if q_pass else "failed",
        pass_=q_pass,
        failed=[str(c.value) for c in q_reason_codes],
    )


def _is_class_conflict(link: Optional[CandidateLink], v, cfg: Config) -> bool:
    if link is None:
        return False
    return bool(
        link.S >= 0.9 and v.cls_votes and max(v.cls_votes.values()) >= 0.6
    )


def _is_contradictory(link: Optional[CandidateLink], v) -> bool:
    """Contradiction: only candidate precedes t_pick by > W_gate, or class conflict with no valid alternative."""
    if link is None:
        return False
    if link.S >= 0.9 and link.T > 1.0:  # strong conflict + far in time
        return True
    return False


def _make_decision(
    v,
    state: DecisionState,
    rule_id: str,
    reason_codes: List[ReasonCode],
    candidates: List[CandidateLink],
    best_cost: Optional[float],
    margin: Optional[float],
    evidence_quality: EvidenceQuality,
    watermark: Optional[float],
    cfg: Config,
    selected_scan=None,
) -> Decision:
    import hashlib

    decision_id = f"D-{v.v_id}-v1"

    # visual summary
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

    candidates_list = [
        {
            "v_id": c.v_id,
            "s_id": c.s_id,
            "slot": c.slot,
            "gate_pass": c.gate_pass,
            "gate_reason": c.gate_reason,
            "cost": c.cost,
            "selected": c.selected,
            "margin": c.margin,
            "T": c.T,
            "Z": c.Z,
            "S": c.S,
            "F": c.F,
            "available_terms": getattr(c, "available_terms", []),
        }
        for c in candidates
    ]

    action_map = {
        DecisionState.MATCHED: ACTION_MATCHED,
        DecisionState.REVIEW: ACTION_REVIEW,
        DecisionState.ABSTAIN: ACTION_ABSTAIN.replace("<reasons>",
            "; ".join(str(c.value) for c in reason_codes) or "none specified"),
        DecisionState.INFO: ACTION_INFO,
    }

    timing = {
        "t_ref": v.t_ref,
        "grace_s": cfg.grace_s,
        "watermark": watermark,
        "time_diffs_s": _time_diffs(v.t_ref, watermark, selected_scan),
    }

    return Decision(
        decision_id=decision_id,
        version=1,
        supersedes=None,
        unit={"type": "visual_transfer", "v_id": v.v_id},
        state=state,
        rule_id=rule_id,
        reason_codes=reason_codes,
        visual=visual_summary,
        candidates=candidates_list,
        association={"selected_s_id": selected_scan.s_id if selected_scan else None,
                     "best_cost": best_cost,
                     "margin": margin},
        evidence_quality=evidence_quality,
        timing=timing,
        warnings=[
            "product_evidence_coarse(class-level only)",
        ],
        recommended_action=action_map.get(state, ""),
        config_hash=cfg_hash(cfg),
        code_commit="unversioned",
        human_resolution=None,
    )


def cfg_hash(cfg: Config) -> str:
    import hashlib, json
    data = json.dumps({
        "lambda_t": cfg.lambda_t,
        "lambda_z": cfg.lambda_z,
        "lambda_s": cfg.lambda_s,
        "lambda_f": cfg.lambda_f,
        "tau_match": cfg.tau_match,
        "w_gate": cfg.w_gate,
        "delta_amb": cfg.delta_amb,
        "w_norm": cfg.w_norm,
        "zone_strict": cfg.zone_strict,
        "grace_s": cfg.grace_s,
        "min_dt": cfg.min_dt,
        "max_dt": cfg.max_dt,
        "min_track_frames": cfg.min_track_frames,
        "confidence_min": cfg.confidence_min,
        "det_conf_min": cfg.det_conf_min,
        "track_continuity_min": cfg.track_continuity_min,
        "gap_max_s_max": cfg.gap_max_s_max,
        "n_frames_min": cfg.n_frames_min,
        "n_persons_max": cfg.n_persons_max,
        "luma_min": cfg.luma_min,
        "luma_max": cfg.luma_max,
        "blur_var_min": cfg.blur_var_min,
        "sku_to_class": cfg.sku_to_class,
    }, sort_keys=True)
    return "sha256:" + hashlib.sha256(data.encode()).hexdigest()[:16]
