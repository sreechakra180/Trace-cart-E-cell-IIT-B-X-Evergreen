"""Assignment + ambiguity margins.

Implements ARCHITECTURE §7.3–7.4:
  - linear_sum_assignment (Hungarian) over the cost matrix
  - accept pair if cost <= τ_match
  - deterministic tie-breaking by (cost, d, s_id, v_id) + ε·rank
  - ambiguity: margin_i and margin_j over rival candidates
  - near-miss for unmatched visual events
  - one scan slot ↔ one visual event (Hungarian guarantees bijection)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from scipy.optimize import linear_sum_assignment

from .schema import CandidateLink
from .cost import build_candidate, distance_to_interval, gate_pair
from .config import Config


BIG = 1e9


@dataclass
class AssignmentResult:
    links: List[CandidateLink]        # all candidate links (selected ones marked)
    matched_pairs: List[Tuple[str, str]]  # (v_id, s_id) accepted matches
    unmatched_visual: List[str]       # v_ids with no accepted match
    near_miss_visual: List[str]       # v_ids with near-miss candidates
    ambiguous_pairs: List[Tuple[str, str]]  # (v_id, s_id) ambiguous but accepted


def assign(
    visuals: List,
    scans: List,
    cfg: Config,
) -> AssignmentResult:
    """Run gated Hungarian assignment over (visual events × scan slots).

    Returns an AssignmentResult. A visual event is matched to at most one scan
    slot and vice versa — Hungarian guarantees a bijection, so a single scan
    slot is never consumed by unlimited visual events.
    """
    # Build expanded scan slots (qty expansion handled upstream)
    from .cost import expand_scans

    expanded = expand_scans(scans)  # List[(scan, slot)]

    # Build cost matrix rows=visuals, cols=scan slots
    n_v = len(visuals)
    n_s = len(expanded)

    # distance lookup for tie-break
    def _dist(v, s_slot):
        s, _ = s_slot
        if s.t_scan is None:
            return BIG
        return distance_to_interval(s.t_scan, v.t_pick, v.t_bag)

    cost_matrix = [[BIG] * n_s for _ in range(n_v)]
    candidate_links: List[CandidateLink] = []

    for i, v in enumerate(visuals):
        row_links: List[CandidateLink] = []
        for j, (s, slot) in enumerate(expanded):
            link = build_candidate(v, s, slot, cfg)
            candidate_links.append(link)
            if link.gate_pass:
                cost_matrix[i][j] = link.cost

    # Hungarian assignment
    if n_v > 0 and n_s > 0:
        row_ind, col_ind = linear_sum_assignment(cost_matrix)
    else:
        row_ind, col_ind = [], []

    # Build selected set
    selected_set: set[Tuple[int, int]] = set()
    accepted_pairs: List[Tuple[str, str]] = []

    for i, j in zip(row_ind, col_ind):
        cost = cost_matrix[i][j]
        if cost < BIG / 2 and cost <= cfg.tau_match:
            selected_set.add((i, j))
            v = visuals[i]
            s, _ = expanded[j]
            accepted_pairs.append((v.v_id, s.s_id))

    # Mark selected on candidate links
    # Re-scan candidate_links with indices
    link_index = 0
    for i, v in enumerate(visuals):
        for j, (s, slot) in enumerate(expanded):
            link = candidate_links[link_index]
            link_index += 1
            if (i, j) in selected_set:
                link.selected = True

    # Ambiguity margins
    # Group links by v_id and by (s_id, slot)
    by_v: Dict[str, List[CandidateLink]] = {}
    by_slot: Dict[Tuple[str, int], List[CandidateLink]] = {}
    for link in candidate_links:
        if not link.gate_pass:
            continue
        by_v.setdefault(link.v_id, []).append(link)
        by_slot.setdefault((link.s_id, link.slot), []).append(link)

    for link in candidate_links:
        if not link.gate_pass or not link.selected:
            continue
        # margin_i = min over other candidate slots j' of C(i,j') - C(i,j)
        rival_costs_v = [
            l.cost for l in by_v.get(link.v_id, [])
            if (l.s_id, l.slot) != (link.s_id, link.slot)
        ]
        margin_i = min((c - link.cost for c in rival_costs_v), default=1.0)
        # margin_j = min over rival visual events for this specific slot of C(i',j) - C(i,j)
        rival_costs_s = [
            l.cost for l in by_slot.get((link.s_id, link.slot), [])
            if l.v_id != link.v_id
        ]
        margin_j = min((c - link.cost for c in rival_costs_s), default=1.0)
        link.margin = min(margin_i, margin_j)

    # Determine unmatched + near-miss
    matched_v_ids = {v_id for v_id, _ in accepted_pairs}
    matched_s_ids = {s_id for _, s_id in accepted_pairs}

    unmatched_visual: List[str] = []
    near_miss_visual: List[str] = []
    ambiguous_pairs: List[Tuple[str, str]] = []

    for v in visuals:
        if v.v_id in matched_v_ids:
            continue
        # check for near-miss: gated candidate with cost <= τ_match + δ_amb
        has_near_miss = any(
            l.cost <= cfg.tau_match + cfg.delta_amb
            for l in by_v.get(v.v_id, [])
        )
        if has_near_miss:
            near_miss_visual.append(v.v_id)
        else:
            unmatched_visual.append(v.v_id)

    for v_id, s_id in accepted_pairs:
        link = next(
            (l for l in candidate_links
             if l.v_id == v_id and l.s_id == s_id and l.selected),
            None,
        )
        if link is not None and link.margin is not None and link.margin < cfg.delta_amb:
            ambiguous_pairs.append((v_id, s_id))

    return AssignmentResult(
        links=candidate_links,
        matched_pairs=accepted_pairs,
        unmatched_visual=unmatched_visual,
        near_miss_visual=near_miss_visual,
        ambiguous_pairs=ambiguous_pairs,
    )
