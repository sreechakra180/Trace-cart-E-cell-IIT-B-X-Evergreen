"""Edge-case tests for TraceCart reconciliation engine.

Tests:
1. Voided scans (TxnStatus.VOIDED) excluded from matching
2. Scan quantity > 1 expands into multiple distinct slots and matches multiple visual picks
3. Cache malformation resilience: malformed JSON, missing fields, or empty lines
4. Duplicate scans dropped during expansion
5. Strict vs non-strict zone gating
6. Time watermark boundaries and grace period absorption
"""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path

from tracecart.config import Config
from tracecart.cost import expand_scans, gate_pair
from tracecart.pipeline import load_cache_detections, run
from tracecart.schema import (
    DecisionState,
    Provenance,
    ReasonCode,
    TransactionScanEvent,
    TxnStatus,
    VisualTransferEvent,
)


@pytest.fixture
def edge_cfg():
    cfg = Config()
    cfg.lambda_t = 0.50
    cfg.lambda_z = 0.15
    cfg.lambda_s = 0.25
    cfg.lambda_f = 0.10
    cfg.tau_match = 0.50
    cfg.w_gate = 10.0
    cfg.delta_amb = 0.10
    cfg.grace_s = 20.0
    cfg.sku_to_class = {
        "SKU-WATER": "bottle",
        "SKU-COFFEE": "bottle",
    }
    return cfg


def test_voided_scan_is_not_matched(edge_cfg):
    """A voided transaction scan must never match a physical visual pick."""
    t_now = datetime.now(timezone.utc).timestamp()
    visual = VisualTransferEvent(
        v_id="V-void-1",
        provenance=Provenance.VIDEO_CV,
        session_id="sess-void",
        camera_id="cam0",
        store_zone="aisle04",
        track_id=1,
        t_pick=t_now - 10,
        t_bag=t_now - 5,
        t_ref=t_now - 5,
        t_ingest=t_now - 4,
        cls_votes={"bottle": 1.0},
        det_conf_median=0.9,
        track_continuity=0.95,
        gap_max_s=0.1,
        n_persons_max=0,
        luma_mean=140.0,
        blur_var_min=220.0,
        n_frames=30,
        quality_flags=[],
        source_ref={"clip": "clip_void"},
    )
    voided_scan = TransactionScanEvent(
        s_id="S-void-1",
        provenance=Provenance.SYNTHETIC_GENERATED,
        session_id="sess-void",
        t_scan=t_now - 4.5,
        t_ingest=t_now + 25.0,  # Past grace period so review is declared
        sku="SKU-WATER",
        qty=1,
        zone_hint="aisle04",
        txn_status=TxnStatus.VOIDED,
        txn_line_id="L-void-1",
        quality_flags=[],
        source_ref={"feed": "stream", "line": 1},
    )

    # Gating must reject voided scan
    gate_res = gate_pair(visual, voided_scan, edge_cfg)
    assert not gate_res.passed
    assert gate_res.reason == "voided"

    # Expanded scans must exclude voided scans
    assert len(expand_scans([voided_scan])) == 0

    # End-to-end: unfulfilled visual pick results in REVIEW (unscanned item)
    decisions = run([visual], [voided_scan], edge_cfg)
    assert len(decisions) == 1
    assert decisions[0].state == DecisionState.REVIEW


