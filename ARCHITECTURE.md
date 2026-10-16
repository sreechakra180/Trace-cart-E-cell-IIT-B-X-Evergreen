# TraceCart — Architecture

Everything here is a **design for code that does not yet exist**. Default numeric values are *initial proposals*, tunable on the dev split only, then frozen (see `EVALUATION_PLAN.md` §6).

---

## 1. System flow

```
 real video clip ──► [V1 decode+zones] ──► [V2 detect+track] ──► [V3 transfer-event extraction + quality metrics]
        │                                                                 │  (cached: data/cache/obs/*.jsonl)
        │                                                                 ▼
 scenario manifest ──► [G1 scan-feed generator, seeded]  ──► scan feed (JSONL, provenance=synthetic_generated)
        │                                                                 │
        ▼                                                                 ▼
                       [I1 ingestion + validation + clock alignment] ─► typed events + data-quality flags
                                                │
                                      [R1 candidate gating]
                                                │
                                      [R2 cost matrix + assignment]
                                                │
                                      [R3 evidence-quality gate]
                                                │
                                      [P1 decision policy R01–R40]
                                                │
                              ┌─────────────────┴──────────────────┐
                       [E1 evidence packets]               [B1 baseline decisions]
                              │                                     │
                       [U1 Streamlit console]            [EV1 evaluator vs ground truth]
```

| Stage | Real video? | Synthetic allowed? |
|---|---|---|
| V1–V3 | **Must run on real video** (or replay of its cache, labelled) | No — never fabricate detections |
| G1 scan feed | n/a | **Yes, always labelled** `synthetic_generated` |
| I1, R1–R3, P1, E1, B1 | n/a (consume events) | Engine unit tests may use hand-built visual events labelled `synthetic_visual` |
| EV1 | Needs annotations from real clips | Engine-only stress sets reported separately |

---

## 2. Repository layout (to be created later)

```
tracecart/
  README.md  LICENSE  Makefile  pyproject.toml
  requirements-core.txt        # numpy scipy pydantic pyyaml pytest streamlit opencv-python-headless
  requirements-vision.txt      # ultralytics (pulls torch) lapx
  configs/  zones.yaml  skumap.yaml  policy.yaml  prereg_v1.yaml
  data/
    clips/            *.mp4 (≈960x540)
    manifests/        scenarios.csv  clips.csv  annotations/*.csv
    cache/obs/        per-clip detections+tracks (JSONL)  <- produced by REAL detector
    feeds/            generated scan feeds (JSONL)         <- synthetic, labelled
    splits.yaml       dev/test assignment (frozen)
  src/tracecart/
    schema.py         # pydantic models, enums, reason codes
    timeutil.py       # parse/align timestamps
    vision/ decode.py zones.py detect_track.py events.py quality.py render.py
    feeds/  generate.py        # noise model, seeded
    ingest.py  gate.py  cost.py  assign.py  quality_gate.py  policy.py  packets.py
    baseline.py  pipeline.py  config.py
    eval/ metrics.py  ablate.py  report.py
  app/streamlit_app.py
  tests/  test_schema.py test_time.py test_cost.py test_assign.py test_policy.py
          test_baseline.py test_scenarios.py test_pipeline_e2e.py
  runs/<run_id>/  decisions.jsonl  packets/*.json  metrics.json  config_snapshot.yaml
  docs/
```

Two install tiers: `pip install -r requirements-core.txt` (engine, tests, demo-from-cache) and `-r requirements-vision.txt` (re-run real detector).

---

## 3. Conventions

