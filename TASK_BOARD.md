# TraceCart — Task Board

Clock reference: plan written **Thu 15 Oct 2026, 23:40 IST**. Deadline **Sun 18 Oct, 12:00 IST** (60 h 20 min). Submission target **Sun 10:00**.

**Owners (assumed team of 3 — merge if fewer):** **V** = vision/footage · **E** = engine/evaluation · **U** = UI/docs/QA + annotation. `ALL` = everyone.
**Priority:** P0 must ship · P1 improves judging · P2 cut first. **Effort** = focused hours for one person.
**Gates** (go/no-go): G0 Thu 01:15 · G1 Fri 12:30 · G2 Fri 18:30 · G3 Fri 23:30 · G4 Sat 18:00.

---

## M0 — Kickoff · Thu 23:40 → Fri 01:15

| ID | Task | Inputs | Creates later | Done when / Verify | Effort | Pri | Deps | Owner |
|---|---|---|---|---|---|---|---|---|
| T-001 | Read official portal/email rules: repo visibility, README, licence, library limits, post-cutoff commits, judging criteria. Write findings in `docs/DECISION_LOG.md` (D00) | portal, email | — | Written list of verified rules + unknowns | 0.3 | P0 | — | U |
| T-002 | Measure real hardware: OS, CPU, RAM, GPU, Python; `pip download ultralytics --no-deps` and fetch YOLO nano weights to test network | laptops | `docs/ENV.md` | Table of machines; weights file downloads **or** blocker noted | 0.4 | P0 | — | V |
| T-003 | `git init`, commit docs/, `.gitignore`, MIT licence unless rules say otherwise, push to a (private for now) remote | T-001 | repo skeleton | Remote exists, all members can push | 0.3 | P0 | — | E |
| T-004 | Freeze **schema v0.1**: `schema.py` models + reason-code enum + `configs/*.yaml` stubs | ARCHITECTURE §4 | `src/tracecart/schema.py`, `configs/` | `pytest tests/test_schema.py` passes (valid/invalid samples) | 0.8 | P0 | T-003 | E |
| T-005 | Shot list + props + scene checklist (see T-010) printed/written; optional **3 smoke clips tonight** (≤ 20 min) | MASTER_PLAN §5 | `data/manifests/shotlist.csv` | Props on a table; shot list agreed | 0.4 | P0 | — | U |
| **G0** | **01:15 checkpoint:** weights downloadable? Python OK? If no install path → choose fallback C front end and say so in DECISION_LOG | | | Decision recorded | | | | ALL |

---

## M1 — Footage · Fri 08:00 → 10:30

| ID | Task | Inputs | Creates | Done when / Verify | Effort | Pri | Deps | Owner |
|---|---|---|---|---|---|---|---|---|
| T-010 | Record clips: fixed phone (1080p/30, landscape, tripod or stacked books), one table as shelf (`Z_PICK`) + bag (`Z_BAG`), COCO-class props (bottle, cup, apple/banana/orange, book). Per `shotlist.csv`: S01×6, S02×3, S03×2, S08×2, S09×2, S10×2, S14×1, N01×2, B01×1 (≈ 21 clips, 10–25 s). Log `scanned_truth` **before** each take; verbal clap + clip-start wall-clock noted | T-005 | raw clips | ≥ 18 clips playable, names `clipNN_Sxx.mp4`, `clips.csv` filled | 2.0 | P0 | T-005 | V+U |
| T-011 | Re-encode to ≈ 960×540 (`ffmpeg … -crf 28`), copy into `data/clips/`; check total size (< ~50 MB) | T-010 | `data/clips/*` | Each clip plays; size noted | 0.3 | P0 | T-010 | U |
| T-012 | Assign **dev/test split by clip** and write `splits.yaml` (≈ 60/40, stratify by scenario) — **before looking at any output** | T-011 | `data/splits.yaml` | File committed | 0.2 | P0 | T-011 | E |

