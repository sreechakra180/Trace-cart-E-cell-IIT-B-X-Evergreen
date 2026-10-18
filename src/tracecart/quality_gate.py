"""Evidence-quality gate (R3).

Per ARCHITECTURE §8:
  - det_conf_median ≥ 0.45
  - track_continuity ≥ 0.70
  - gap_max_s ≤ 1.0
  - n_frames ≥ 8
  - n_persons_max ≤ 1
  - luma_mean ∈ [40, 220], blur_var_min ≥ 50
  - timestamps valid, fps_unreliable absent
  - feed: heartbeat watermark ≥ t_ref + G (grace period) and no feed_gap

Q_pass = AND of all components (conservative: one weak link blocks REVIEW).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .schema import EvidenceQuality
from .config import Config


@dataclass
class GateResult:
    passed: bool
    failed: List[str]  # component names that failed


def _feed_healthy(
    watermark: Optional[float],
    t_ref: float,
    cfg: Config,
    has_feed_gap: bool = False,
) -> bool:
    if watermark is None:
        return False
    if has_feed_gap:
        return False
    if watermark < t_ref + cfg.grace_s:
        return False
    return True


def evaluate_quality(
    det_conf_median: float,
    track_continuity: float,
    gap_max_s: float,
    n_frames: int,
    n_persons_max: int,
    luma_mean: float,
    blur_var_min: float,
    timestamps_valid: bool,
    fps_unreliable: bool,
    watermark: Optional[float],
    t_ref: float,
    cfg: Config,
    has_feed_gap: bool = False,
) -> GateResult:
    failed: List[str] = []

    if det_conf_median < cfg.det_conf_min:
        failed.append("det_conf_median")
    if track_continuity < cfg.track_continuity_min:
        failed.append("track_continuity")
    if gap_max_s > cfg.gap_max_s_max:
        failed.append("gap_max_s")
    if n_frames < cfg.n_frames_min:
        failed.append("n_frames")
    if n_persons_max > cfg.n_persons_max:
        failed.append("n_persons_max")
    if not (cfg.luma_min <= luma_mean <= cfg.luma_max):
        failed.append("frame_quality_luma")
    if blur_var_min < cfg.blur_var_min:
        failed.append("frame_quality_blur")
    if not timestamps_valid:
        failed.append("timestamps_invalid")
    if fps_unreliable:
        failed.append("fps_unreliable")
    if not _feed_healthy(watermark, t_ref, cfg, has_feed_gap):
        failed.append("feed_unhealthy")

    return GateResult(passed=(len(failed) == 0), failed=failed)


def evidence_quality_from_event_and_feed(
    visual_quality_flags,
    feed_healthy: bool,
    cfg: Config,
) -> GateResult:
    """Build a GateResult from a VisualTransferEvent's quality_flags.

    Convenience wrapper: flags map directly to failed components.
    """
    failed = []
    for flag in visual_quality_flags:
        flag_str = str(flag.value) if hasattr(flag, "value") else str(flag)
        if flag_str == "ts_invalid":
            failed.append("timestamps_invalid")
        elif flag_str == "short_track":
            failed.append("n_frames")
        elif flag_str == "multi_person":
            failed.append("n_persons_max")
        elif flag_str == "low_light":
            failed.append("frame_quality_luma")
        elif flag_str == "blurry":
            failed.append("frame_quality_blur")
        elif flag_str == "fps_unreliable":
            failed.append("fps_unreliable")
        elif flag_str == "id_switch_suspect":
            failed.append("track_continuity")
    if not feed_healthy:
        failed.append("feed_unhealthy")
    return GateResult(passed=(len(failed) == 0), failed=failed)


def quality_pass(
    det_conf_median: float,
    track_continuity: float,
    gap_max_s: float,
    n_frames: int,
    n_persons_max: int,
    luma_mean: float,
    blur_var_min: float,
    timestamps_valid: bool,
    fps_unreliable: bool,
    watermark: Optional[float],
    t_ref: float,
    cfg: Config,
    has_feed_gap: bool = False,
) -> bool:
    """Convenience: returns True iff Q_pass."""
    result = evaluate_quality(
        det_conf_median, track_continuity, gap_max_s, n_frames,
        n_persons_max, luma_mean, blur_var_min, timestamps_valid,
        fps_unreliable, watermark, t_ref, cfg, has_feed_gap,
    )
    return result.passed
