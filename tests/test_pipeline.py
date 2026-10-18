"""Comprehensive unit, scenario, edge-case, and API tests for TraceCart."""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from tracecart.schema import (
    VisualTransferEvent,
    TransactionScanEvent,
    Provenance,
    TxnStatus,
    DecisionState,
    ReasonCode,
)
from tracecart.config import Config
from tracecart.pipeline import run
from tracecart.baseline import run_baseline
from tracecart.eval.metrics import score, wilson_ci, upper_bound_zero_failures
from app.server import app


@pytest.fixture
def base_cfg():
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
        "SKU-ORANGE": "orange",
        "SKU-APPLE": "apple",
        "SKU-STEAK": "steak",
    }
    cfg.fps_assumed = 30.0
    return cfg


# 1. Clean MATCHED test (S01)
def test_s01_clean_matched(base_cfg):
    t_now = datetime.now(timezone.utc).timestamp()
    clean_visual = VisualTransferEvent(
        v_id="V-clip01-1-0",
        provenance=Provenance.VIDEO_CV,
        session_id="session-test",
        camera_id="cam0",
        store_zone="aisle04",
        track_id=1,
        t_pick=t_now - 10,
        t_bag=t_now - 5,
        t_ref=t_now - 5,
        t_ingest=t_now - 4,
        cls_votes={"bottle": 1.0},
        det_conf_median=0.8,
        track_continuity=0.95,
        gap_max_s=0.2,
        n_persons_max=0,
        luma_mean=120.0,
        blur_var_min=200.0,
        n_frames=30,
        quality_flags=[],
        source_ref={"clip": "clip01"},
    )
    clean_scan = TransactionScanEvent(
        s_id="S-feed-1",
        provenance=Provenance.SYNTHETIC_GENERATED,
        session_id="session-test",
        t_scan=t_now - 4.5,
        t_ingest=t_now - 4,
        sku="SKU-WATER",
        qty=1,
        zone_hint="aisle04",
        txn_status=TxnStatus.COMMITTED,
        txn_line_id="L1",
        quality_flags=[],
        source_ref={"feed": "feed1", "line": 1},
    )

    decisions = run([clean_visual], [clean_scan], base_cfg)
    assert len(decisions) == 1
    assert decisions[0].state == DecisionState.MATCHED
    assert decisions[0].rule_id == "R10"
    assert decisions[0].association["selected_s_id"] == "S-feed-1"


# 2. Unscanned REVIEW test (S02)
def test_s02_unscanned_review(base_cfg):
    t_now = datetime.now(timezone.utc).timestamp()
    unscanned_visual = VisualTransferEvent(
        v_id="V-clip02-2-0",
        provenance=Provenance.VIDEO_CV,
        session_id="session-test",
        camera_id="cam0",
        store_zone="aisle04",
        track_id=2,
        t_pick=t_now - 30,
        t_bag=t_now - 25,
        t_ref=t_now - 25,
        t_ingest=t_now - 24,
        cls_votes={"apple": 1.0},
        det_conf_median=0.85,
        track_continuity=0.90,
        gap_max_s=0.3,
        n_persons_max=0,
        luma_mean=100.0,
        blur_var_min=150.0,
        n_frames=25,
        quality_flags=[],
        source_ref={"clip": "clip02"},
    )

    decisions = run([unscanned_visual], [], base_cfg)
    assert len(decisions) == 1
    assert decisions[0].state == DecisionState.REVIEW
    assert decisions[0].rule_id == "R20"
    assert "No compatible scan event" in decisions[0].recommended_action