Fallback: < 12 usable clips by 10:30 → use a licence-clear public clip for pipeline testing *only if its licence is verified*; mark it clearly; reduce the test split accordingly (metrics become UNSUPPORTED, not hidden).

---

## M2 — Vision + engine core (parallel) · Fri 10:30 → 14:00

| ID | Task | Inputs | Creates | Done when / Verify | Effort | Pri | Deps | Owner |
|---|---|---|---|---|---|---|---|---|
| T-020 | Install vision extras on the primary machine; run YOLO nano on one clip, print detections | T-002, T-011 | `requirements-vision.txt` | Boxes printed for ≥ 1 clip; CPU fps noted | 0.5 | P0 | T-011 | V |
| T-021 | Zone config + **debug overlay** (draw `Z_PICK`, `Z_BAG` on a frame) | T-011 | `vision/zones.py`, `configs/zones.yaml`, `render.py` | PNG with polygons correct on 3 clips | 0.7 | P0 | T-011 | V |
| T-022 | Detect+track every clip at 10 fps → cache JSONL (boxes, class, conf, track id, frame, t) | T-020, T-021 | `vision/detect_track.py`, `data/cache/obs/*` | Cache exists for all clips; cache file hash logged | 1.2 | P0 | T-020, T-021 | V |
| T-023 | Transfer extraction + quality metrics from cache (pure Python, unit-tested on synthetic tracks) | T-022 | `vision/events.py`, `quality.py` | `tests/test_events.py` passes; events printed for 3 clips | 1.5 | P0 | T-022 (tests can start on T-004) | V |
| T-024 | Annotation: `t_pick`, `t_bag`, prop, adequacy, cause, for every clip (independent; no system output); double-label 5 clips | T-011 | `data/manifests/annotations/*.csv` | All clips annotated; agreement on 5 clips computed | 2.0 | P0 | T-011 | U |
| T-025 | `timeutil.py` + `ingest.py`: parse, align, validate; malformed → flags | T-004 | `timeutil.py`, `ingest.py` | `tests/test_time.py`, `test_ingest.py` pass (bad/naive/null/dup) | 1.2 | P0 | T-004 | E |
| T-026 | Scan feed generator (recipes in ARCHITECTURE §6, seeds) | T-024 (can stub with manual GT) | `feeds/generate.py`, `data/feeds/*` | Feeds exist for every clip × recipe; provenance = `synthetic_generated` | 1.2 | P0 | T-004 | E |
| **G1** | **12:30 — detector go/no-go:** on dev clips, events within ±1 s of annotated transfers ≥ **60%** (use T-024 partial annotations). Else: try small model / imgsz 960 / lower conf (≤ 45 min), then **switch to fallback C** (background-subtraction transfers; same schema) | | | Result written in DECISION_LOG D03 | | | | V |

---

## M3 — Association + policy · Fri 15:00 → 19:00

| ID | Task | Inputs | Creates | Done when / Verify | Effort | Pri | Deps | Owner |
|---|---|---|---|---|---|---|---|---|
| T-030 | Gating + cost terms T/Z/S/F + missing-term renormalisation | T-004, T-025 | `gate.py`, `cost.py` | `test_cost.py` boundary cases | 1.0 | P0 | T-025 | E |
| T-031 | Assignment (Hungarian), ambiguity margin, near-miss, deterministic ties | T-030 | `assign.py` | `test_assign.py`: 3v/2s, equal cost, qty-2, determinism | 1.2 | P0 | T-030 | E |
| T-032 | Evidence-quality gate + feed watermark | T-023, T-025 | `quality_gate.py` | `test_policy.py` quality cases | 0.8 | P0 | T-023 | E |
| T-033 | Decision policy R01–R40, late-event revision, versioned decisions | T-031, T-032 | `policy.py`, `pipeline.py` | One test per rule; REVIEW→MATCHED revision test | 1.5 | P0 | T-031, T-032 | E |
| T-034 | Baseline `timestamp_only` (W=5, W=10) | T-025 | `baseline.py` | `test_baseline.py` | 0.5 | P1 | T-025 | E |
| T-035 | Evidence packet JSON writer (Mechanism D minimal) | T-033 | `packets.py` | Packet for every decision; schema-validated | 0.8 | P0 | T-033 | E |
| T-036 | Visual-front-end validation vs annotations (dev): recall/precision/time error | T-023, T-024 | `eval/metrics.py` (front-end part) | Table in `runs/dev-*/frontend.md` | 1.0 | P0 | T-023, T-024 | V |
| **G2** | **18:30:** 3-state output on ≥ 5 scenarios, both from real-clip events | | | Screenshot/log saved | | | | ALL |

