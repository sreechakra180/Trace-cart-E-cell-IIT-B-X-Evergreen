"""Evaluation metrics.

Implements EVALUATION_PLAN.md §4:
  4.1 Visual front end: transfer-event recall/precision, event-time error
  4.2 Matching precision/recall (engine-given-truth and end-to-end)
  4.3 Discrepancy detection: detection recall, detection precision
  4.4 False REVIEW on clean units
  4.5 Abstention correctness
  4.6 Latency
  4.7 Revision rate

All metrics report N, value, and where applicable a 95% CI.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..schema import Decision, DecisionState


def wilson_ci(p: float, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Wilson score 95% confidence interval for a proportion."""
    if n == 0:
        return 0.0, 1.0
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return max(0.0, center - spread), min(1.0, center + spread)


def upper_bound_zero_failures(n: int, z: float = 1.96) -> float:
    """95% upper bound when zero failures observed: 1 - 0.05^(1/n)."""
    if n == 0:
        return 1.0
    return 1.0 - (0.05 ** (1.0 / n))


@dataclass
class MetricValue:
    value: float
    n: int
    ci_low: float = 0.0
    ci_high: float = 1.0
    status: str = "measured"  # measured / unsupported / unavailable


@dataclass
class MetricsReport:
    """Full metrics report for a run."""
    # 4.1 Visual front end
    transfer_recall: Optional[MetricValue] = None
    transfer_precision: Optional[MetricValue] = None
    event_time_error_median: Optional[float] = None
    event_time_error_p90: Optional[float] = None

    # 4.2 Matching
    matching_precision_e2e: Optional[MetricValue] = None
    matching_precision_engine: Optional[MetricValue] = None
    matching_recall_e2e: Optional[MetricValue] = None
    matching_recall_engine: Optional[MetricValue] = None

    # 4.3 Discrepancy detection (REVIEW is the positive)
    detection_recall: Optional[MetricValue] = None
    detection_precision: Optional[MetricValue] = None

    # 4.4 False intervention
    false_review_rate: Optional[MetricValue] = None
    clean_abstain_rate: Optional[MetricValue] = None

    # 4.5 Abstention
    abstention_correctness: Optional[MetricValue] = None
    unnecessary_abstain_rate: Optional[MetricValue] = None
    coverage: Optional[MetricValue] = None

    # 4.6 Latency
    decision_latency_median: Optional[float] = None
    decision_latency_p95: Optional[float] = None
    video_fps: Optional[float] = None

    # 4.7 Revisions
    revision_rate: Optional[MetricValue] = None

    def to_dict(self) -> dict:
        result = {}
        for field_name in (
            "transfer_recall", "transfer_precision",
            "matching_precision_e2e", "matching_precision_engine",
            "matching_recall_e2e", "matching_recall_engine",
            "detection_recall", "detection_precision",
            "false_review_rate", "clean_abstain_rate",
            "abstention_correctness", "unnecessary_abstain_rate",
            "coverage", "revision_rate",
        ):
            mv = getattr(self, field_name)
            if mv is not None:
                result[field_name] = {
                    "value": mv.value,
                    "n": mv.n,
                    "ci_low": mv.ci_low,
                    "ci_high": mv.ci_high,
                    "status": mv.status,
                }
        for field_name in (
            "event_time_error_median", "event_time_error_p90",
            "decision_latency_median", "decision_latency_p95",
            "video_fps",
        ):
            mv = getattr(self, field_name)
            if mv is not None:
                result[field_name] = mv
        return result


def proportion_metric(successes: int, total: int, supported: bool = True) -> MetricValue:
    """Build a proportion metric with Wilson CI."""
    if total == 0:
        return MetricValue(value=0.0, n=0, ci_low=0.0, ci_high=1.0,
                          status="unsupported" if supported else "unsupported")
    p = successes / total
    ci_low, ci_high = wilson_ci(p, total)
    status = "supported" if supported else "unsupported"
    # Check if N too small for target claims
    if total < 30:
        status = "unsupported (n too small)"
    return MetricValue(value=p, n=total, ci_low=ci_low, ci_high=ci_high, status=status)


def rate_metric(successes: int, total: int, per_1000: bool = False, supported: bool = True) -> MetricValue:
    """Build a rate metric (e.g., false REVIEW rate)."""
    if total == 0:
        return MetricValue(value=0.0, n=0, ci_low=0.0, ci_high=1.0,
                          status="unsupported")
    if successes == 0:
        ub = upper_bound_zero_failures(total)
        return MetricValue(
            value=0.0, n=total, ci_low=0.0, ci_high=ub,
            status=f"unsupported (UB={ub*100:.1f}% per 100)" if per_1000 else f"unsupported (UB={ub*100:.1f}%)",
        )
    p = successes / total
    ci_low, ci_high = wilson_ci(p, total)
    scale = 1000.0 if per_1000 else 1.0
    return MetricValue(
        value=p * scale, n=total, ci_low=ci_low * scale, ci_high=ci_high * scale,
        status="measured",
    )