# 3. Adverse Optical Quality ABSTAIN test (S08)
def test_s08_bad_quality_abstain(base_cfg):
    t_now = datetime.now(timezone.utc).timestamp()
    bad_visual = VisualTransferEvent(
        v_id="V-clip03-3-0",
        provenance=Provenance.VIDEO_CV,
        session_id="session-test",
        camera_id="cam0",
        store_zone="aisle04",
        track_id=3,
        t_pick=t_now - 50,
        t_bag=t_now - 45,
        t_ref=t_now - 45,
        t_ingest=t_now - 44,
        cls_votes={"banana": 1.0},
        det_conf_median=0.3,
        track_continuity=0.50,
        gap_max_s=3.0,
        n_persons_max=2,
        luma_mean=20.0,
        blur_var_min=10.0,
        n_frames=5,
        quality_flags=[],
        source_ref={"clip": "clip03"},
    )

    decisions = run([bad_visual], [], base_cfg)
    assert len(decisions) == 1
    # Verify poor visual evidence does not trigger REVIEW! It must safely ABSTAIN
    assert decisions[0].state == DecisionState.ABSTAIN
    assert decisions[0].rule_id in ("R21", "R01")


# 4. Delayed Scan arriving within grace period (S04)
def test_delayed_scan_absorbed_by_grace(base_cfg):
    t_now = datetime.now(timezone.utc).timestamp()
    visual = VisualTransferEvent(
        v_id="V-delayed-1",
        provenance=Provenance.VIDEO_CV,
        session_id="session-delayed",
        camera_id="cam0",
        store_zone="aisle04",
        track_id=4,
        t_pick=t_now - 18.0,
        t_bag=t_now - 14.0,
        t_ref=t_now - 14.0,
        t_ingest=t_now - 13.5,
        cls_votes={"orange": 1.0},
        det_conf_median=0.90,
        track_continuity=0.95,
        gap_max_s=0.1,
        n_persons_max=0,
        luma_mean=130.0,
        blur_var_min=190.0,
        n_frames=35,
        quality_flags=[],
        source_ref={"clip": "clip_delayed"},
    )
    # Scan occurs 7 seconds after bag entry (within W_gate=10s and grace=20s)
    scan = TransactionScanEvent(
        s_id="S-delayed-1",
        provenance=Provenance.SYNTHETIC_GENERATED,
        session_id="session-delayed",
        t_scan=t_now - 7.0,
        t_ingest=t_now - 6.5,
        sku="SKU-ORANGE",
        qty=1,
        zone_hint="aisle04",
        txn_status=TxnStatus.COMMITTED,
        txn_line_id="L-del",
        quality_flags=[],
        source_ref={"feed": "stream", "line": 1},
    )

    decisions = run([visual], [scan], base_cfg)
    assert len(decisions) == 1
    assert decisions[0].state == DecisionState.MATCHED
    assert decisions[0].rule_id == "R10"


# 5. Duplicate transaction scan handling
def test_duplicate_transaction_scan(base_cfg):
    t_now = datetime.now(timezone.utc).timestamp()
    visual = VisualTransferEvent(
        v_id="V-dup-1",
        provenance=Provenance.VIDEO_CV,
        session_id="session-dup",
        camera_id="cam0",
        store_zone="aisle04",
        track_id=5,
        t_pick=t_now - 8.0,
        t_bag=t_now - 5.0,
        t_ref=t_now - 5.0,
        t_ingest=t_now - 4.8,
        cls_votes={"bottle": 1.0},
        det_conf_median=0.88,
        track_continuity=0.92,
        gap_max_s=0.1,
        n_persons_max=0,
        luma_mean=140.0,
        blur_var_min=200.0,
        n_frames=30,
        quality_flags=[],
        source_ref={"clip": "clip_dup"},
    )
    # Original scan
    scan1 = TransactionScanEvent(
        s_id="S-dup-1",
        provenance=Provenance.SYNTHETIC_GENERATED,
        session_id="session-dup",
        t_scan=t_now - 4.5,
        t_ingest=t_now - 4.0,
        sku="SKU-WATER",
        qty=1,
        zone_hint="aisle04",
        txn_status=TxnStatus.COMMITTED,
        txn_line_id="L-dup-1",
        quality_flags=[],
        source_ref={"feed": "stream", "line": 1},
    )
    # Duplicate scan record with same timestamp & line
    scan2 = TransactionScanEvent(
        s_id="S-dup-2",
        provenance=Provenance.SYNTHETIC_GENERATED,
        session_id="session-dup",
        t_scan=t_now - 4.5,
        t_ingest=t_now - 4.0,
        sku="SKU-WATER",
        qty=1,
        zone_hint="aisle04",
        txn_status=TxnStatus.COMMITTED,
        txn_line_id="L-dup-1",
        quality_flags=[ReasonCode.POSSIBLE_DUPLICATE],
        source_ref={"feed": "stream", "line": 2},
    )

    decisions = run([visual], [scan1, scan2], base_cfg)
    assert len(decisions) >= 1
    # Visual event must match cleanly to one slot, other scan becomes orphan INFO
    assert decisions[0].state == DecisionState.MATCHED


