"""Pydantic v2 schemas and enums for TraceCart events and decisions.

All enums and models mirror ARCHITECTURE.md §4 and §6.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, ConfigDict, computed_field, field_validator, model_validator


class Provenance(str, Enum):
    """Origin of an event."""
    VIDEO_CV = "video_cv"
    SYNTHETIC_GENERATED = "synthetic_generated"
    SYNTHETIC_VISUAL = "synthetic_visual"
    GROUND_TRUTH = "ground_truth"  # never fed to engine
    MANUAL_ANNOTATION = "manual_annotation"


class TxnStatus(str, Enum):
    """Transaction status from retailer feed."""
    COMMITTED = "committed"
    PENDING = "pending"
    VOIDED = "voided"


class ReasonCode(str, Enum):
    """Machine-readable reasons attached to a decision."""
    # Timestamps
    TS_INVALID = "ts_invalid"
    TS_NAIVE = "ts_naive"
    # Track/visual quality
    SHORT_TRACK = "short_track"
    MULTI_PERSON = "multi_person"
    LOW_LIGHT = "low_light"
    BLURRY = "blurry"
    ID_SWITCH_SUSPECT = "id_switch_suspect"
    FPS_UNRELIABLE = "fps_unreliable"
    # Scan feed
    SKU_MISSING = "sku_missing"
    QTY_INVALID = "qty_invalid"
    DUPLICATE_OF = "duplicate_of:"
    POSSIBLE_DUPLICATE = "possible_duplicate"
    VOIDED = "voided"
    # Matching / policy
    NO_CANDIDATE_IN_WINDOW = "no_candidate_in_window"
    EVIDENCE_QUALITY_OK = "evidence_quality_ok"
    FEED_HEALTHY = "feed_healthy"
    LATE_EVENT_REVISION = "late_event_revision"


class EvidenceQuality(BaseModel):
    """Bundle of per-component quality flags (true means component passed)."""
    model_config = ConfigDict(populate_by_name=True)

    det_conf: float = Field(..., ge=0.0, le=1.0)
    continuity: float = Field(..., ge=0.0, le=1.0)
    gap_max_s: float = Field(..., ge=0.0)
    n_persons: int = Field(..., ge=0)
    frame_quality: str = Field(...)  # "ok" or reason
    pass_: bool = Field(alias="pass")
    failed: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _set_failed(self) -> "EvidenceQuality":
        if not self.pass_:
            # caller should set failed; this just ensures list exists
            return self
        self.failed = []
        return self


class VisualTransferEvent(BaseModel):
    """Event produced by the vision front end (V1–V3)."""
    v_id: str
    provenance: Provenance
    session_id: str
    camera_id: str
    zone_path: List[str] = Field(default_factory=lambda: ["Z_PICK", "Z_BAG"])
    store_zone: str
    track_id: int
    t_pick: float
    t_bag: float
    t_ref: float  # = t_bag by convention
    t_ingest: float
    cls_votes: Dict[str, float] = Field(default_factory=dict)  # sums to 1
    det_conf_median: float = Field(..., ge=0.0, le=1.0)
    track_continuity: float = Field(..., ge=0.0, le=1.0)
    gap_max_s: float = Field(..., ge=0.0)
    n_persons_max: int = Field(..., ge=0)
    luma_mean: float
    blur_var_min: float
    n_frames: int
    quality_flags: List[ReasonCode] = Field(default_factory=list)
    source_ref: Dict[str, Union[str, int]]  # {clip, frame_start, frame_end, cache_file}

    @computed_field  # type: ignore[misc]
    @property
    def handling_interval(self) -> tuple[float, float]:
        """(t_pick, t_bag)"""
        return (self.t_pick, self.t_bag)

    @field_validator("cls_votes")
    @classmethod
    def _sum_to_one(cls, v: Dict[str, float]) -> Dict[str, float]:
        if abs(sum(v.values()) - 1.0) > 1e-6 and v:
            raise ValueError("cls_votes must sum to 1.0")
        return v

    @field_validator("t_ref")
    @classmethod
    def _t_ref_eq_t_bag(cls, v: float, info) -> float:
        if hasattr(info, "data") and "t_bag" in info.data and abs(v - info.data["t_bag"]) > 1e-9:
            raise ValueError("t_ref must equal t_bag")
        return v


class TransactionScanEvent(BaseModel):
    """One scan line from the transaction feed."""
    s_id: str
    provenance: Provenance
    session_id: str
    t_scan: Optional[float] = None  # None if malformed/naive
    t_ingest: float
    sku: Optional[str] = None
    qty: Optional[int] = None
    zone_hint: Optional[str] = None
    txn_status: TxnStatus
    txn_line_id: Optional[str] = None
    source_seq: Optional[int] = None
    quality_flags: List[ReasonCode] = Field(default_factory=list)
    source_ref: Dict[str, Union[str, int]]  # {feed file + line}

    @field_validator("qty")
    @classmethod
    def _positive_qty(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v <= 0:
            raise ValueError("qty must be positive when present")
        return v


class FeedHeartbeat(BaseModel):
    """Proves the transaction feed was alive; gives watermark."""
    feed_id: str
    session_id: str
    t_ingest: float


class CandidateLink(BaseModel):
    """Edge in the association graph (one visual event ↔ one scan slot)."""
    v_id: str
    s_id: str
    slot: int  # 1..qty for that scan line
    gate_pass: bool
    gate_reason: Optional[ReasonCode] = None
    T: float  # temporal term [0,1]
    Z: float  # zone term [0,1] or unavailable (see cost.py)
    S: float  # product term [0,1] or unavailable
    F: float  # flow/quantity term [0,1]
    available_terms: List[str] = Field(default_factory=list)  # subset of {"T","Z","S","F"}
    cost: float  # normalised C(i,j) ∈ [0,1]
    selected: bool
    margin: Optional[float] = None  # for ambiguity detection


class DecisionState(str, Enum):
    MATCHED = "MATCHED"
    REVIEW = "REVIEW"
    ABSTAIN = "ABSTAIN"
    INFO = "INFO"  # orphan scans only


class Decision(BaseModel):
    """Evidence packet emitted by the policy (P1)."""
    decision_id: str
    version: int = 1
    supersedes: Optional[str] = None
    unit: Dict[str, str]  # {"type": "visual_transfer", "v_id": "..."}
    state: DecisionState
    rule_id: str
    reason_codes: List[ReasonCode] = Field(default_factory=list)
    visual: Dict[str, Any]  # summary of VisualTransferEvent + media refs
    candidates: List[CandidateLink] = Field(default_factory=list)
    association: Dict[str, Optional[Union[str, float]]]  # selected_s_id, best_cost, margin
    evidence_quality: Optional[EvidenceQuality] = None
    timing: Dict[str, Optional[Union[float, Dict[str, float]]]]  # t_ref, grace_s, watermark, time_diffs_s
    warnings: List[str] = Field(default_factory=list)
    recommended_action: str
    config_hash: str
    code_commit: str
    human_resolution: Optional[Dict] = None

    @model_validator(mode="after")
    def _set_defaults(self) -> "Decision":
        if not self.recommended_action:
            action_map = {
                DecisionState.MATCHED: "No action.",
                DecisionState.REVIEW: (
                    "Request a low-friction rescan/verification per store policy. "
                    "This is a verification request, not an accusation."
                ),
                DecisionState.ABSTAIN: (
                    "No alert. Insufficient/ambiguous evidence: <reasons>. "
                    "Optional alternative verification only if store policy allows."
                ),
                DecisionState.INFO: "No intervention (orphan scan).",
            }
            self.recommended_action = action_map.get(self.state, "")
        return self