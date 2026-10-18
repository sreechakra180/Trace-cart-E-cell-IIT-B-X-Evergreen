"""Cost terms and gated candidate-link construction.

Implements ARCHITECTURE §7:
  - Hard gating (R1 rules)
  - 4 normalised cost terms T (temporal), Z (zone), S (product), F (flow)
  - Missing-term renormalisation (missing ≠ mismatch, never treated as 1)
  - CandidateLink objects

The cost matrix is produced in this module; assignment (Hungarian) is in
`assign.py`. This module is pure-Python and tested without torch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .schema import (
    CandidateLink,
    ReasonCode,
    TransactionScanEvent,
    VisualTransferEvent,
)
from .config import Config


@dataclass(frozen=True)
class GateResult:
    passed: bool
    reason: Optional[str] = None  # ReasonCode if failed


def distance_to_interval(t_scan: float, t_pick: float, t_bag: float) -> float:
    """Distance from t_scan to the handling interval [t_pick, t_bag].
    0 if t_pick <= t_scan <= t_bag; else distance to nearest endpoint."""
    if t_pick <= t_scan <= t_bag:
        return 0.0
    return min(abs(t_scan - t_pick), abs(t_scan - t_bag))


def gate_pair(
    v: VisualTransferEvent,
    s: TransactionScanEvent,
    cfg: Config,
) -> GateResult:
    """Hard gating check for a (visual event, scan slot) pair.

    Per ARCHITECTURE §7.1:
      - same session_id
      - both timestamps valid
      - d(i,j) <= W_gate
      - if zone_strict: zones equal (else zone is a penalty term, not exclusion)
      - scan txn_status != voided
    """
    if v.session_id != s.session_id:
        return GateResult(False, "session_mismatch")
    if v.t_bag is None or s.t_scan is None:
        return GateResult(False, "ts_invalid")
    if ReasonCode.TS_INVALID in v.quality_flags or ReasonCode.TS_INVALID in s.quality_flags:
        return GateResult(False, "ts_invalid")

    d = distance_to_interval(s.t_scan, v.t_pick, v.t_bag)
    if d > cfg.w_gate:
        return GateResult(False, ReasonCode.NO_CANDIDATE_IN_WINDOW.value)

    if cfg.zone_strict and v.store_zone and s.zone_hint:
        if v.store_zone != s.zone_hint:
            return GateResult(False, "zone_mismatch_strict")

    if s.txn_status == "voided":
        return GateResult(False, "voided")

    return GateResult(True)


def _temporal_term(t_scan: float, v: VisualTransferEvent, cfg: Config) -> float:
    """T = min(1, d(i,j) / W_norm) ∈ [0,1]."""
    d = distance_to_interval(t_scan, v.t_pick, v.t_bag)
    return min(1.0, d / cfg.w_norm)


def _zone_term(s: TransactionScanEvent, v: VisualTransferEvent) -> Tuple[Optional[float], bool]:
    """Z: 0 if zone_hint missing or equals store_zone; 1 if both known and different.
    Returns (term, available). Missing zone_hint ⇒ unavailable (not 0)."""
    if s.zone_hint is None or s.zone_hint == "":
        return None, False
    if v.store_zone is None or v.store_zone == "":
        return None, False
    if s.zone_hint == v.store_zone:
        return 0.0, True
    return 1.0, True


def _product_term(
    s: TransactionScanEvent,
    v: VisualTransferEvent,
    cfg: Config,
) -> Tuple[Optional[float], bool]:
    """S = 1 − cls_votes[class(sku)] if sku has class in skumap and cls_votes exists.
    Else unavailable."""
    if not s.sku or s.sku not in cfg.sku_to_class or not v.cls_votes:
        return None, False
    cls = cfg.sku_to_class[s.sku]
    prob = v.cls_votes.get(cls, 0.0)
    return (1.0 - prob), True


def _flow_term(slot: int, s: TransactionScanEvent) -> Tuple[float, bool]:
    """F = max(slot_pen, status_pen).
      slot_pen = 0 for slot 1, 0.5 for slots >=2 (qty>1 indistinguishable).
      status_pen = 0.5 if pending, else 0."""
    slot_pen = 0.0 if slot <= 1 else 0.5
    status_pen = 0.5 if s.txn_status == "pending" else 0.0
    return max(slot_pen, status_pen), True


def build_candidate(
    v: VisualTransferEvent,
    s: TransactionScanEvent,
    slot: int,
    cfg: Config,
) -> Optional[CandidateLink]:
    """Build a CandidateLink with cost if gating passes, else None.

    Cost = Σ_{k∈A} λ_k · k(i,j) / Σ_{k∈A} λ_k   (always in [0,1]).
    Missing terms are dropped and weights renormalised.
    """
    g = gate_pair(v, s, cfg)
    if not g.passed:
        return CandidateLink(
            v_id=v.v_id,
            s_id=s.s_id,
            slot=slot,
            gate_pass=False,
            gate_reason=None,
            T=1.0,
            Z=1.0,
            S=1.0,
            F=1.0,
            available_terms=[],
            cost=1.0,  # BIG — non-candidate
            selected=False,
            margin=None,
        )

    # Compute terms
    available: List[str] = []
    w_sum = 0.0
    weighted_sum = 0.0

    T = _temporal_term(s.t_scan, v, cfg)
    available.append("T")
    w_sum += cfg.lambda_t
    weighted_sum += cfg.lambda_t * T

    Z, z_avail = _zone_term(s, v)
    if z_avail:
        available.append("Z")
        w_sum += cfg.lambda_z
        weighted_sum += cfg.lambda_z * Z

    S, s_avail = _product_term(s, v, cfg)
    if s_avail:
        available.append("S")
        w_sum += cfg.lambda_s
        weighted_sum += cfg.lambda_s * S

    F, f_avail = _flow_term(slot, s)
    if f_avail:
        available.append("F")
        w_sum += cfg.lambda_f
        weighted_sum += cfg.lambda_f * F

    cost = weighted_sum / w_sum if w_sum > 0 else 1.0
    cost = min(1.0, max(0.0, cost))

    return CandidateLink(
        v_id=v.v_id,
        s_id=s.s_id,
        slot=slot,
        gate_pass=True,
        gate_reason=None,
        T=T,
        Z=Z if z_avail else -1.0,
        S=S if s_avail else -1.0,
        F=F,
        available_terms=available,
        cost=cost,
        selected=False,
        margin=None,
    )


def expand_scans(scans: List[TransactionScanEvent]) -> List[Tuple[TransactionScanEvent, int]]:
    """Expand each valid scan by its qty into (scan, slot) pairs.

    Voided and exact-duplicate scans are removed first per ARCHITECTURE §7.
    """
    expanded: List[Tuple[TransactionScanEvent, int]] = []
    seen_lines = set()
    for s in scans:
        if s.txn_status == "voided":
            continue
        line_key = (s.txn_line_id, s.sku, s.t_scan) if s.txn_line_id else None
        if line_key and line_key in seen_lines:
            continue
        if any("duplicate" in str(f).lower() for f in s.quality_flags):
            continue
        if line_key:
            seen_lines.add(line_key)

        q = s.qty if s.qty and s.qty > 0 else 1
        for slot in range(1, q + 1):
            expanded.append((s, slot))
    return expanded