---

## M4 — End-to-end path · Fri 20:00 → 23:30

| ID | Task | Inputs | Creates | Done when / Verify | Effort | Pri | Deps | Owner |
|---|---|---|---|---|---|---|---|---|
| T-040 | `tracecart.run` CLI + `Makefile` (`demo`, `test`, `eval-dev`, `vision`) | T-033, T-035 | `run.py`, `Makefile` | `make demo` produces `runs/…/decisions.jsonl` from cache | 1.0 | P0 | T-033 | E |
| T-041 | Evaluator: all §4 metrics with denominators + Wilson/UB; target-vs-measured template | T-024, T-040 | `eval/metrics.py`, `report.py` | Hand-computed toy test passes; dev report generated | 2.0 | P0 | T-040 | E |
| T-042 | Dev tuning pass: λ, τ_match, W_gate, quality cut-offs **on dev only**; log every change | T-041 | `configs/policy.yaml` | Change log in DECISION_LOG | 1.0 | P0 | T-041 | E |
| T-043 | Hero scenarios S02/S03/S08 verified by eye vs overlay render | T-040, T-021 | `vision/render.py` overlays | 3 overlay mp4/gifs | 1.0 | P0 | T-040 | V |
| T-044 | README v0 with install steps for core and vision tiers | T-040 | `README.md` | A teammate can run `make demo` from the README | 0.7 | P0 | T-040 | U |
| **G3** | **23:30:** e2e `make demo` works on S02/S03/S08 on cached data. If not → **no new features Saturday until fixed** | | | | | | | ALL |

---

## M5 — Console + packets · Sat 08:00 → 12:30

| ID | Task | Inputs | Creates | Done when / Verify | Effort | Pri | Deps | Owner |
|---|---|---|---|---|---|---|---|---|
| T-050 | Streamlit console: scenario picker, overlay video, decision cards (state, rule, reasons, action), candidate table with T/Z/S/F, timeline of event times | T-035, T-043 | `app/streamlit_app.py` | `streamlit run app/streamlit_app.py` shows S02/S03/S08/S04; "cache replay" badge visible | 3.0 | P0 | T-035 | U |
| T-051 | Remaining scenario variants (S04–S07, S11–S13, S15) generated + tested | T-026, T-033 | `tests/test_scenarios.py` | Expected state per scenario asserted | 2.0 | P0 | T-033 | E |
| T-052 | Real-clip scenarios S09/S10/S14 inspected; reasons readable | T-040 | — | Each yields a justified state | 1.0 | P0 | T-040 | V |
| T-053 | Baseline wired into runner and scorer | T-034, T-041 | — | `make eval-dev` prints both systems | 0.7 | P1 | T-034, T-041 | E |
| T-054 | README v1: purpose, scope, limits, install, demo, tests, data provenance, licence (AGPL note) | T-044 | `README.md` | Reviewer checklist passes | 1.0 | P0 | T-044 | U |

---

## M6 — Freeze + evaluation · Sat 13:30 → 18:00