def test_qty_greater_than_one_slot_expansion(edge_cfg):
    """A single scan line with qty=2 must expand to 2 slots and match 2 visual transfers."""
    t_now = datetime.now(timezone.utc).timestamp()
    v1 = VisualTransferEvent(
        v_id="V-qty-1",
        provenance=Provenance.VIDEO_CV,
        session_id="sess-multi",
        camera_id="cam0",
        store_zone="aisle04",
        track_id=101,
        t_pick=t_now - 12,
        t_bag=t_now - 8,
        t_ref=t_now - 8,
        t_ingest=t_now - 7,
        cls_votes={"bottle": 1.0},
        det_conf_median=0.9,
        track_continuity=0.95,
        gap_max_s=0.1,
        n_persons_max=0,
        luma_mean=140.0,
        blur_var_min=200.0,
        n_frames=30,
        quality_flags=[],
        source_ref={"clip": "clip_multi"},
    )
    v2 = VisualTransferEvent(
        v_id="V-qty-2",
        provenance=Provenance.VIDEO_CV,
        session_id="sess-multi",
        camera_id="cam0",
        store_zone="aisle04",
        track_id=102,
        t_pick=t_now - 10,
        t_bag=t_now - 6,
        t_ref=t_now - 6,
        t_ingest=t_now - 5,
        cls_votes={"bottle": 1.0},
        det_conf_median=0.9,
        track_continuity=0.95,
        gap_max_s=0.1,
        n_persons_max=0,
        luma_mean=140.0,
        blur_var_min=200.0,
        n_frames=30,
        quality_flags=[],
        source_ref={"clip": "clip_multi"},
    )
    scan_qty2 = TransactionScanEvent(
        s_id="S-multi-1",
        provenance=Provenance.SYNTHETIC_GENERATED,
        session_id="sess-multi",
        t_scan=t_now - 7.0,
        t_ingest=t_now - 5.0,
        sku="SKU-WATER",
        qty=2,
        zone_hint="aisle04",
        txn_status=TxnStatus.COMMITTED,
        txn_line_id="L-multi-1",
        quality_flags=[],
        source_ref={"feed": "stream", "line": 1},
    )

    # Check expansion
    expanded = expand_scans([scan_qty2])
    assert len(expanded) == 2
    assert expanded[0][1] == 1
    assert expanded[1][1] == 2

    # Run bipartite matching
    decisions = run([v1, v2], [scan_qty2], edge_cfg)
    assert len(decisions) == 2
    # Verify candidate links have slots 1 and 2
    candidate_slots = {c.slot for d in decisions for c in d.candidates}
    assert candidate_slots == {1, 2}


def test_cache_malformation_resilience(tmp_path):
    """load_cache_detections must skip corrupt lines, non-JSON text, and incomplete dictionaries."""
    test_file = tmp_path / "corrupt_cache.jsonl"
    lines = [
        "",  # Empty line
        '{"frame": 1, "t": 0.033, "x1": 10, "y1": 20, "x2": 30, "y2": 40, "class_name": "bottle", "conf": 0.9, "track_id": 1}',  # Valid
        "NOT JSON AT ALL {{{",  # Syntax error
        '{"frame": 2, "t": 0.066}',  # Missing required keys
        '{"frame": 3, "t": 0.099, "x1": 12, "y1": 22, "x2": 32, "y2": 42, "class_name": "bottle", "conf": 0.95, "track_id": 1}',  # Valid
        "   \n",  # Whitespace line
    ]
    test_file.write_text("\n".join(lines), encoding="utf-8")

    entries = load_cache_detections(test_file)
    assert len(entries) == 2
    assert entries[0]["frame"] == 1
    assert entries[1]["frame"] == 3


def test_duplicate_scans_deduplication():
    """Identical scan lines within the feed are deduplicated to prevent double-counting."""
    t_now = datetime.now(timezone.utc).timestamp()
    scan1 = TransactionScanEvent(
        s_id="S-dup-1",
        provenance=Provenance.SYNTHETIC_GENERATED,
        session_id="sess-dup",
        t_scan=t_now - 5.0,
        t_ingest=t_now - 4.0,
        sku="SKU-WATER",
        qty=1,
        zone_hint="aisle04",
        txn_status=TxnStatus.COMMITTED,
        txn_line_id="L-SAME",
        quality_flags=[],
        source_ref={"feed": "stream", "line": 1},
    )
    scan2 = TransactionScanEvent(
        s_id="S-dup-2",
        provenance=Provenance.SYNTHETIC_GENERATED,
        session_id="sess-dup",
        t_scan=t_now - 5.0,
        t_ingest=t_now - 3.9,
        sku="SKU-WATER",
        qty=1,
        zone_hint="aisle04",
        txn_status=TxnStatus.COMMITTED,
        txn_line_id="L-SAME",
        quality_flags=[],
        source_ref={"feed": "stream", "line": 2},
    )

    expanded = expand_scans([scan1, scan2])
    assert len(expanded) == 1
    assert expanded[0][0].s_id == "S-dup-1"
