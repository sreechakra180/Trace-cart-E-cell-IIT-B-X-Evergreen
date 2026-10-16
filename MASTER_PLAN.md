# TraceCart — Master Plan

**Team Samanvaya · E-Cell IIT Bombay × Everseen CV AI Hackathon · Problem Statement 2 (Mobile Scan & Go)**
Plan written: Thu 15 Oct 2026, 23:40 IST. Repository deadline: **Sun 18 Oct 2026, 12:00 IST**.
Status of the build: **zero**. Nothing in this plan exists yet; every component below is a *proposal*.

Companion docs: `ARCHITECTURE.md` · `EVALUATION_PLAN.md` · `TASK_BOARD.md` · `DEMO_PLAN.md` · `RISK_REGISTER.md` · `DECISION_LOG.md`

---

## 0. Verified facts vs assumptions

| Item | Status | Source / note |
|---|---|---|
| Repo cutoff Sun 18 Oct 2026 12:00 IST; finale 18–20 Oct | **User-provided** (selection email) | Not verified on the official site |
| Time remaining from 15 Oct 23:40 IST | **Computed**: 60 h 20 min | System clock, Asia/Kolkata |
| Official rules (repo visibility, licence, allowed libraries, judging criteria, team size, what may change after cutoff) | **NOT VERIFIED** | One web search found nothing relevant. **Task T-001: read the portal/email tonight.** |
| Team size | **Assumed 3** (roles V/E/U in the Task Board; merge roles if fewer) | Please correct |
| Your hardware (CPU/GPU/RAM/OS) | **UNKNOWN** | The container I inspected (1 vCPU, 3.9 GB RAM, no GPU, Python 3.12, no Git repo) is *not* your machine. T-002 measures yours. Plan assumes **CPU-only laptop**. |
| Workspace | Clean: only the deck PDF exists; no repo, no code, no footage | Inspected |
| Network | PyPI and GitHub reachable **from my container**; unknown from yours | Weights/pip are a live blocker until T-002 passes |
| Deck stats on slide 2 (ECR report) | **Not verified by me**, cited as context only | Don't repeat them as facts in the pitch without checking the source |
| Anything about detector accuracy on our items | **Unknown** until Fri 12:30 gate G1 | Plan contains a fallback |

The brief was cut off at "Include an early …". I read it as "early go/no-go checkpoints" and built them in (gates G0–G4). If more followed, send it.

---

## 1. What the deck commits to (and what is only conceptual)

| Deck item | Essential to the submitted proposition? | Plan treatment |
|---|---|---|
| p3 problem (A unmatched, B delayed, C conflicting, D incomplete) + MVP boundary | **Essential** | Maps 1:1 to scenarios S02, S04, S12, S08/S09 |
| p4/p5 three outcomes + 3-items-2-scans scenario | **Essential** (demo centrepiece) | Scenario S03 is the hero demo |
| p6 six layers; "demo needs layers 1–4 + minimal decision rule" | Layers 1–5 essential; console = lightweight | FastAPI, PostgreSQL **dropped** (decision D07, D08) |
| p7 cost formula, zone-conditioned graph, uncertainty gating | **Essential but unproven**; deck itself says "value to be validated" | Implemented and tested against a baseline; graph only as an *explanatory view* |
| p8 privacy by design | Essential (constraint) | No faces, no identity; pseudonymous session id only |
| p9 targets + 5 ablations | Essential to the "honest metrics" promise | Reported in 4-column target-vs-measured format; two ablations dropped (D10) |
| p10 phases 0–5 | Conceptual; replaced by the deadline schedule below | |
| p11 commercial positioning | Conceptual | One slide/paragraph in README only |
| p12 commitments | **Binding on us**: working 3-state demo, testable cost formulation, pre-registered targets/ablations/honest table, deployable policy | Every deliverable below traces to one of these |

**Deck claims that would be embarrassing if a judge probes them**
- "Live three-product scenario": the footage is *recorded*. Say "recorded clip processed by the pipeline" unless the detector is truly run live.
- "Calibrated thresholds": with ~20 clips we can only *tune on a dev split and pre-register*. Say that.
- "False REVIEW < 1 per 1,000 scan events": **cannot be demonstrated** (see §7).
- "Learned risk score where labels permit": labels don't permit; dropped.

---

## 2. The problem-definition gap (what we can legitimately claim)

