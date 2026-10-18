# TraceCart — Evaluation Plan

No result exists yet. Every number below is a **target, an acceptance criterion, or a statistical bound**, not a measurement.

---

## 1. Four kinds of numbers (never mix them)

| Column | Meaning | Where it lives |
|---|---|---|
| **1. Deck target** | Submitted on slide 9 | `configs/prereg_v1.yaml` → `deck_targets` |
| **2. Internal MVP acceptance** | What we decide is "good enough to submit" | `prereg_v1.yaml` → `acceptance` |
| **3. Measured** | Value, N, denominator, 95% CI, config hash, commit | `runs/<id>/metrics.json` |
| **4. Future pilot/production target** | Aspirational; never claimed | README "Future work" only |

Report status values: `MET`, `NOT MET`, `UNSUPPORTED (N too small)`, `UNAVAILABLE (no data)`.

---

## 2. Ground truth protocol

**Annotation unit:** one *real transfer event* per row in `data/manifests/annotations/<clip>.csv`:
`clip, transfer_id, prop, t_pick, t_bag, scanned_truth (yes|no), evidence_adequate (yes|no), inadequate_cause, annotator, notes`.

**Rules**
1. Annotators watch the raw clip (VLC, time shown) and **never see system output** while labelling.
2. `evidence_adequate` follows a written rubric, decided from the video alone: **adequate** = item visible in ≥ 70% of the pick→bag interval, one person in the zone, lighting/blur acceptable. Else **inadequate**, with a cause (`occlusion`, `multi_person`, `low_light`, `blur`, `out_of_frame`).
3. Two people independently label ≥ 5 clips; agreement within ±0.5 s on times defines the **tolerance floor** (event matching tolerance = max(1.0 s, 2× observed disagreement)).
4. `scanned_truth` is a *staging fact* (we decided whether to generate a scan), recorded in the manifest before recording each clip.
5. Items that appear in a clip but are not transferred (distractors) are listed in `distractors` so visual false positives can be counted.

**Expected decision label** (derived mechanically, not by looking at output):

| scanned_truth | evidence_adequate | Scan feed condition | `expected_decision` |
|---|---|---|---|
| yes | yes | scan present, in window, unambiguous | MATCHED |
| yes | yes | scan present but late-ingested | MATCHED (final), first-issued may be REVIEW → counted as false REVIEW |
| no | yes | none, feed healthy | REVIEW |
| any | no | any | ABSTAIN |
| any | yes | ambiguous/competing, malformed timestamps, feed gap, contradictory | ABSTAIN |

**Leakage controls**
- `data/splits.yaml`: each **clip** (and every transaction variant derived from it) belongs to exactly one of `dev` or `test`. Target ≈ 60/40.
- Tuning (λ, thresholds, zones, quality cut-offs) uses **dev only**.
- Freeze: commit `configs/prereg_v1.yaml` + `splits.yaml`, tag `prereg-v1`. `make eval-test` refuses to run if the tag is missing or the config hash differs.
- The test split is run **once** for the headline table. Any later change creates `prereg_v2` and the table says so.
- Generator seeds for test variants are different and unused during development.

---

## 3. Scenario suite

