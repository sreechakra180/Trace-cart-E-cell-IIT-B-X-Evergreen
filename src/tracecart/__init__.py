"""TraceCart — Mobile Scan & Go reconciliation engine.

Core package. The engine is a library + CLI + HTTP API; the UI is a separate
Antigravity (React/TS) application that consumes the API. This package never
depends on torch at import time in the core tier.
"""

from tracecart.schema import (
    Provenance,
    TxnStatus,
    ReasonCode,
    EvidenceQuality,
    VisualTransferEvent,
    TransactionScanEvent,
    FeedHeartbeat,
    CandidateLink,
    Decision,
    DecisionState,
)

__all__ = [
    "Provenance",
    "TxnStatus",
    "ReasonCode",
    "EvidenceQuality",
    "VisualTransferEvent",
    "TransactionScanEvent",
    "FeedHeartbeat",
    "CandidateLink",
    "Decision",
    "DecisionState",
]

__version__ = "0.1.0"