| Layer | What it can establish | What it cannot |
|---|---|---|
| **1. Camera observes** | Pixels of a hand/object moving through a fixed region | Which SKU; whether it was paid for; intent; anything occluded |
| **2. Detector + tracker infer** | COCO-class boxes (bottle, cup, apple, banana, orange, book…) with confidence; short tracklets with IDs that can break | SKU identity; reliable detection of hand-held/occluded items; shopper identity (we deliberately do not attempt it); quantity of identical items |
| **3. Transaction events establish** | *Synthetic here*: that a scan record with (session, sku, qty, time, status) exists | Anything about physical reality; in the demo, records are generated and labelled `synthetic_generated`, never "detections" |
| **4. Combination can conclude** | "A tracked item of class X completed a pickup-zone → bag-zone transfer at time t in session s; no compatible scan record exists by watermark t+G; visual quality passes gates" → *worth a verification request* | That anyone stole anything. "Unmatched" ≠ wrongdoing. |

### Event semantics the prototype supports (frozen in schema v0.1)

- **Visual transfer event (`V_TRANSFER`)** — a single tracked object of an *eligible* class whose track enters zone `Z_PICK`, later enters zone `Z_BAG`, lasts ≥ `min_track_frames`, and moves in that order. Reference time `t_ref` = entry time into `Z_BAG`; handling interval = `[t_pick, t_bag]`.
- **Product evidence = COCO class-vote distribution only.** SKU → class is a **configured map** for the staged props (e.g., `SKU-WATER → bottle`). This is "class consistency", not SKU recognition, and the docs/UI must say so.
- **Session link is contextual, not visual.** One clip = one pseudonymous session window from the manifest. We never identify a person. Multi-person frames raise an *ambiguity flag* (person-box count, not identity).
- **Quantity** is not observable per item; each track = 1 unit. Quantity is checked only at session level (`count_mismatch` flag) and through scan-line slot expansion.
- **Transaction scan event (`T_SCAN`)** — `(event_id, session_id, t_scan with tz, t_ingest, sku, qty, zone_hint?, txn_status, txn_line_id?)`.

---

## 3. Smallest competitive product

> Recorded real clips of a staged one-zone scene → real detector + ByteTrack → zone-transfer events (cached) → synthetic-but-labelled scan feed → gated min-cost association → evidence-quality gating → MATCHED / REVIEW / ABSTAIN → evidence-packet console → evaluation against annotated ground truth vs a timestamp-only baseline.

### Strategy comparison