# 6. Missing timestamp (ts_invalid) -> Deterministic ABSTAIN
def test_missing_timestamp_abstains(base_cfg):
    t_now = datetime.now(timezone.utc).timestamp()
    invalid_ts_visual = VisualTransferEvent(
        v_id="V-bad-ts-1",
        provenance=Provenance.VIDEO_CV,
        session_id="session-ts-err",
        camera_id="cam0",
        store_zone="aisle04",
        track_id=6,
        t_pick=t_now - 10.0,
        t_bag=t_now - 6.0,
        t_ref=t_now - 6.0,
        t_ingest=t_now - 5.5,
        cls_votes={"bottle": 1.0},
        det_conf_median=0.88,
        track_continuity=0.92,
        gap_max_s=0.1,
        n_persons_max=0,
        luma_mean=140.0,
        blur_var_min=200.0,
        n_frames=30,
        quality_flags=[ReasonCode.TS_INVALID],
        source_ref={"clip": "clip_bad_ts"},
    )

    decisions = run([invalid_ts_visual], [], base_cfg)
    assert len(decisions) == 1
    assert decisions[0].state == DecisionState.ABSTAIN
    assert decisions[0].rule_id == "R01"


# 7. Missing product info (missing SKU not in skumap) -> Dropped term, NOT mismatch
def test_missing_product_not_treated_as_mismatch(base_cfg):
    t_now = datetime.now(timezone.utc).timestamp()
    visual = VisualTransferEvent(
        v_id="V-unlisted-1",
        provenance=Provenance.VIDEO_CV,
        session_id="session-unlisted",
        camera_id="cam0",
        store_zone="aisle04",
        track_id=7,
        t_pick=t_now - 8.0,
        t_bag=t_now - 5.0,
        t_ref=t_now - 5.0,
        t_ingest=t_now - 4.8,
        cls_votes={"bottle": 1.0},
        det_conf_median=0.88,
        track_continuity=0.92,
        gap_max_s=0.1,
        n_persons_max=0,
        luma_mean=140.0,
        blur_var_min=200.0,
        n_frames=30,
        quality_flags=[],
        source_ref={"clip": "clip_unlisted"},
    )
    # SKU not in sku_to_class
    scan = TransactionScanEvent(
        s_id="S-unlisted-1",
        provenance=Provenance.SYNTHETIC_GENERATED,
        session_id="session-unlisted",
        t_scan=t_now - 5.0,
        t_ingest=t_now - 4.5,
        sku="SKU-UNKNOWN-ITEM",
        qty=1,
        zone_hint="aisle04",
        txn_status=TxnStatus.COMMITTED,
        txn_line_id="L-unlisted",
        quality_flags=[],
        source_ref={"feed": "stream", "line": 1},
    )

    decisions = run([visual], [scan], base_cfg)
    assert len(decisions) == 1
    # Must match via temporal agreement T with S dropped and weights renormalized
    assert decisions[0].state == DecisionState.MATCHED
    assert decisions[0].rule_id == "R10"


