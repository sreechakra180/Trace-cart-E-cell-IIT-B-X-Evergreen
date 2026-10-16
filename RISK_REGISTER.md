# TraceCart — Risk Register

P = probability, I = impact (L/M/H). Probabilities are judgement, not data.

| ID | Risk / assumption | P | I | Early warning signal | Mitigation | Fallback | Cut condition |
|---|---|---|---|---|---|---|---|
| R-01 | Official rules differ from assumptions (repo visibility, licence, deliverables, post-cutoff commits) | M | H | T-001 finds items we didn't plan | Read portal tonight; record in D00 | Adapt README/visibility; ask organisers by email | n/a — resolve before Fri 08:00 |
| R-02 | Torch/Ultralytics won't install or weights can't download (network, Python version, no wheels) | M | H | T-002/T-020 fail | Separate `requirements-core` / `-vision`; try Python 3.11; pre-download weights on a working machine | **Fallback C** front end (OpenCV background subtraction); cache committed so demo needs no torch | G0/G1 fail → switch immediately |
| R-03 | Detector misses hand-held props / low recall on our clips | H | H | G1 recall < 60% | Lower conf (0.25), imgsz 960, try small model, use props with large simple shapes (bottle, orange), plain background | Fallback C; or restrict to props the detector sees and **say so** | If still < 40% after 45 min → C |
| R-04 | Footage not recorded early or too few clips | M | H | < 12 clips by 10:30 Fri | Props prepared Thu night; shot list; two people | Smaller test split → metrics print UNSUPPORTED; licence-verified public clip for pipeline testing only | < 8 clips → say so in README; focus on engine + demo |
| R-05 | Zones mis-specified; transfers never trigger | M | H | Overlay shows no events on clean clips | T-021 debug overlay on 3 clips before tracking | Re-draw zones; widen `max_dt` | — |
| R-06 | ID switches / track fragmentation break events | H | M | Many `id_switch_suspect` flags | Limited stitching; A1 ablation reports effect | Accept lower recall; ABSTAIN behaviour covers it | Drop stitching if it creates false events |
| R-07 | Annotation takes longer than 2 h | M | M | < 50% annotated by 14:00 Fri | U starts as soon as clips exist; CSV + VLC only | Annotate dev clips first; test clips by Sat 10:00 | Annotate fewer test clips; flag N |
| R-08 | Evaluation looks tuned (leakage / post-hoc thresholds) | M | H | Test run before tag; config hash mismatch | `splits.yaml`, tag `prereg-v1`, `make eval-test` guard | Report as exploratory | If violated, label the result "exploratory" |
| R-09 | Baseline matches TraceCart (no demonstrated benefit) | M | M | Dev results equal | Decision rule pre-written (EVAL §5) | Pitch pivots to auditability/abstention behaviour | — (report honestly) |
| R-10 | Synthetic scans seen as circular (we make data, then match it) | H | M | Judge questions | Provenance labels, noise model documented, natural vs stress split, separate visual metrics | Emphasise the real-video front end and failure analysis | — |
| R-11 | Engine over-abstains (unnecessary-abstain high) | M | M | Clean-abstain rate high on dev | Report risk–coverage; B01 scenario; tune on dev before freeze | Loosen quality cut-offs pre-freeze | — |
| R-12 | Scope creep (graph, SQLite, FastAPI, learned score) | H | H | Work started on P1/P2 before G3 | Cut ladder; G3 rule "no new features until e2e works" | — | Feature freeze Sat 20:30 |
| R-13 | Streamlit/dependency issues on judge machine | M | M | Fresh-clone test fails | Core tier tiny; pinned lower bounds; CLI + static screenshots | `make demo --print` text mode | — |
| R-14 | Repo too large / licence problem (clips, weights, AGPL) | M | M | `du -sh .git` > ~100 MB | Re-encode clips; no weights in repo; README licence note | Host clips as release asset if allowed | — |
| R-15 | Teammates in clips haven't consented / privacy concerns in a public repo | L | M | Objection | Frame torso/hands; only teammates; confirm before pushing | Keep clips private, share cache + screenshots | Remove clips, keep cache |
| R-16 | Team fatigue / sleep debt → bugs near deadline | H | H | Late commits with failing tests | Scheduled sleep, code freeze Sat 23:00, Sunday verification only | — | No features after freeze |
| R-17 | Clock/timestamp alignment bugs (fps metadata, timezone) | M | M | Offsets of whole seconds / 5.5 h | Tests with injected offset; fps check flag | Use frame-index-relative time everywhere in demo | — |
| R-18 | Hard-to-explain results (reasons not computed from data) | L | H | Hard-coded strings | Reasons come from rule table + packet fields; test asserts | — | — |
| R-19 | Deck overclaims vs repo (live, calibrated, FastAPI, learned score) | M | H | README differs from deck | T-074 claim-by-claim reconciliation; DECISION_LOG lists deviations | Update README wording | — |
| R-20 | Submission portal / link problem on Sunday | L | H | Upload errors Sun 09:00 | Submit at 10:00 target, hard stop 11:00; screenshot confirmation | Email organisers with repo link | — |
| R-21 | Slide-2 statistics (ECR) mis-cited | M | L | Judge asks for source | Don't present as TraceCart evidence; verify or drop | Delete slide 2 numbers from talk | — |