- **Time:** all internal times are UTC epoch seconds (float). Transaction input must carry ISO-8601 *with* timezone; naïve strings → `ts_naive` flag (assume `Asia/Kolkata` only if config `assume_tz` is set; otherwise treat as invalid).
- **Visual time:** `t = clip_start_epoch + frame_idx / fps` (fps read from file metadata; `fps_unreliable` flag if metadata is 0 or VFR detected).
- **Clock alignment:** each source has `clock_offset_s` in config; applied once at ingestion and recorded on the event (`clock_offset_applied`). Tests inject known offsets.
- **event time vs ingest time:** `t_event` = when it happened; `t_ingest` = when TraceCart could have known. Delayed scans have `t_ingest > t_event`.
- **IDs:** deterministic, e.g. `V-<clip>-<tid>-<n>`, `S-<feed>-<seq>`; decisions `D-<v_id>-v<version>`.
- **Provenance enum:** `video_cv`, `synthetic_generated`, `synthetic_visual`, `ground_truth` (**never** fed to engine), `manual_annotation`.
- **Privacy:** no face model is imported anywhere; `person` detections are used **only** as a count/overlap ambiguity signal; session ids are pseudonymous strings from the manifest.

---

## 4. Event schemas (schema_version `0.1`)

### 4.1 `VisualTransferEvent`

| Field | Type | Notes |
|---|---|---|
| `v_id` | str | |
| `provenance` | enum | `video_cv` / `synthetic_visual` |
| `session_id` | str | from manifest (context link, **not** visual identification) |
| `camera_id`, `zone_path` | str, list[str] | e.g. `["Z_PICK","Z_BAG"]` |
| `store_zone` | str | logical zone name (e.g. `aisle04`) for matching a scan `zone_hint` |
| `track_id` | int | local to clip; may be broken by tracker |
| `t_pick`, `t_bag`, `t_ref` | float | `t_ref = t_bag` |
| `t_ingest` | float | `t_bag + latency` (offline replay: `t_bag + 0.5`) |
| `cls_votes` | dict[str,float] | confidence-weighted class share, sums to 1 |
| `det_conf_median` | float | detector confidence — **a visibility signal, never a theft probability** |
| `track_continuity` | float 0–1 | frames with detection ÷ frames in span (at sampled fps) |
| `gap_max_s` | float | longest detection gap in span |
| `n_persons_max` | int | max person boxes overlapping the transfer region (count only) |
| `luma_mean`, `blur_var_min` | float | frame-quality proxies |
| `n_frames` | int | |
| `quality_flags` | list[str] | `ts_invalid`, `fps_unreliable`, `short_track`, `multi_person`, `low_light`, `blurry`, `id_switch_suspect` |
| `source_ref` | obj | `{clip, frame_start, frame_end, cache_file}` |

### 4.2 `TransactionScanEvent`

| Field | Type | Notes |
|---|---|---|
| `s_id` | str | |
| `provenance` | enum | `synthetic_generated` (real feeds if ever available: `retailer_feed`) |
| `session_id` | str | |
| `t_scan` | float | UTC epoch after parse; `None` if malformed |
| `t_ingest` | float | |
| `sku`, `qty`, `zone_hint` | str?, int, str? | `sku`/`zone_hint` may be null → *missing*, not *mismatch* |
| `txn_status` | enum | `committed` / `pending` / `voided` |
| `txn_line_id`, `source_seq` | str?, int? | idempotency keys |
| `quality_flags` | list[str] | `ts_invalid`, `ts_naive`, `sku_missing`, `qty_invalid`, `duplicate_of:<id>`, `possible_duplicate`, `voided` |
| `source_ref` | obj | feed file + line |

### 4.3 `FeedHeartbeat`
`{feed_id, session_id, t_ingest}` — proves the transaction feed was alive; gives the **watermark** (`max t_ingest` seen). No heartbeat ⇒ watermark unknown ⇒ treat as unhealthy.

### 4.4 `CandidateLink` (graph edge)
`{v_id, s_id, slot, gate_pass, gate_reason?, T, Z, S, F, available_terms, cost, selected, margin}`