def score(
    decisions: List[Decision],
    ground_truth: List[dict],
    cfg,
) -> MetricsReport:
    """Score a set of decisions against ground truth.

    ground_truth: list of dicts with:
      {v_id, expected_state, scanned_truth, evidence_adequate, expected_match_s_id?}
    """
    report = MetricsReport()

    # Build lookup
    by_vid: Dict[str, Decision] = {}
    for d in decisions:
        if d.unit.get("type") == "visual_transfer":
            by_vid[d.unit.get("v_id")] = d
        # For INFO (orphan) decisions, they are not scored in 3-state metrics

    # 4.1 Visual front end (front-end recall/precision from ground truth)
    # We need visual event detection results; these come from a separate
    # visual evaluation pass. Here we score the reconciliation decisions.

    # 4.3 Discrepancy detection (REVIEW = positive)
    tp_review = 0
    fp_review = 0
    fn_review = 0
    for gt in ground_truth:
        d = by_vid.get(gt["v_id"])
        expected = gt["expected_state"]
        if expected == "REVIEW":
            if d is not None and d.state == DecisionState.REVIEW:
                tp_review += 1
            else:
                fn_review += 1
        else:
            if d is not None and d.state == DecisionState.REVIEW:
                fp_review += 1

    n_positive = sum(1 for g in ground_truth if g["expected_state"] == "REVIEW")
    n_negative = sum(1 for g in ground_truth if g["expected_state"] != "REVIEW")

    report.detection_recall = proportion_metric(tp_review, n_positive, supported=(n_positive >= 30))
    report.detection_precision = proportion_metric(tp_review, tp_review + fp_review) if (tp_review + fp_review) > 0 else MetricValue(0.0, 0, status="unsupported")

    # 4.2 Matching precision
    matched_correct = 0
    matched_total = 0
    matched_expected = 0
    for gt in ground_truth:
        d = by_vid.get(gt["v_id"])
        if gt["expected_state"] == "MATCHED":
            matched_expected += 1
            if d is not None and d.state == DecisionState.MATCHED:
                matched_total += 1
                # Check if the matched scan is the expected one
                selected = d.association.get("selected_s_id")
                if selected == gt.get("expected_match_s_id"):
                    matched_correct += 1

    report.matching_precision_e2e = proportion_metric(matched_correct, matched_total) if matched_total > 0 else MetricValue(0.0, 0, status="unsupported")
    report.matching_recall_e2e = proportion_metric(matched_correct, matched_expected) if matched_expected > 0 else MetricValue(0.0, 0, status="unsupported")

    # 4.4 False REVIEW on clean units
    clean_units = [g for g in ground_truth if g.get("scanned_truth") and g.get("evidence_adequate")]
    false_revs = sum(
        1 for g in clean_units
        if by_vid.get(g["v_id"]) and by_vid[g["v_id"]].state == DecisionState.REVIEW
    )
    report.false_review_rate = rate_metric(false_revs, len(clean_units), per_1000=True,
                                           supported=(len(clean_units) >= 30))

    # 4.5 Abstention correctness
    inadequate = [g for g in ground_truth if not g.get("evidence_adequate")]
    abstained_correct = sum(
        1 for g in inadequate
        if by_vid.get(g["v_id"]) and by_vid[g["v_id"]].state == DecisionState.ABSTAIN
    )
    report.abstention_correctness = proportion_metric(abstained_correct, len(inadequate),
                                                       supported=(len(inadequate) >= 30))

    # Unnecessary abstain
    adequate_units = [g for g in ground_truth if g.get("evidence_adequate")]
    unnecessary_abs = sum(
        1 for g in adequate_units
        if by_vid.get(g["v_id"]) and by_vid[g["v_id"]].state == DecisionState.ABSTAIN
    )
    report.unnecessary_abstain_rate = proportion_metric(unnecessary_abs, len(adequate_units))

    # Coverage
    decided = sum(
        1 for g in ground_truth
        if by_vid.get(g["v_id"]) and by_vid[g["v_id"]].state in (DecisionState.MATCHED, DecisionState.REVIEW)
    )
    report.coverage = proportion_metric(decided, len(ground_truth))

    return report


def score_vs_baseline(
    tracecart_decisions: List[Decision],
    baseline_decisions: List[Decision],
    ground_truth: List[dict],
    cfg,
) -> dict:
    """Compare TraceCart vs baseline on the same metrics."""
    tc_report = score(tracecart_decisions, ground_truth, cfg)
    base_report = score(baseline_decisions, ground_truth, cfg)

    return {
        "tracecart": tc_report.to_dict(),
        "baseline_timestamp_only": base_report.to_dict(),
    }