| ID | Task | Inputs | Creates | Done when / Verify | Effort | Pri | Deps | Owner |
|---|---|---|---|---|---|---|---|---|
| T-060 | **Pre-registration:** write `prereg_v1.yaml` (thresholds, targets, acceptance), update `splits.yaml`, commit, **tag `prereg-v1`** (~14:00) | T-042 | tag | Tag exists; hash printed | 0.3 | P0 | T-042 | E |
| T-061 | Run test split once → `runs/test-prereg-v1/` incl. baseline | T-060, T-053 | results | `metrics.json` with hash matching tag | 0.7 | P0 | T-060 | E |
| T-062 | Engine-only synthetic stress set E-SYN (≥ 3,000 clean events) | T-033 | `eval/ablate.py` | Reported with "synthetic" label and UB | 0.7 | P1 | T-033 | E |
| T-063 | Ablations A1, A2, A4 (A3 on dev only) | T-061 | `eval/ablate.py` | Table rows or `UNAVAILABLE` | 2.0 | P1 | T-061 | V+E |
| T-064 | `make report` → `results.md` in the target-vs-measured template; limitations section | T-061 | `docs/RESULTS.md` | All statuses filled, incl. UNSUPPORTED | 1.0 | P0 | T-061 | U |
| **G4** | **18:00 — honest results table exists.** If not: drop T-063/T-062; report what exists | | | | | | | ALL |

---

## M7 — Polish + clean-clone test · Sat 19:00 → 23:00 (feature freeze 20:30, code freeze 23:00)

| ID | Task | Pri | Deps | Verify | Effort | Owner |
|---|---|---|---|---|---|---|
| T-070 | Evidence thumbnails (pick/bag frames with boxes) in packets and console | P1 | T-050 | Visible in UI for S02/S03 | 1.5 | U |
| T-071 | Explanatory event graph from real packets (Graphviz) | P1 | T-035, T-050 | Graph edges equal packet candidates | 1.0 | U |
| T-072 | Demo rehearsal ×2 with timing; record backup screen capture | P0 | T-050 | 5-min run-through; backup video saved | 1.0 | ALL |
| T-073 | **Fresh-clone test** on a second machine/clean venv: core install, `make test`, `make demo` | P0 | T-054 | Passes; fixes committed | 1.0 | U |
| T-074 | Docs reconciliation: README, RESULTS, DECISION_LOG reflect what exists (remove claims for anything not built) | P0 | T-064 | Claim-by-claim check against code | 1.0 | ALL |
| T-075 | Pitch (README summary + 1-page technical report) | P1 | T-064 | Reads as factual | 1.0 | U |
| P2 | SQLite, human-resolution workflow, static HTML export, extra latency profiling | P2 | — | **Only if everything above is green** | — | — |

---

## M8–M9 — Verification and submission · Sun 07:00 → 10:00 (hard stop 11:00; deadline 12:00)

| ID | Task | Pri | Verify | Effort | Owner |
|---|---|---|---|---|---|
| T-080 | Fresh clone from remote URL, run README top to bottom, `make test`, `make demo` | P0 | All green, times noted | 0.7 | U+E |
| T-081 | Repo hygiene: no secrets, no oversize files, licence, `.gitignore`, repo visibility per rules (T-001), clip consent confirmed | P0 | Checklist | 0.4 | U |
| T-082 | Tag `v0.1-submission`; push; confirm remote HEAD = tag | P0 | `git ls-remote` | 0.2 | E |
| T-083 | Submit on portal; screenshot confirmation; confirm link opens logged-out | P0 | Screenshot saved | 0.3 | ALL |
| T-084 | Buffer. No code changes unless the fresh-clone test fails | — | — | 1.5 | — |

---

## Cut ladder (apply in order when time is short)
1. T-071 graph → 2. T-070 thumbnails → 3. A4 occlusion → 4. A1 tracker ablation → 5. E-SYN → 6. A3 → 7. Streamlit styling → 8. baseline (keep if at all possible) → never cut: schema, real-video events, association, 3 states, tests, README, honest results.

## Effort check
Sum of P0 rows ≈ 38 h across 3 people ≈ 13 h each against ≈ 22–26 h available each → ~45% slack for integration bugs, installs, annotation overruns. With 2 people, slack ≈ 15% — cut P1 earlier.