### 4.5 `Decision` / evidence packet
```json
{
  "decision_id": "D-V-clip07-12-0-v1",
  "version": 1, "supersedes": null,
  "unit": {"type": "visual_transfer", "v_id": "..."},
  "state": "REVIEW",
  "rule_id": "R20",
  "reason_codes": ["NO_CANDIDATE_IN_WINDOW","EVIDENCE_QUALITY_OK","FEED_HEALTHY"],
  "visual": { ...VisualTransferEvent summary + media refs... },
  "candidates": [ {CandidateLink...} ],
  "association": {"selected_s_id": null, "best_cost": null, "margin": null},
  "evidence_quality": {"det_conf":0.71,"continuity":0.88,"gap_max_s":0.3,"n_persons":1,"frame_quality":"ok","pass":true,"failed":[]},
  "timing": {"t_ref":..., "grace_s":20, "watermark":..., "time_diffs_s": {}},
  "warnings": ["product_evidence_coarse(class-level only)"],
  "recommended_action": "Request a low-friction rescan/verification per store policy. This is a verification request, not an accusation.",
  "config_hash": "sha256:...", "code_commit": "...",
  "human_resolution": null
}
```
Orphan scans (scan with no visual transfer) are emitted as `unit.type = "scan_orphan"` with state `INFO` — **not** an intervention and not counted in the three-state metrics.

---

## 5. Vision front end (V1–V3)

1. **Decode** with OpenCV; process at `analysis_fps = 10` (stride from native fps).
2. **Zones**: polygons in `configs/zones.yaml` in pixel coordinates (`Z_PICK`, `Z_BAG`, optional `Z_IGNORE`). A debug render must overlay them (task T-021) because wrong zones are the most likely silent bug.
3. **Detect + track**: YOLO nano/small, COCO classes restricted to `eligible_classes` ∪ `person`; conf ≥ 0.25 (low, because hand-held items score low); ByteTrack through the same library. Save every frame's boxes/IDs/conf to `data/cache/obs/<clip>.jsonl`.
4. **Transfer extraction** (pure Python on the cache — fast, testable, no torch):
   - For each non-person track: record the first frame its box centre is inside `Z_PICK` and the first later frame inside `Z_BAG`.
   - Accept if `t_bag − t_pick ∈ [min_dt, max_dt]` (defaults 0.3–15 s), `n_frames ≥ 8`, class ∈ eligible.
   - **Track stitching (limited):** if a track ends and another of the same class begins within 1.0 s and 80 px of the end position, merge and set `id_switch_suspect` (the A1 ablation turns this off).
   - Quality metrics as in §4.1; `n_persons_max` counted from `person` boxes overlapping the pick→bag path region.
5. **Known limits (written into the UI):** item in hand may not be detected; identical items are indistinguishable; transfers outside the two zones don't exist for us.

---

## 6. Scan feed generator (G1) — synthetic, seeded

Input: clip's ground-truth annotation (`t_pick`, `t_bag`, `prop`, `scanned: yes/no`) + scenario recipe. Output JSONL with provenance `synthetic_generated`.

Noise model (documented, seeds recorded in manifest):
- `scan_time = t_bag + U(-6, +6)` s for clean (ordinary timing) **or** recipe-specific (e.g., +9 s for "late but valid").
- `ingest_delay = lognormal`, clipped, or recipe-specific (e.g., +35 s → *delayed event*).
- Recipes: `clean`, `unscanned`, `late_ingest`, `duplicate_exact`, `duplicate_heuristic`, `bad_ts`, `naive_ts`, `sku_missing`, `sku_class_conflict`, `competing_pair`, `voided`, `scan_before_pickup`, `feed_gap`.
- Heartbeats every 5 s of ingest time; `feed_gap` removes them across the window.

**Leakage guard:** the generator reads ground truth; the engine never does. The test split's seeds are different and not used during tuning (`splits.yaml`).

---

## 7. Association (R1–R2)

For each session, visual events `V = {v_i}`, scan units `S = {s_j,k}` where a scan with `qty = q` expands into `q` slots `k = 1..q`. Voided and exact-duplicate scans are removed first (kept in the packet as warnings).

