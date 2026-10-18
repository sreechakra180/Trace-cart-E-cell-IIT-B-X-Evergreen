"""Scan feed generator (G1) — synthetic, seeded.

Implements ARCHITECTURE §6:
  Input: clip's ground-truth annotation (t_pick, t_bag, prop, scanned: yes/no)
         + scenario recipe.
  Output: JSONL with provenance `synthetic_generated`.

Noise model (documented, seeds recorded in manifest):
  - scan_time = t_bag + U(-6, +6) s for clean (ordinary timing)
            or recipe-specific (e.g., +9 s for "late but valid").
  - ingest_delay = lognormal, clipped, or recipe-specific
            (e.g., +35 s → delayed event).
  - Recipes: clean, unscanned, late_ingest, duplicate_exact,
             duplicate_heuristic, bad_ts, naive_ts, sku_missing,
             sku_class_conflict, competing_pair, voided,
             scan_before_pickup, feed_gap.
  - Heartbeats every 5 s of ingest time; feed_gap removes them across window.

Leakage guard: generator reads ground truth; engine never does.
Test split's seeds are different and unused during tuning.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..schema import TxnStatus


@dataclass
class GroundTruth:
    """One row from annotations/<clip>.csv."""
    clip: str
    transfer_id: str
    prop: str  # e.g., "bottle", "cup"
    t_pick: float  # UTC epoch seconds
    t_bag: float
    scanned_truth: bool  # yes/no from manifest
    evidence_adequate: bool  # rubric-based
    inadequate_cause: Optional[str] = None
    annotator: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class Recipe:
    """Scenario recipe dictating noise injection."""
    name: str
    scan_time_offset_s: Tuple[float, float] = (-6.0, 6.0)  # uniform range
    ingest_delay_s: Tuple[float, float] = (0.0, 0.0)      # uniform range
    duplicate_exact: bool = False
    duplicate_heuristic: bool = False
    missing_sku: bool = False
    sku_class_conflict: bool = False
    competing_pair: bool = False
    voided: bool = False
    scan_before_pickup: bool = False
    feed_gap: bool = False
    bad_ts: bool = False
    naive_ts: bool = False


# Predefined recipes matching ARCHITECTURE §6 and EVALUATION_PLAN §3
RECIPES: Dict[str, Recipe] = {
    "clean": Recipe(
        name="clean",
        scan_time_offset_s=(-6.0, 6.0),
        ingest_delay_s=(0.0, 5.0),  # small random delay
    ),
    "unscanned": Recipe(
        name="unscanned",
        scan_time_offset_s=(0.0, 0.0),  # not used (no scan generated)
        ingest_delay_s=(0.0, 0.0),
    ),
    "late_ingest": Recipe(
        name="late_ingest",
        scan_time_offset_s=(-6.0, 6.0),
        ingest_delay_s=(30.0, 40.0),  # +30-40s ingest delay
    ),
    "duplicate_exact": Recipe(
        name="duplicate_exact",
        scan_time_offset_s=(-6.0, 6.0),
        ingest_delay_s=(0.0, 5.0),
        duplicate_exact=True,
    ),
    "duplicate_heuristic": Recipe(
        name="duplicate_heuristic",
        scan_time_offset_s=(-6.0, 6.0),
        ingest_delay_s=(0.0, 5.0),
        duplicate_heuristic=True,
    ),
    "bad_ts": Recipe(
        name="bad_ts",
        scan_time_offset_s=(-6.0, 6.0),
        ingest_delay_s=(0.0, 5.0),
        bad_ts=True,  # malformed ISO-8601
    ),
    "naive_ts": Recipe(
        name="naive_ts",
        scan_time_offset_s=(-6.0, 6.0),
        ingest_delay_s=(0.0, 5.0),
        naive_ts=True,  # timestamp without timezone
    ),
    "sku_missing": Recipe(
        name="sku_missing",
        scan_time_offset_s=(-6.0, 6.0),
        ingest_delay_s=(0.0, 5.0),
        missing_sku=True,
    ),
    "sku_class_conflict": Recipe(
        name="sku_class_conflict",
        scan_time_offset_s=(-6.0, 6.0),
        ingest_delay_s=(0.0, 5.0),
        sku_class_conflict=True,
    ),
    "competing_pair": Recipe(
        name="competing_pair",
        scan_time_offset_s=(-6.0, 6.0),
        ingest_delay_s=(0.0, 5.0),
        competing_pair=True,
    ),
    "voided": Recipe(
        name="voided",
        scan_time_offset_s=(-6.0, 6.0),
        ingest_delay_s=(0.0, 5.0),
        voided=True,
    ),
    "scan_before_pickup": Recipe(
        name="scan_before_pickup",
        scan_time_offset_s=(-60.0, -30.0),  # scan before pickup
        ingest_delay_s=(0.0, 5.0),
        scan_before_pickup=True,
    ),
    "feed_gap": Recipe(
        name="feed_gap",
        scan_time_offset_s=(0.0, 0.0),  # not used
        ingest_delay_s=(0.0, 0.0),
        feed_gap=True,
    ),
}


def _uniform(a: float, b: float) -> float:
    return random.uniform(a, b)


def _log_normal_clip(mean: float, sigma: float, clip_min: float, clip_max: float) -> float:
    """Log-normal sample clipped to [clip_min, clip_max]."""
    if mean <= 0:
        return 0.0
    val = np.random.lognormal(mean=mean, sigma=sigma)
    return max(clip_min, min(clip_max, val))


def generate_scan_event(
    gt: GroundTruth,
    recipe: Recipe,
    seed: int,
    sku_map: Dict[str, str],
) -> List[dict]:
    """Generate one or more TransactionScanEvent dicts from GT + recipe.

    Returns list of dicts compatible with TransactionScanEvent.
    """
    random.seed(seed)
    np.random.seed(seed)

    events: List[dict] = []

    if recipe.name == "unscanned":
        # No scan generated
        return events

    if recipe.feed_gap:
        # No scan events generated (simulates feed downtime)
        return events

    # Determine scan time
    if recipe.scan_before_pickup:
        t_scan = gt.t_pick + _uniform(*recipe.scan_time_offset_s)
    else:
        t_scan = gt.t_bag + _uniform(*recipe.scan_time_offset_s)

    # Determine ingest time
    if recipe.name == "late_ingest":
        # Special case: large fixed delay
        t_ingest = t_scan + 35.0  # example from ARCHITECTURE §6
    else:
        base_delay = _uniform(*recipe.ingest_delay_s)
        t_ingest = t_scan + base_delay

    # Base event
    base_event = {
        "s_id": f"S-{gt.clip}-{gt.transfer_id}-{seed}",
        "provenance": "synthetic_generated",
        "session_id": gt.clip,  # session_id from manifest (clip name)
        "t_scan": t_scan,
        "t_ingest": t_ingest,
        "sku": gt.prop if not recipe.missing_sku else None,
        "qty": 2 if recipe.competing_pair else 1,
        "zone_hint": "aisle04" if not recipe.missing_sku else None,
        "txn_status": TxnStatus.VOIDED.value if recipe.voided else TxnStatus.COMMITTED.value,
        "txn_line_id": f"L{seed}" if not recipe.duplicate_exact else f"L{seed}",  # exact duplicate uses same ID
        "source_seq": seed,
        "quality_flags": [],
        "source_ref": {
            "feed": f"feed_{gt.clip}",
            "line": seed,
        },
    }

    # Apply recipe-specific modifications
    quality_flags = []

    if recipe.bad_ts:
        # Malformed timestamp string
        base_event["t_scan"] = "not-a-timestamp"
        quality_flags.append("ts_invalid")
    elif recipe.naive_ts:
        # Timestamp without timezone (ISO-8601 but naive)
        base_event["t_scan"] = f"{datetime.fromtimestamp(t_scan).isoformat()}T00:00:00"
        quality_flags.append("ts_naive")
    else:
        # Keep as float epoch seconds
        pass

    if recipe.missing_sku:
        base_event["sku"] = None
        quality_flags.append("sku_missing")

    if recipe.sku_class_conflict and sku_map:
        # Map SKU to wrong class on purpose
        base_event["sku"] = "SKU-CONFLICT"
        quality_flags.append("sku_class_conflict")

    if quality_flags:
        base_event["quality_flags"] = quality_flags

    events.append(base_event)

    # Handle duplicate recipes
    if recipe.duplicate_exact:
        # Exact duplicate: same s_id, same txn_line_id, same everything
        dup = dict(base_event)
        dup["s_id"] = f"S-{gt.clip}-{gt.transfer_id}-{seed}-dup"
        events.append(dup)

    if recipe.duplicate_heuristic:
        # Heuristic duplicate: same sku, <1.5 s apart, no idempotency key
        hep = dict(base_event)
        hep["t_scan"] = t_scan + _uniform(0.2, 1.4)  # within 1.5s
        hep["t_ingest"] = hep["t_scan"] + _uniform(*recipe.ingest_delay_s)
        hep["txn_line_id"] = None  # no idempotency key
        hep["source_seq"] = seed + 1000
        events.append(hep)

    if recipe.competing_pair:
        # Competing pair: two scans for one visual event (qty=2 already set)
        comp = dict(base_event)
        comp["t_scan"] = t_scan + _uniform(2.0, 4.0)
        comp["t_ingest"] = comp["t_scan"] + _uniform(*recipe.ingest_delay_s)
        comp["source_seq"] = seed + 2000
        events.append(comp)

    return events


def generate_heartbeat(
    session_id: str,
    start_time: float,
    end_time: float,
    interval: float = 5.0,
    seed: int = 0,
) -> List[dict]:
    """Generate feed heartbeat events.

    Returns list of dicts compatible with FeedHeartbeat.
    """
    random.seed(seed)
    heartbeats: List[dict] = []
    t = start_time
    hb_id = 0
    while t <= end_time:
        heartbeats.append({
            "feed_id": f"feed-{session_id}",
            "session_id": session_id,
            "t_ingest": t,
            "source_ref": {"feed": f"feed-{session_id}", "line": hb_id},
        })
        t += interval
        hb_id += 1
    return heartbeats


def generate_feed_for_clip(
    clip_name: str,
    ground_truths: List[GroundTruth],
    recipe_name: str,
    base_seed: int,
    sku_map: Dict[str, str],
) -> Tuple[List[dict], List[dict]]:
    """Generate scan feed + heartbeats for one clip.

    Returns (scan_events, heartbeats) as lists of dicts.
    """
    recipe = RECIPES[recipe_name]
    scan_events: List[dict] = []
    hbs: List[dict] = []

    for gt in ground_truths:
        seed = base_seed + hash(gt.transfer_id) % 10000
        events = generate_scan_event(gt, recipe, seed, sku_map)
        scan_events.extend(events)

    # Heartbeats cover the whole clip duration
    if ground_truths:
        t_min = min(g.t_bag for g in ground_truths)
        t_max = max(g.t_bag for g in ground_truths)
        hbs = generate_heartbeat(
            session_id=clip_name,
            start_time=t_min - 10.0,
            end_time=t_max + 30.0,
            seed=base_seed + 50000,
        )

    return scan_events, hbs


def write_feed_jsonl(
    scan_events: List[dict],
    heartbeats: List[dict],
    scan_path: str | Path,
    hb_path: str | Path,
) -> None:
    """Write scan events and heartbeats to JSONL files."""
    scan_path = Path(scan_path)
    hb_path = Path(hb_path)
    scan_path.parent.mkdir(parents=True, exist_ok=True)
    hb_path.parent.mkdir(parents=True, exist_ok=True)

    with open(scan_path, "w", encoding="utf-8") as f:
        for event in scan_events:
            f.write(json.dumps(event) + "\n")

    with open(hb_path, "w", encoding="utf-8") as f:
        for hb in heartbeats:
            f.write(json.dumps(hb) + "\n")


# Helper for CLI/testing
def generate_demo_feeds(
    data_dir: str | Path = "data",
    scenario: str = "S03",
    seed: int = 42,
) -> None:
    """Generate feeds for demo scenario using hardcoded ground truth.
    This is a placeholder — real implementation loads from annotations/.
    """
    data_dir = Path(data_dir)
    clips_dir = data_dir / "clips"
    manifests_dir = data_dir / "manifests"
    feeds_dir = data_dir / "feeds"
    feeds_dir.mkdir(parents=True, exist_ok=True)

    # Hardcoded GT for demo (normally loaded from annotations/<clip>.csv)
    demo_gt = [
        GroundTruth(
            clip="clip01_S01",
            transfer_id="T01",
            prop="bottle",
            t_pick=1000.0,
            t_bag=1005.0,
            scanned_truth=True,
            evidence_adequate=True,
        ),
        GroundTruth(
            clip="clip02_S03",
            transfer_id="T02",
            prop="apple",
            t_pick=1000.0,
            t_bag=1005.0,
            scanned_truth=True,
            evidence_adequate=True,
        ),
        GroundTruth(
            clip="clip03_S03",
            transfer_id="T03",
            prop="banana",
            t_pick=1010.0,
            t_bag=1015.0,
            scanned_truth=False,
            evidence_adequate=True,
        ),
    ]

    sku_map = {"SKU-WATER": "bottle", "SKU-APPLE": "apple", "SKU-BANANA": "banana", "SKU-ORANGE": "orange"}

    for gt in demo_gt:
        scan_events, hbs = generate_feed_for_clip(
            clip_name=gt.clip,
            ground_truths=[gt],
            recipe_name="clean" if gt.scanned_truth else "unscanned",
            base_seed=seed,
            sku_map=sku_map,
        )
        write_feed_jsonl(
            scan_events,
            hbs,
            scan_path=feeds_dir / f"feed_{gt.clip}.jsonl",
            hb_path=feeds_dir / f"hb_{gt.clip}.jsonl",
        )

    # Also generate standard scenario feeds (S01-S08) for CLI runs
    scenarios_meta = [
        ("S01", [GroundTruth("S01", "T01", "bottle", 1000.0, 1005.0, True, True)], "clean"),
        ("S02", [GroundTruth("S02", "T02", "apple", 1000.0, 1005.0, False, True)], "unscanned"),
        ("S03", [
            GroundTruth("S03", "T01", "bottle", 1000.0, 1005.0, True, True),
            GroundTruth("S03", "T02", "apple", 1002.0, 1007.0, True, True)
        ], "clean"),
        ("S04", [GroundTruth("S04", "T01", "orange", 1000.0, 1005.0, True, True)], "clean"),
        ("S08", [GroundTruth("S08", "T01", "banana", 1000.0, 1005.0, False, False)], "unscanned"),
    ]

    for sc_name, gts, recipe in scenarios_meta:
        scan_events, hbs = generate_feed_for_clip(
            clip_name=sc_name,
            ground_truths=gts,
            recipe_name=recipe,
            base_seed=seed,
            sku_map=sku_map,
        )
        write_feed_jsonl(
            scan_events,
            hbs,
            scan_path=feeds_dir / f"feed_{sc_name}.jsonl",
            hb_path=feeds_dir / f"hb_{sc_name}.jsonl",
        )
    print(f"Generated scenario feeds in {feeds_dir}")


if __name__ == "__main__":
    generate_demo_feeds()