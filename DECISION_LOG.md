# TraceCart — Decision Log

Format: **Decision · Date · Status** → why → alternatives rejected → evidence that would make us revisit.
All decisions are provisional as of Thu 15 Oct 2026, 23:40 IST; none has been tested.

---

**D00 · Official rules unverified · OPEN**
One search did not find the hackathon page. T-001 must verify repo visibility, README/licence expectations, library restrictions, post-cutoff commit policy. Revisit: any contradiction with this plan.

**D01 · Primary architecture B (detector + ByteTrack + zone events → engine), fallback C · Provisional**
Why: scores 75.4 vs 70.8 (A) and 70.4 (C); wins only because genuine CV content is weighted 15. Rejected: A as primary (no real vision; high judge-interrogation risk); three parallel prototypes (no time). Revisit: **G1 fails** (< 60% transfer recall) → C becomes primary.

**D02 · Real video, synthetic scans, always labelled · Decided**
Why: no real retailer feed exists; synthetic scans test association, delay, duplication, uncertainty. Rejected: pretending synthetic scans are real; scripted visual events as the main path. Revisit: organisers supply a real transaction feed or dataset.

**D03 · Detector family: Ultralytics YOLO nano/small (COCO) · Provisional**
Why: CPU-feasible, single install, ByteTrack included. Licence **AGPL-3.0** noted. Rejected: YOLOX (Apache-2.0; more install friction), RT-DETR/large models (CPU latency), training or fine-tuning (no labels, no time), open-vocabulary detectors (heavy, unproven). Revisit: G1 recall result; rules forbidding AGPL deps; install failure → try YOLOX-ONNX or fallback C.

**D04 · Evidence = COCO class votes via configured SKU→class map; no SKU recognition · Decided**
Why: only claim we can support. Rejected: any "SKU detection" language. Revisit: a SKU-level labelled dataset appears.

**D05 · Visual→session link is contextual (manifest), not by person identity · Decided**
Why: privacy-by-design; the deck forbids identity tracking. Person boxes used only for overlap/ambiguity count. Rejected: re-ID, face features. Revisit: never in MVP.

**D06 · Association: hard gating + normalised 4-term cost + Hungarian + margin test · Provisional**
Why: smallest method that handles competition between candidates and is explainable. Rejected: timestamp-greedy (that's the baseline); learned matcher (no labels); full probabilistic graph/CRF (unneeded complexity). Missing terms are dropped and weights renormalised (never treated as mismatch). Revisit: A3/A2 show no benefit from extra terms → simplify to T+gating.

**D07 · No FastAPI service · Decided**
Why: pipeline is a library + CLI + Streamlit reading artefacts; a service adds failure modes without a measured benefit. Deck listed it as a *candidate component*. Revisit: a second consumer needs HTTP access.

**D08 · JSON/JSONL artefacts, not PostgreSQL; SQLite deferred (P2) · Decided**
Why: artefacts are diff-able, hashable, judge-inspectable. Revisit: console needs queries across many runs.

**D09 · Streamlit console reading precomputed artefacts; static report is a fallback · Provisional**
Why: deck promises a console; pure-Python. Rejected: React/web stack. Revisit: Streamlit install issues in the fresh-clone test → static HTML.

**D10 · Ablations: keep A1–A4; drop "learned risk score" · Decided**
Why: no labels to train/evaluate a learned score; reporting `UNAVAILABLE` is more honest than a toy. Revisit: ≥ several hundred labelled decisions exist.

**D11 · Pre-registration by git tag + config hash; dev/test split by clip · Decided**
Why: deck promises it; protects against threshold-fitting. Revisit: if we change thresholds after test results, issue `prereg_v2` and say so.

**D12 · First-issued decision used for false-intervention metrics; later versions kept · Decided**
Why: late data must not hide false REVIEWs. Revisit: n/a.

**D13 · Orphan scans are INFO, not a fourth state · Decided**
Why: the deck specifies three outcomes; scans with no visual evidence are not the MVP's target discrepancy. Revisit: a pilot wants "scan without movement" analytics.

**D14 · Grace period G = 20 s, W_gate = 10 s, τ_match = 0.50, δ_amb = 0.10 (initial values) · Provisional**
Why: first guesses from Scan & Go handling intuition; no data. Tuned on dev only, then frozen. Revisit: dev results.

**D15 · Cached detector output is committed; demo defaults to replay (labelled) · Decided**
Why: guarantees a demo if torch/network fails. Risk: judges may think it is "not live" → badge says replay and `make vision` re-runs the detector. Revisit: n/a.

**D16 · Two-tier dependencies (`core` vs `vision`) · Decided**
Why: judges can run tests/demo without torch. Revisit: none.

**D17 · Deviations from the deck to disclose in README · Decided**
FastAPI and PostgreSQL not used; "live" scenarios are recorded clips (replay by default); thresholds are dev-tuned and pre-registered, not "calibrated"; learned risk score not built; false-REVIEW < 1/1000 not demonstrable.

**D18 · Team size assumed 3; roles V/E/U · Provisional**
Revisit: actual team size (with 2 members, cut P1 earlier; with 4, add a dedicated annotator/QA).
