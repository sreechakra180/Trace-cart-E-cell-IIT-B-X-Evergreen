# TraceCart — Demo Plan

Everything below describes an *intended* demo. Expected states are the **design intent**; the actual outputs must be re-checked once the system exists (T-072).

---

## 1. Principles
- Every screen says what is **real** (recorded video, real detector output) and what is **synthetic** (scan feed). Badges: `REAL VIDEO` · `CACHED DETECTOR OUTPUT (replay)` · `SYNTHETIC SCAN FEED`.
- Never say "theft", "caught", "shoplifter". Say "unmatched transfer", "verification request".
- Show a failure/abstention on purpose: it is the differentiator.
- The demo must run from the **core install + committed cache** with no GPU, no network.

## 2. Sequence (target 5 min + 3 min Q&A)

| # | Time | Screen | What the audience sees | Expected state |
|---|---|---|---|---|
| 0 | 0:00–0:30 | Title + one sentence | "A camera sees movement; a scan log records scans. We reconcile them, and abstain when evidence is weak." | — |
| 1 | 0:30–1:30 | **S01** clean clip with overlay | Zones `Z_PICK`→`Z_BAG`, tracked item, scan feed row (labelled synthetic) 3 s later; candidate table with T/Z/S/F | **MATCHED**, cost shown |
| 2 | 1:30–2:45 | **S03** 3 items, 2 scans (hero) | Three transfer events on the timeline; two links drawn; one unmatched; evidence panel opens | 2×MATCHED + 1×**REVIEW** (rule R20, quality passes, feed healthy, grace elapsed) |
| 3 | 2:45–3:30 | **S08** occlusion/dark | Same transfer, quality gate fails (continuity/visibility) | **ABSTAIN** (R21), "failed: track_continuity, gap_max" |
| 4 | 3:30–4:00 | **S04** delayed scan | Timeline replay: REVIEW v1, scan arrives late, MATCHED v2 (supersedes) | REVIEW → **MATCHED** with `LATE_EVENT_REVISION`; show it counts as a false REVIEW in metrics |
| 5 | 4:00–4:40 | **Baseline vs TraceCart** table | Same scenarios, same scorer, natural-clip and full-suite columns | Whatever the numbers are. If inconclusive, say so |
| 6 | 4:40–5:00 | **Results table** (target vs measured) | Four columns; UNSUPPORTED row for false REVIEW <1/1000 | Honest statuses |

Optional (if time): S10 ambiguous pair → ABSTAIN (R11), event graph view of its candidate links.

## 3. Inputs and outputs per step
- Inputs: `data/clips/*.mp4`, `data/cache/obs/*.jsonl`, `data/feeds/*.jsonl`, `configs/prereg_v1.yaml`.
- Command: `make demo` (writes `runs/demo-…`), then `streamlit run app/streamlit_app.py`.
- Outputs shown: overlay video, decision card, candidate table, evidence packet JSON (collapsible), config hash + git commit footer.
- Evidence packet shows: visual event, candidate scans with time differences, zone/product evidence, T/Z/S/F values, missing-information warnings, rule id, recommended action, quality components pass/fail.

## 4. Pre-demo checklist (T-072)
- [ ] Fresh clone works on the demo laptop; Streamlit port free.
- [ ] Hardware, Python, library versions noted for the latency slide.
- [ ] Offline mode tested (airplane mode).
- [ ] Backup screen recording saved locally (not only on the repo).
- [ ] Screenshots of S01/S02/S03/S08/S04 + results table in `docs/img/` (generated from the real UI).
- [ ] All labels present: REAL VIDEO / REPLAY / SYNTHETIC.

## 5. Failure recovery

| Failure | Recovery |
|---|---|
| Streamlit won't start | `python -m tracecart.run --scenario S03 --print` (CLI table), or open `runs/…/results.md` + screenshots |
| Video won't play | Use pre-rendered overlay GIFs / stills; the packet JSON still shows evidence |
| torch/weights fail | Not needed — demo uses cache; say "replaying cached detector output" |
| Live detector asked for | Run `make vision CLIP=clip07` only if the install is verified; otherwise say it ran offline and show the cache hash |
| Result disagrees with expectation | Show it, explain the rule that fired; do not re-tune on stage |
| Judge asks for another scenario | Use `--scenario` flag on any clip; if the clip isn't cached, say so |

## 6. Technical pitch (~60 s)

> Scan & Go moves checkout into the aisle, so two data streams drift apart: what the camera sees and what the phone scanned. TraceCart reconciles them as an *event-association* problem rather than an object-detection problem. A real detector and tracker turn recorded video into zone-ordered transfer events with quality metrics. A gated, minimum-cost assignment links those events to scan records using time, zone, product-class and flow terms — and treats missing information as missing, not as mismatch. A separate evidence-quality gate decides whether we're even entitled to raise a flag: weak visibility, ambiguous matches, a dead transaction feed all lead to **ABSTAIN**. Every decision ships with an evidence packet listing the rule that fired. We evaluate against annotated clips and a timestamp-only baseline, with pre-registered thresholds, and we report what we could not establish — including false-alert rates that need far more data than a hackathon allows. It flags discrepancies for verification; it never declares theft.

## 7. Likely judge questions — honest answers

| Question | Answer to give (check against actual results first) |
|---|---|
| "Is this detecting SKUs?" | No. COCO class-level consistency only, via a configured SKU→class map for our props. |
| "Are the scan events real?" | No — synthetic, generated from annotated ground truth with a stated noise model and seeds. Real integration is future work. |
| "How is the shopper linked to the scan?" | By session context in the manifest. We do not identify people. |
| "Does it beat a timestamp matcher?" | Show the table. Natural-clip N is small; if the difference isn't clear, say it's inconclusive. |
| "What about the <1/1000 false-alert target?" | Unsupported at this scale; show the upper bound. |
| "Why not train a model?" | No labelled data, and no measured need; rules are auditable. |
| "What does Everseen's system do that this doesn't?" | Almost everything at scale. We contribute an auditable reconciliation-and-abstention layer, as a concept to evaluate. |
| "Licence of the detector?" | Ultralytics YOLO is AGPL-3.0; repo is public/compliant per rules; weights not redistributed unless licence allows. |
| "Does it run live?" | Recorded clips; cached detector output replay by default; live re-run available if installed. |