### 7.1 Gating (hard)
Pair `(i, j)` is a candidate only if **all** hold:
- same `session_id`;
- both timestamps valid;
- `d(i,j) ≤ W_gate` (default **10 s**) where `d` is the distance from `t_scan` to the handling interval `[t_pick, t_bag]` (0 if inside);
- if `zone_strict` and both zones known: zones equal (default `false` → mismatch is a penalty, not exclusion);
- scan `txn_status ≠ voided`.

### 7.2 Cost terms (each in [0,1])

| Term | Definition |
|---|---|
| **T** temporal | `T = min(1, d(i,j) / W_norm)`, `W_norm = 10 s` |
| **Z** zone | `0` if zone_hint missing **or** equals `store_zone_i`; `1` if both known and different. *Missing ⇒ term unavailable* (see below), not 0 |
| **S** product | If `sku_j` has a class in `skumap.yaml` **and** `cls_votes_i` exists: `S = 1 − cls_votes_i[class(sku_j)]`. Else **unavailable** |
| **F** flow/quantity | `F = max(slot_pen, status_pen)`; `slot_pen = 0` for slot 1, `0.5` for slots ≥ 2 of a qty > 1 line (cannot tell which physical unit); `status_pen = 0.5` if `pending`, else 0 |

**Missing-term handling.** With available set `A ⊆ {T,Z,S,F}` and weights `λ`:

`C(i,j) = Σ_{k∈A} λ_k · k(i,j) / Σ_{k∈A} λ_k`  → always in [0,1]; missing info is never treated as mismatch.

Default λ: `λ_T=0.50, λ_Z=0.15, λ_S=0.25, λ_F=0.10`.
Worked example: scan 6 s after bag entry, zone unknown, SKU class prob 0.8, committed: `T=0.6, S=0.2, F=0` → `A={T,S,F}`, `C=(0.5·0.6+0.25·0.2+0)/0.85 = 0.41`.

### 7.3 Assignment
Build matrix `C` over gated pairs (non-gated = `BIG`). Solve `scipy.optimize.linear_sum_assignment`. Accept pair if `C ≤ τ_match` (default **0.50**). Rejected/unassigned visual events go to the policy as "no accepted match".
Deterministic tie-breaking: sort by `(cost, d, s_id, v_id)`; add `ε = 1e-9·rank` jitter-free tie-break terms so results are reproducible.

### 7.4 Ambiguity
For each accepted pair `(i,j)`: `margin_i = min over other candidates j' of C(i,j') − C(i,j)`, and likewise `margin_j` over rival visual events. `ambiguous = min(margin_i, margin_j) < δ_amb` (default **0.10**). Equal-cost rivals ⇒ margin 0 ⇒ ambiguous.
For each *unmatched* visual event: `near_miss` if it has a gated candidate with `C ≤ τ_match + δ_amb` (competed for and lost).

---

## 8. Evidence-quality gate (R3)

Association quality (cost, margin) and **evidence quality** (can we trust the *visual* observation and the *feed*?) are separate.

| Component | Pass condition (defaults) |
|---|---|
| `det_conf_median` | ≥ 0.45 |
| `track_continuity` | ≥ 0.70 |
| `gap_max_s` | ≤ 1.0 |
| `n_frames` | ≥ 8 |
| `n_persons_max` | ≤ 1 |
| frame quality | `luma_mean ∈ [40,220]` and `blur_var_min ≥ 50` (calibrate once on clips; then freeze) |
| timestamps | visual and relevant scans valid, `fps_unreliable` absent |
| feed | heartbeat watermark ≥ `t_ref + G` (default **G = 20 s**) and no `feed_gap` |

`Q_pass = AND` of all components (conservative: one weak link blocks REVIEW). The failing components are listed in the packet. No weighted "confidence score" is shown as a probability.

---

## 9. Decision policy (P1) — evaluated top-down, first match wins

