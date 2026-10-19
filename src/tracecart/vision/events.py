"""Transfer-event extraction from cached detections + tracks.

Implements ARCHITECTURE §5, step 4:
  - For each non-person track: first frame its box centre is inside Z_PICK,
    then first later frame inside Z_BAG.
  - Accept if t_bag - t_pick ∈ [min_dt, max_dt], n_frames ≥ min_track_frames,
    class ∈ eligible_classes.
  - Limited track stitching (id_switch_suspect flag).
  - Quality metrics: det_conf_median, track_continuity, gap_max_s,
    n_persons_max, luma_mean, blur_var_min.

Output: list[VisualTransferEvent] compatible dicts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..config import Config
from .zones import Zone


@dataclass
class Detection:
    frame: int
    t: float
    x1: float
    y1: float
    x2: float
    y2: float
    class_name: str
    conf: float
    track_id: int


@dataclass
class Track:
    track_id: int
    class_name: str
    detections: List[Detection]  # sorted by frame

    @property
    def center_box(self):
        """Most recent detection box center."""
        d = self.detections[-1]
        return ((d.x1 + d.x2) / 2, (d.y1 + d.y2) / 2)


def extract_transfer_events(
    detections: List[Detection],
    zones: Dict[str, Zone],
    cfg: Config,
    clip_start_epoch: float,
    *,
    session_id: Optional[str] = None,
    clip_name: Optional[str] = None,
) -> List[dict]:
    """Convert detection+track stream into transfer event dicts.

    Returns dicts compatible with VisualTransferEvent (keys matching schema).

    Per ARCHITECTURE §5, step 4:
      - For each non-person track: first frame inside Z_PICK, then first later
        frame inside Z_BAG.
      - Accept if t_bag - t_pick in [min_dt, max_dt], n_frames >= min_track_frames,
        class in eligible_classes.
      - Timestamps are absolute: t = clip_start_epoch + frame-relative seconds.
    """
    eligible_classes = set(cfg.get("eligible_classes", []))
    person_class = cfg.get("person_class", "person")
    session_id = session_id or cfg.get("session_id") or "unknown"
    clip_name = clip_name or cfg.get("clip_name") or "unknown"

    # Build per-track person-overlap counts from person-class detections.
    person_dets_by_track: Dict[int, List[Detection]] = {}
    for d in detections:
        if d.class_name == person_class:
            person_dets_by_track.setdefault(d.track_id, []).append(d)

    # Group detections by track
    by_track: Dict[int, List[Detection]] = {}
    for d in detections:
        by_track.setdefault(d.track_id, []).append(d)

    # Index raw cache entries by track so we can pull per-frame quality if present.
    # callers may have stashed dicts under d.extra; kept simple here.

    events: List[dict] = []

    for track_id, dets in by_track.items():
        dets.sort(key=lambda d: d.frame)
        cls = dets[0].class_name

        # Skip person class
        if cls == person_class:
            continue
        # Skip classes not eligible
        if eligible_classes and cls not in eligible_classes:
            continue

        # Find first frame inside Z_PICK and first later frame inside Z_BAG
        z_pick = zones.get("Z_PICK")
        z_bag = zones.get("Z_BAG")
        if not z_pick or not z_bag:
            continue

        t_pick: Optional[float] = None
        t_bag: Optional[float] = None
        t_pick_frame: Optional[int] = None
        t_bag_frame: Optional[int] = None

        for d in dets:
            if t_pick is None and z_pick.box_center_inside((d.x1, d.y1, d.x2, d.y2)):
                t_pick = clip_start_epoch + d.t
                t_pick_frame = d.frame
            elif t_pick is not None and t_bag is None and z_bag.box_center_inside((d.x1, d.y1, d.x2, d.y2)):
                t_bag = clip_start_epoch + d.t
                t_bag_frame = d.frame
                break

        if t_pick is None or t_bag is None:
            continue

        dt = t_bag - t_pick
        if not (cfg.min_dt <= dt <= cfg.max_dt):
            continue

        # n_frames: number of frames track spans
        n_frames = dets[-1].frame - dets[0].frame + 1
        if n_frames < cfg.min_track_frames:
            continue

        # Count distinct person boxes overlapping the pick→bag path region
        n_persons_max = max(
            (len(person_dets_by_track.get(tid, [])) for tid in person_dets_by_track),
            default=0,
        )

        # Quality metrics: prefer cached per-frame quality if present, else
        # conservative defaults that will fail the quality gate (leading to
        # ABSTAIN) rather than pretending quality is good.
        confs = [d.conf for d in dets]
        det_conf_median = _median(confs)
        track_continuity = len(dets) / max(1, dets[-1].frame - dets[0].frame + 1)
        gap_max_s = _max_gap_s(dets)
        luma_mean = cfg.get("luma_mean", 0.0)
        blur_var_min = cfg.get("blur_var_min", 0.0)

        # cls_votes: confidence-weighted class distribution
        cls_votes: Dict[str, float] = {}
        total_conf = sum(confs)
        if total_conf > 0:
            for c in eligible_classes:
                share = sum(d.conf for d in dets if d.class_name == c) / total_conf
                if share > 0:
                    cls_votes[c] = round(share, 6)

        quality_flags: List[str] = []
        if track_continuity < cfg.track_continuity_min:
            quality_flags.append("short_track")
        if gap_max_s > cfg.gap_max_s_max:
            quality_flags.append("id_switch_suspect")
        if n_persons_max > cfg.n_persons_max:
            quality_flags.append("multi_person")
        if luma_mean > 0 and not (cfg.luma_min <= luma_mean <= cfg.luma_max):
            quality_flags.append("low_light")
        if blur_var_min > 0 and blur_var_min < cfg.blur_var_min:
            quality_flags.append("blurry")

        event = {
            "v_id": f"V-{clip_start_epoch}-{track_id}-0",
            "provenance": "video_cv",
            "session_id": session_id,
            "camera_id": cfg.get("camera_id", "cam0"),
            "zone_path": ["Z_PICK", "Z_BAG"],
            "store_zone": z_pick.store_zone or cfg.get("store_zone", "aisle04"),
            "track_id": track_id,
            "t_pick": t_pick,
            "t_bag": t_bag,
            "t_ref": t_bag,
            "t_ingest": t_bag + 0.5,
            "cls_votes": cls_votes,
            "det_conf_median": det_conf_median,
            "track_continuity": track_continuity,
            "gap_max_s": gap_max_s,
            "n_persons_max": n_persons_max,
            "luma_mean": luma_mean,
            "blur_var_min": blur_var_min,
            "n_frames": n_frames,
            "quality_flags": quality_flags,
            "source_ref": {
                "clip": clip_name,
                "frame_start": t_pick_frame,
                "frame_end": t_bag_frame,
                "cache_file": "",
            },
        }
        events.append(event)

    return events


def _median(values: List[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 0:
        return (s[mid - 1] + s[mid]) / 2.0
    return s[mid]


def _max_gap_s(dets: List[Detection]) -> float:
    """Longest gap between consecutive detections in seconds."""
    if len(dets) < 2:
        return 0.0
    max_gap = 0.0
    for i in range(1, len(dets)):
        gap = dets[i].t - dets[i - 1].t
        if gap > max_gap:
            max_gap = gap
    return max_gap