# 8. Ambiguous candidates (|C1 - C2| < delta_amb) -> Deterministic ABSTAIN
def test_ambiguous_candidates_abstain(base_cfg):
    t_now = datetime.now(timezone.utc).timestamp()
    visual = VisualTransferEvent(
        v_id="V-amb-1",
        provenance=Provenance.VIDEO_CV,
        session_id="session-amb",
        camera_id="cam0",
        store_zone="aisle04",
        track_id=8,
        t_pick=t_now - 10.0,
        t_bag=t_now - 6.0,
        t_ref=t_now - 6.0,
        t_ingest=t_now - 5.5,
        cls_votes={"bottle": 1.0},
        det_conf_median=0.88,
        track_continuity=0.92,
        gap_max_s=0.1,
        n_persons_max=0,
        luma_mean=140.0,
        blur_var_min=200.0,
        n_frames=30,
        quality_flags=[],
        source_ref={"clip": "clip_amb"},
    )
    # Two identical scans at the exact same second
    scan1 = TransactionScanEvent(
        s_id="S-amb-1",
        provenance=Provenance.SYNTHETIC_GENERATED,
        session_id="session-amb",
        t_scan=t_now - 5.0,
        t_ingest=t_now - 4.5,
        sku="SKU-WATER",
        qty=1,
        zone_hint="aisle04",
        txn_status=TxnStatus.COMMITTED,
        txn_line_id="L-amb-1",
        quality_flags=[],
        source_ref={"feed": "stream", "line": 1},
    )
    scan2 = TransactionScanEvent(
        s_id="S-amb-2",
        provenance=Provenance.SYNTHETIC_GENERATED,
        session_id="session-amb",
        t_scan=t_now - 5.0,
        t_ingest=t_now - 4.5,
        sku="SKU-WATER",
        qty=1,
        zone_hint="aisle04",
        txn_status=TxnStatus.COMMITTED,
        txn_line_id="L-amb-2",
        quality_flags=[],
        source_ref={"feed": "stream", "line": 2},
    )

    decisions = run([visual], [scan1, scan2], base_cfg)
    # Equal rival costs -> margin = 0 < delta_amb -> R11 ABSTAIN
    assert decisions[0].state == DecisionState.ABSTAIN
    assert decisions[0].rule_id == "R11"


# 9. Class conflict (R12 / R13) -> Barcode swap detection
def test_class_conflict_triggers_review_or_abstain(base_cfg):
    t_now = datetime.now(timezone.utc).timestamp()
    visual = VisualTransferEvent(
        v_id="V-swap-1",
        provenance=Provenance.VIDEO_CV,
        session_id="session-swap",
        camera_id="cam0",
        store_zone="aisle04",
        track_id=9,
        t_pick=t_now - 8.0,
        t_bag=t_now - 5.0,
        t_ref=t_now - 5.0,
        t_ingest=t_now - 4.5,
        cls_votes={"bottle": 1.0},  # Confident optical detection of bottle
        det_conf_median=0.92,
        track_continuity=0.95,
        gap_max_s=0.1,
        n_persons_max=0,
        luma_mean=140.0,
        blur_var_min=200.0,
        n_frames=30,
        quality_flags=[],
        source_ref={"clip": "clip_swap"},
    )
    # Scan is steak, not bottle -> S = 1.0 (conflict)
    scan = TransactionScanEvent(
        s_id="S-swap-1",
        provenance=Provenance.SYNTHETIC_GENERATED,
        session_id="session-swap",
        t_scan=t_now - 5.0,
        t_ingest=t_now + 20.0,  # Feed watermark past grace period (t_ref + 20s)
        sku="SKU-STEAK",
        qty=1,
        zone_hint="aisle04",
        txn_status=TxnStatus.COMMITTED,
        txn_line_id="L-swap",
        quality_flags=[],
        source_ref={"feed": "stream", "line": 1},
    )

    decisions = run([visual], [scan], base_cfg)
    assert len(decisions) >= 1
    # When optical quality passes, class conflict triggers R12 REVIEW
    assert decisions[0].state == DecisionState.REVIEW
    assert decisions[0].rule_id == "R12"