`✔ video` = needs a real clip. `variant` = same clip, different generated transaction stream (stays in the clip's split).

| ID | Scenario | Real video? | Expected |
|---|---|---|---|
| S01 | Legit: one item, scan within window | ✔ video (several clips, different props) | MATCHED |
| S02 | Staged unscanned transfer, good visibility | ✔ video | REVIEW |
| S03 | 3 items handled, 2 scans (deck scenario) | ✔ video | 2 MATCHED + 1 REVIEW |
| S04 | Delayed scan (valid event time, late ingest) | variant of S01/S03 | first REVIEW → revised MATCHED |
| S05 | Duplicate transaction event (exact id / txn_line_id) | variant | MATCHED, no extra intervention |
| S05b | Heuristic duplicate (same sku, <1.5 s, no key) | variant | MATCHED; leftover flagged, not intervention |
| S06 | Missing / malformed / naïve timestamp | variant | ABSTAIN (ts_invalid) |
| S07 | Missing product info (null sku / no class map) | variant | MATCHED on T/Z only (no mismatch penalty) |
| S08 | Inadequate visual evidence (body blocks view / dark) | ✔ video | ABSTAIN |
| S09 | Tracking loss (item behind obstacle, fast motion) | ✔ video | ABSTAIN or MATCHED, never REVIEW unless Q passes |
| S10 | Two items within 2 s, two scans with near-equal cost | ✔ video | ABSTAIN on ambiguous pair |
| S11 | Clean transaction a naïve 5 s matcher flags (scan 6–8 s late) | variant | MATCHED |
| S12 | Contradiction: scan before pickup / sku class conflict | variant | ABSTAIN or REVIEW per R12/R13/R30 |
| S13 | Feed gap (missing records because feed was down) | variant | ABSTAIN |
| S14 | Two people overlap in zone | ✔ video | ABSTAIN |
| S15 | Scans with no visual transfer (orphans) | variant of a no-transfer clip | INFO, no intervention |
| N01 | **Negative control:** person walks past shelf, no transfer | ✔ video | no visual events; any event = visual false positive |
| B01 | **Baseline-favourable:** clean transfer with mediocre quality | ✔ video | MATCHED; TraceCart may over-abstain — report it |

Bias warning: S11 is designed so the baseline fails. B01 and the natural clips (S01–S03) are the fair test. The headline comparison is reported **twice**: natural clips only, and full suite.

**Engine-only synthetic stress set (`E-SYN`)**: hand-built visual events (provenance `synthetic_visual`) × scan recipes, ≥ 3,000 clean events with randomised timing, used only for engine false-REVIEW and abstention behaviour. Labelled "engine-only synthetic; not real-world evidence".

**Minimum data to proceed:** ≥ 18 clips total; ≥ 10 with a real transfer under adequate evidence; ≥ 6 deliberately adverse; ≥ 2 negative controls. If fewer, metrics print `UNSUPPORTED`.

---

## 4. Metric definitions and denominators

Let `V_true` = annotated real transfers; `V_det` = system visual events.

### 4.1 Visual front end (separately from matching)
- **Transfer-event recall** = `|annotated transfers with a detected event within ±tol of t_bag and same prop class| / |annotated transfers|`.
- **Transfer-event precision** = `|detected events matching an annotation| / |V_det|`. Unmatched detections = visual false positives.
- **Event-time error** = median / p90 `|t_bag_det − t_bag_true|`.
- Frame-level detector mAP: **UNAVAILABLE** (no box-level labels; we do not make them).

### 4.2 Event matching (association) — pairs `(visual, scan)`
- Ground-truth pairs come from the staging manifest (which scan corresponds to which transfer).
- **Matching precision** = correct selected pairs ÷ selected pairs. **Matching recall** = correct selected pairs ÷ ground-truth pairs.
- Reported in two modes: **engine-given-truth** (inputs = annotated visual events, isolating the engine) and **end-to-end** (detector events).
- Deck target "event-association precision ≥ 85%" maps to **matching precision on staged scenarios, end-to-end and engine-given-truth both shown**.

### 4.3 Discrepancy detection (REVIEW is the positive)
- Positive units = `expected_decision == REVIEW` (unscanned, adequate evidence).
- **Detection recall** = positives with first-issued REVIEW ÷ positives. (ABSTAIN on a positive = miss, also reported as "abstained-positive rate".)
- **Detection precision** = true-positive REVIEWs ÷ all REVIEWs (includes REVIEWs issued on clean or inadequate units).
- Deck "unmatched-transfer recall ≥ 80% at adequate coverage" = **detection recall on adequate-evidence positives**.

### 4.4 Clean-transaction false intervention
- Denominator = **clean units** (`scanned_truth=yes ∧ evidence_adequate=yes`).
- **False-REVIEW rate** = clean units whose **first-issued** decision is REVIEW ÷ clean units. REVIEW **counts as an operational intervention**.
- **Clean-abstain rate** = clean units with ABSTAIN ÷ clean units. Reported separately; ABSTAIN is **not** a "correct negative" and is not silently merged.
- Per-1,000 conversion is shown only when `N_clean ≥ 3,000`; otherwise `UNSUPPORTED`, with the exact one-sided 95% upper bound: `1 − 0.05^(1/n)` when zero failures (n=20 → 13.9%; 100 → 3.0%; 300 → 1.0%; 1,000 → 0.30%; 3,000 → 0.10%). **The deck's "< 1 per 1,000" cannot be demonstrated with real clips or any small synthetic set.**

### 4.5 Abstention
- **Abstention correctness** = ABSTAIN ÷ units with `evidence_adequate=no` or labelled ambiguous. Deck target ≥ 95% → with N≈20 that tolerates one miss; report Wilson 95% CI (19/20 → [0.76, 0.99]).
- **Unnecessary-abstain rate** = ABSTAIN ÷ units with `evidence_adequate=yes` (cost of caution).
- **Coverage** = units with MATCHED or REVIEW ÷ all units.
- **Risk–coverage view:** error rate among decided units vs coverage, for TraceCart and for baselines — this is the fair way to compare a system that can abstain with one that cannot.

### 4.6 Latency
- **Decision latency** = wall-clock from the moment the last needed input (visual event + feed watermark) is available to decision emitted, per event; median and p95 on named hardware. Deck target "< 2 s per event".
- **Video front-end throughput** reported separately (analysis fps, real-time factor). The two numbers must not be blended.
- Report CPU model, RAM, OS, library versions.

### 4.7 Revisions
- **Revision rate** = decisions superseded by late events ÷ decisions. Trade-off with grace period `G`.

---

## 5. Baseline and the differentiation test

**Baselines** (same inputs, same scorer):
- `B1`: timestamp-only nearest scan, `W=5 s`. `B1b`: `W=10 s`. Outputs MATCHED/REVIEW only.

**Comparison table (identical rows for each system):** detection precision/recall · false-REVIEW rate on clean units · matching precision/recall · coverage · risk at coverage · unnecessary-abstain.

**Decision rule written now:** TraceCart is claimed to improve the trade-off only if, on the **natural-clip subset of the test split**, it (a) lowers false REVIEWs on clean units *or* raises detection precision, (b) without losing more than 10 percentage points of detection recall relative to B1b among adequate-evidence positives. If not, `README` and the pitch must say that the simpler baseline performed comparably and the contribution is *auditability*, not accuracy. With small N this may well be an inconclusive result — say "inconclusive; N = …".

---

## 6. Ablations (small by design)

| ID | Change | Data | Reads out |
|---|---|---|---|
| A1 | Tracker on vs off (per-frame zone presence, no stitching) | real clips, front end | transfer P/R, event-time error |
| A2 | S term on vs off | engine on all scenarios | matching P/R; conflict handling (S12) |
| A3 | λ sweep (small grid, **dev only**) + τ_match, W_gate | dev split | Match/Review/Abstain mix sensitivity |
| A4 | Occlusion stress: black box over item path on 0/25/50/75% of frames in ~6 clips (**synthetic augmentation, labelled**) | augmented clips through real detector | ABSTAIN rate vs occlusion; REVIEW must not rise |
| — | Rule policy vs learned risk score | — | **UNAVAILABLE** (no labels; dropped) |

A3 may inform thresholds *only before* the freeze. A1/A4 run once on the frozen setup.

---

## 7. Target-versus-measured reporting template

`runs/<id>/results.md` (generated by `make report`; stamped with config hash, git commit, hardware):

| Metric | Denominator | Deck target | Internal MVP acceptance | Measured (value · N · 95% CI) | Status | Future pilot target |
|---|---|---|---|---|---|---|
| Matching precision (e2e) | selected pairs | ≥ 85% | ≥ 80% | — | — | per pilot |
| Matching precision (engine-given-truth) | selected pairs | ≥ 85% | ≥ 85% | — | — | |
| Detection recall (adequate positives) | adequate unscanned units | ≥ 80% | ≥ 70% | — | — | |
| Visual transfer-event recall | annotated transfers | — | ≥ 70% | — | — | |
| Decision latency (median / p95) | events | < 2 s | < 2 s | — | — | |
| Abstention correctness | inadequate/ambiguous units | ≥ 95% | ≥ 90% | — | — | |
| False REVIEW on clean units (real clips) | clean units | < 1/1000 | **0 observed, report UB** | — | **UNSUPPORTED** | |
| False REVIEW (E-SYN engine-only) | synthetic clean events | < 1/1000 | ≤ 1/1000 observed | — | labelled synthetic | |

Acceptance values above are **proposed now**; if they change, record it in `DECISION_LOG.md` before the test run.

---

## 8. Limitations to print in the README and results page

1. ~20 staged clips, one scene, one camera, teammates, COCO-class props: **no generalisation claim**.
2. Scan events are **synthetic**; timing noise is our assumption, not measured retailer behaviour.
3. Session linkage is by manifest context, not by visual identification of people.
4. Product evidence is COCO class only; **no SKU recognition**.
5. Annotators are the builders; agreement is checked on a subset only.
6. Stress scenarios were authored by us and can favour our design; natural-clip results are reported separately.
7. Thresholds were tuned on the dev split; test results are single-run.
8. Very-low false-alert rates cannot be established at this scale.

---

## 9. Verification checklist before publishing results
- [ ] Config hash in `metrics.json` equals tagged `prereg_v1`.
- [ ] No test clip used in tuning (`splits.yaml` diff check).
- [ ] Every metric lists numerator, denominator and N.
- [ ] Unsupported/unavailable metrics are printed as such, not omitted.
- [ ] First-issued decisions used for false-intervention metrics.
- [ ] Baseline and TraceCart scored by the same function.