| | **A. Engine-first, scripted events** | **B. Detector + tracker + zone events → engine** | **C. Class-agnostic motion/background-subtraction transfers → engine** |
|---|---|---|---|
| Idea | Reconcile hand-authored visual/scan events; no real video | Pretrained YOLO + ByteTrack; zone-ordered transfer events from real clips | OpenCV MOG2 blobs crossing zone ROIs; no weights, no classes |
| Time to e2e demo | Fastest (~hours) | Moderate; depends on install + detector recall | Fast |
| Genuine CV content | **None** — judges will call it a spreadsheet matcher | High, real | Medium; classic CV, no product evidence |
| Product-class evidence (S term) | Fake | Real but coarse (COCO) | Not available |
| Reliability under adversity | Perfectly reliable (it's scripted) | Detector misses hand-held items; ID switches | Lighting, hands and shadows all become "objects" |
| Install / data risk | None | Torch + weights download; AGPL licence note | OpenCV only |
| Event-level measurability | Trivial (and meaningless) | Good (annotated transfer times) | Good |
| Interrogation risk | **High** ("where's the vision?") | Medium (accuracy, licence) | Medium ("it's just motion") |

### Weighted decision matrix (scores 1–5, judgement not measurement)

| Criterion | Weight | A | B | C |
|---|---:|---:|---:|---:|
| Time to working e2e demo | 15 | 5 | 3 | 4 |
| Technical credibility | 10 | 3 | 4 | 3 |
| Genuine CV content | 15 | 1 | 5 | 3 |
| Originality of demonstrated function | 5 | 3 | 3 | 3 |
| Reliability under adverse tests | 10 | 5 | 3 | 3 |
| Dataset/model requirements (5 = least) | 8 | 5 | 3 | 5 |
| Install difficulty (5 = easiest) | 8 | 5 | 3 | 5 |
| Event-level measurability | 10 | 4 | 4 | 3 |
| Demo clarity | 8 | 3 | 5 | 4 |
| Low judge-interrogation risk | 8 | 2 | 4 | 3 |
| Extensibility | 3 | 3 | 4 | 2 |
| **Weighted total /100** | 100 | **70.8** | **75.4** | **70.4** |

**Honest reading.** The margin is small. If you drop the "genuine CV content" criterion, A wins (79.8 vs B 71.1) — B only wins because this is a *computer-vision* hackathon and a no-vision submission is the most likely way to lose. The matrix therefore does not say B is easy; it says B is the best bet *if* the detector works on our footage. That is exactly what gate G1 tests early.

**Primary: B**, scoped tightly (one zone, COCO-class props, cached observations).
**Fallback: C as the front end** (same event schema, same engine) if G1 fails or installs fail. The engine is always tested with A-style synthetic visual events too, so the engine work is never wasted.
No third prototype is built.

---

## 4. Differentiator: what we claim and what we don't

Everseen already sells checkout loss prevention. We do **not** claim novelty for missed-scan detection.

| Mechanism | Verdict | Minimum implementation |
|---|---|---|
| **A. Zone-conditioned event schema** | **Do (P0)** — it is the contract everything else depends on | Pydantic models, provenance field, quality flags, source refs |
| **B. Constrained association** | **Do (P0)** — gated min-cost assignment (Hungarian via SciPy) with explicit tie/ambiguity handling | 4 normalised cost terms, missing-term renormalisation, margin test |
| **C. Evidence-quality gating + abstention** | **Do (P0)** — the actual differentiator vs. a timestamp matcher | Rule table R01–R40, conservative `min()` over quality components |
| **D. Evidence packets** | **Do (P0 JSON, P1 thumbnails)** | Packet = decision + candidates + terms + rule id + warnings + thresholds hash |
| Event graph visual | **P1 only**, explanatory: rendered from *actual* candidate links of a run | Graphviz DOT in Streamlit |
| Learned risk score | **Dropped** (no labels) | — |

**Required differentiation test.** TraceCart vs. a timestamp-only nearest-scan baseline, same scenarios, same metrics, thresholds pre-registered, dev/test split. If TraceCart does not improve the operational trade-off on the *natural* clips (not just on cases we built to break the baseline), `EVALUATION_PLAN.md` says to report that and recommend the simpler system. No result is claimed in this plan.

---

## 5. Data strategy (summary; detail in `EVALUATION_PLAN.md`)

- **Real video (must be real):** ~20 staged clips, one fixed phone camera, one table-top "shelf" zone + one bag zone, props from COCO classes, teammates only (consent; no faces required in frame). ~60–75 min to shoot. Re-encode to ≈960×540 for the repo.
- **Synthetic (explicitly labelled `synthetic_generated`):** scan feeds with delay, duplicates, malformed timestamps, missing SKU, heartbeat gaps; generated *from annotated ground truth plus a documented noise model* with fixed seeds.
- **Annotation:** human annotators log true `t_pick`, `t_bag`, prop, and a rubric-based `evidence_adequate` label **before** looking at system output.
- **Visual and matching performance evaluated separately** (front-end event P/R vs annotations; engine association P/R given ground-truth visual events; end-to-end).
- **No SKU claims.** No training. No dataset downloads needed.
- **Fallback footage:** a licence-clear public clip if our recording fails — *team must verify its licence; not verified here.*

---

## 6. Technology choices (detail + alternatives in `DECISION_LOG.md`)

| Component | Decision | Why / simplest alternative / risk |
|---|---|---|
| Python 3.10–3.12 | Yes | Unknown local version → `requirements-core.txt` vs `requirements-vision.txt` split |
| OpenCV | Yes | Decode, zone drawing, quality metrics (blur/luma), overlay render. Low risk |
| Detector | **Ultralytics YOLO nano/small (COCO)** | Fast on CPU, one install. **AGPL-3.0** licence — acceptable for a public repo, record it. Alternative: YOLOX (Apache-2.0), more install friction |
| Tracker | **ByteTrack bundled with Ultralytics** | No separate install. Fallback: ~80-line IoU/centroid tracker |
| Assignment | SciPy `linear_sum_assignment` | Alternative: gated greedy; n ≤ ~10 per session so either works; Hungarian handles competition correctly |
| Schemas/validation | Pydantic v2 | Malformed data must become data-quality flags, not crashes |
| Config | YAML (PyYAML) | Comments for pre-registration; hashed into every output |
| Persistence | **JSONL/JSON run artefacts** | SQLite deferred to P2 — no need for DB to demonstrate anything |
| UI | **Streamlit** reading precomputed artefacts | Static HTML report as fallback. No FastAPI, no React, no PostgreSQL |
| Tests | pytest | Core install must run tests without torch |
| Not used | Cloud/paid APIs, LLMs, model training, microservices | No measured benefit for this scope |

**Reproducibility rule.** The repo ships (a) the clips, (b) the cached per-frame observations produced by the real detector, (c) the generated scan feeds, so `make demo` works with only the core install. `make vision` re-runs the real detector when torch/weights are available. Replay-from-cache is **labelled as replay** in the UI.

---

## 7. Evaluation honesty (headline points)

- All deck numbers are **targets**. We report four columns: *deck target · internal MVP acceptance · measured (value, N, 95% CI) · future production target (not claimed)*.
- **< 1 false REVIEW per 1,000 scan events cannot be established.** Zero failures in *n* clean events gives a 95% upper bound ≈ 3/*n*: n=300 → 1.0%, n=3,000 → 0.1%. Our real-clip clean set will be ~15–30 events → UB 10–20%. The metric will be printed as **UNSUPPORTED (N=…, UB=…)**, never "met".
- ≥ 95% abstention correctness with N≈20 low-evidence cases means ≤ 1 miss; Wilson CI for 19/20 is [0.76, 0.99]. Report the interval.
- Thresholds are frozen in a git-tagged config (`prereg-v1`) **before** the first test-split run.
- The engine-only synthetic stress set (thousands of clean events) is reported separately and labelled "engine-only, synthetic — says nothing about real-world false-REVIEW rate".

---

## 8. Roadmap (anchored to the clock — full detail in `TASK_BOARD.md`)

Time left: **60 h 20 min** from Thu 23:40 IST. Realistic focused time per person ≈ 22–26 h after sleep, meals, setup and integration.

| Milestone | Window (IST) | Deliverable | Gate |
|---|---|---|---|
| **M0** Kickoff | Thu 23:40–01:15 | Rules checked, hardware measured, repo + schema v0.1 + shot list ready; optional 3 smoke clips | **G0** (01:15): installs work on ≥1 machine, or fallback C chosen |
| Sleep | Thu 01:15–Fri 08:00 | | |
| **M1** Footage | Fri 08:00–10:30 | ≥ 18 usable clips + manifest | |
| **M2** Vision + engine core (parallel) | Fri 10:30–14:00 | Cached observations; schemas, ingestion, timestamp alignment, tests | **G1** (12:30): detector yields transfer events on ≥ 60% of annotated transfers, else fallback C |
| Break | Fri 14:00–15:00 | | |
| **M3** Association + policy | Fri 15:00–19:00 | Cost, assignment, R-rules, baseline, 20+ tests | **G2** (18:30): 3-state output on ≥ 5 scenarios |
| Dinner | Fri 19:00–20:00 | | |
| **M4** E2E path | Fri 20:00–23:30 | `make demo` end-to-end CLI; dev-split metrics | **G3** (23:30): e2e works on hero scenarios S02/S03/S08 |
| Sleep | Fri 23:45–Sat 07:45 | | |
| **M5** Console + packets | Sat 08:00–12:30 | Streamlit console, evidence packets, README v1 | |
| Break | Sat 12:30–13:30 | | |
| **M6** Freeze + evaluation | Sat 13:30–18:00 | `prereg-v1` tag at ~14:00; test run; baseline; ablations A1–A4 | **G4** (18:00): honest results table exists |
| Dinner | Sat 18:00–19:00 | | |
| **M7** Polish + clean-clone test | Sat 19:00–23:00 | P1 items only if G4 passed; docs/results update | **Feature freeze 20:30; code freeze 23:00** |
| Sleep | Sat 23:30–Sun 07:00 | | |
| **M8** Verification | Sun 07:00–09:00 | Fresh-clone install, README walk-through, tag `v0.1-submission` | |
| **M9** Submit | Sun 09:00–10:00 | Portal submission **target 10:00**, internal hard stop 11:00 | **90–120 min buffer** before 12:00 |

Cut order if behind: see §9 and `RISK_REGISTER.md`.

---

## 9. Priorities and cut order

- **P0 (must ship):** setup + split requirements files; schema; real video → events (cached); ingestion + timestamp alignment; association; 3-state policy; computed explanations; repeatable demo scenario; essential tests; accurate README; submission-ready repo.
- **P1 (if P0 is stable by Sat 14:00):** baseline comparison; ablations A1–A4; evidence thumbnails; explanatory graph; polished Streamlit view; results report.
- **P2 (cut first):** SQLite; human-resolution workflow; static HTML export; latency profiling beyond a single table; tracker-vs-no-tracker on all clips; extra zones/cameras; any "learned" component.

Cut triggers: G1 fail → fallback C; G2 slip > 3 h → drop graph + thumbnails; G3 slip → drop A3/A4 ablations; Sat 20:30 → freeze regardless.

---

## 10. Open items for the team (answer tonight)

1. Official rules: repo visibility (public vs shared), required README items, licence expectations, post-cutoff commits allowed?
2. Team size and who owns V / E / U.
3. Laptops: OS, RAM, CPU/GPU, Python version.
4. Do you have props (bottle, cup, apple/banana/orange, book), a bag, a table, and a phone tripod (or stacked books)?
5. Are all people in clips teammates who consent to the clips being public?