# 10. Orphan scan (R40 INFO)
def test_orphan_scan_info(base_cfg):
    t_now = datetime.now(timezone.utc).timestamp()
    orphan_scan = TransactionScanEvent(
        s_id="S-orphan-1",
        provenance=Provenance.SYNTHETIC_GENERATED,
        session_id="session-orphan",
        t_scan=t_now - 5.0,
        t_ingest=t_now - 4.5,
        sku="SKU-WATER",
        qty=1,
        zone_hint="aisle04",
        txn_status=TxnStatus.COMMITTED,
        txn_line_id="L-orphan",
        quality_flags=[],
        source_ref={"feed": "stream", "line": 1},
    )

    decisions = run([], [orphan_scan], base_cfg)
    assert len(decisions) == 1
    assert decisions[0].state == DecisionState.INFO
    assert decisions[0].rule_id == "R40"


# 11. Baseline comparison test
def test_baseline_comparison(base_cfg):
    t_now = datetime.now(timezone.utc).timestamp()
    visual = VisualTransferEvent(
        v_id="V-base-1",
        provenance=Provenance.VIDEO_CV,
        session_id="session-base",
        camera_id="cam0",
        store_zone="aisle04",
        track_id=10,
        t_pick=t_now - 8.0,
        t_bag=t_now - 5.0,
        t_ref=t_now - 5.0,
        t_ingest=t_now - 4.5,
        cls_votes={"bottle": 1.0},
        det_conf_median=0.90,
        track_continuity=0.95,
        gap_max_s=0.1,
        n_persons_max=0,
        luma_mean=140.0,
        blur_var_min=200.0,
        n_frames=30,
        quality_flags=[],
        source_ref={"clip": "clip_base"},
    )
    scan = TransactionScanEvent(
        s_id="S-base-1",
        provenance=Provenance.SYNTHETIC_GENERATED,
        session_id="session-base",
        t_scan=t_now - 4.5,
        t_ingest=t_now - 4.0,
        sku="SKU-WATER",
        qty=1,
        zone_hint="aisle04",
        txn_status=TxnStatus.COMMITTED,
        txn_line_id="L-base",
        quality_flags=[],
        source_ref={"feed": "stream", "line": 1},
    )

    tc_decs = run([visual], [scan], base_cfg)
    base_decs = run_baseline([visual], [scan], base_cfg)

    assert tc_decs[0].state == DecisionState.MATCHED
    assert base_decs[0].state == DecisionState.MATCHED


# 12. Wilson score CI and zero-failure upper bound test
def test_wilson_ci_and_upper_bound():
    # 0 failures out of 4 samples -> UB = 1 - 0.05^(1/4) ≈ 52.7%
    ub_4 = upper_bound_zero_failures(4)
    assert 0.52 < ub_4 < 0.53

    # Wilson CI on 10 successes out of 10 samples
    ci_low, ci_high = wilson_ci(1.0, 10)
    assert ci_low > 0.65
    assert ci_high == 1.0


# 13. API Endpoints Test (TestClient)
def test_api_endpoints():
    client = TestClient(app)

    # Test /api/v1/health
    res_health = client.get("/api/v1/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "healthy"

    # Test /api/status
    res_status = client.get("/api/status")
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert "optical_cameras" in status_data
    assert status_data["optical_cameras"]["total"] == 1  # honest single-zone

    # Test /api/scenarios
    res_scenarios = client.get("/api/scenarios")
    assert res_scenarios.status_code == 200
    assert len(res_scenarios.json()) >= 4

    # Test /api/run for S03
    res_run = client.post("/api/run", json={"scenario": "S03"})
    assert res_run.status_code == 200
    run_data = res_run.json()
    assert run_data["scenario"] == "S03"
    assert len(run_data["decisions"]) == 2
    assert all(d["state"] == "MATCHED" for d in run_data["decisions"])

    # Test /api/evaluation
    res_eval = client.get("/api/evaluation")
    assert res_eval.status_code == 200
    eval_data = res_eval.json()
    assert "sla_matrix" in eval_data
    assert "UNSUPPORTED" in eval_data["metrics"]["false_intervention_rate"]["claim_status"]