| Rule | Condition | State |
|---|---|---|
| **R01** | visual `ts_invalid` or session link missing | ABSTAIN |
| **R02** | feed unhealthy (no heartbeat / gap / watermark < `t_ref+G`) **and** no accepted match | ABSTAIN |
| **R10** | accepted match, not ambiguous, no class conflict | MATCHED |
| **R11** | accepted match but ambiguous | ABSTAIN |
| **R12** | accepted match but *class conflict* (`S ≥ 0.9` and top visual class prob ≥ 0.6) **and** `Q_pass` | REVIEW |
| **R13** | class conflict and not `Q_pass` | ABSTAIN |
| **R20** | no accepted match, no near-miss, `Q_pass`, feed healthy, grace elapsed | **REVIEW** |
| **R21** | no accepted match and not `Q_pass` | ABSTAIN (list failed components) |
| **R22** | no accepted match but near-miss candidate exists | ABSTAIN |
| **R30** | contradictory sequence: only candidate scan precedes `t_pick` by > `W_gate` or sku/class conflict with no valid alternative | ABSTAIN |
| **R40** | scan with no visual transfer | `INFO` (orphan, no intervention) |

**Re-evaluation on late events.** Decisions are recomputed whenever a new scan/heartbeat arrives (`t_ingest` order). A late scan with in-window `t_event` that arrives after a REVIEW supersedes it with a MATCHED version 2 (`supersedes = D-…-v1`, reason `LATE_EVENT_REVISION`). Both versions are kept, and the evaluator counts the *first-issued* decision for false-REVIEW metrics (otherwise late data would hide false REVIEWs).

**Recommended-action templates** (fixed strings, non-accusatory): MATCHED → "No action." REVIEW → "Request a low-friction rescan/verification per store policy. Verification request, not an accusation." ABSTAIN → "No alert. Insufficient/ambiguous evidence: <reasons>. Optional alternative verification only if store policy allows."

---

## 10. Baseline (B1)

`timestamp_only`: for each visual event (same session) take the nearest unused scan by `|t_scan − t_ref|` within `W_base = 5 s`, greedy in time order; no zone/product/quality; outputs MATCHED or REVIEW only (no ABSTAIN). Also reports a variant with `W_base = 10 s`. Both baselines get the same inputs and the same scoring.

---

## 11. Interfaces (module contracts)

```
vision.extract(clip_path, zones, cfg) -> list[VisualTransferEvent]        # uses cache if present
feeds.generate(annotation, recipe, seed) -> list[TransactionScanEvent|FeedHeartbeat]
ingest.load_feed(path, cfg) -> (events, data_quality_log)                  # never raises on bad rows
pipeline.run(visuals, feed, cfg) -> list[Decision]                         # pure function, deterministic
baseline.run(visuals, feed, cfg) -> list[Decision]
packets.write(decisions, run_dir)
eval.score(decisions, ground_truth, cfg) -> MetricsReport
```
CLI: `python -m tracecart.run --scenario S03 --mode cache|live --out runs/...`; `make demo`, `make test`, `make eval-dev`, `make eval-test` (refuses to run unless `prereg_v1` tag exists and config hash matches), `make report`.

---

## 12. Explanatory event graph (P1)
Per session, nodes = visual and scan events; edges = *all gated candidate links* with cost labels; selected assignments bold; unmatched visual nodes highlighted. Rendered with Graphviz DOT from `candidates` in the packet. If it is not generated from real packets, it does not ship.

---

## 13. Test map (what proves each module works)

| Module | Test |
|---|---|
| schema/ingest | malformed timestamp, naive timestamp, null SKU, duplicate ids → flags, no crash |
| timeutil | known clock offset recovered; tz handling |
| zones/events | synthetic track trajectories produce / don't produce transfer events (ordering, min frames) |
| cost | each term's boundary values; missing term renormalisation keeps C∈[0,1] |
| assign | competing candidates, equal cost, 3 visuals/2 scans, qty-2 slots, deterministic |
| policy | one test per rule R01–R40 |
| late event | REVIEW → MATCHED revision with both versions stored |
| baseline | known failure cases reproduce |
| e2e | `make demo` on cached data returns expected states for S02/S03/S08 |
| eval | metric denominators on a hand-computed toy set |
