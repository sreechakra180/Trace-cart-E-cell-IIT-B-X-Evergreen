# TraceCart — Change Log (Session: 2026-10-19)

**Scope of this session:** Fix the vulnerabilities and audit findings, harden the
code for a live hackathon demo, add tests/CI/tooling, validate against real
datasets, and publish a final audit.

**Baseline at session start:** 13 tests passing, `pytest` green, but the
end-to-end CLI path was silently broken (the detector cache could not be
ingested), CI was red, and the API server had an unvalidated path-traversal
sink.

---

## Status Legend

| Marker | Meaning |
|---|---|
| ✅ | Fixed and verified |
| 🟡 | In progress |
| ⬜ | Not yet started |

---

## 1. Critical — The End-to-End Demo Path Was Broken

### 1.1 `src/tracecart/pipeline.py` — cache ingestion was structurally wrong ✅

**Finding.** `run_scenario()` called `ingest_visual_events(cache_file, cfg)`,
which tries to validate each cache line as a `VisualTransferEvent`. But the
detector cache stores **raw per-frame detections**
(`{frame, t, x1..y2, class_name, conf, track_id}`) — a completely different
shape. Every line therefore failed Pydantic validation and was silently
dropped into the quality log.

**Measured impact (before fix):**

```
visual events: 0
visual log errors: 60
```

The demo therefore never produced a single real reconciliation decision. The
S01 "clean pick & scan" scenario reported an **orphan scan** (`INFO`/`R40`)
and nothing else — the visual evidence was invisible to the engine.

**Fix.** Added a proper two-stage path that mirrors ARCHITECTURE §5:

- `load_cache_detections(cache_file)` — reads raw detection rows, skipping
  malformed lines instead of aborting the run.
- `load_visuals_from_cache(cache_file, cfg, clip_start_epoch, session_id)` —
  converts detections to `Detection` objects, runs the V3 transfer-event
  extraction, and validates the results into typed `VisualTransferEvent`s.
- `align_clip_start_epoch(feed_events)` — recovers the clip's absolute start
  epoch from the feed so visual and scan clocks share a frame.

**After fix:** S01 produces a genuine `MATCHED`/`R10` decision with a linked
scan.

---

### 1.2 `src/tracecart/vision/events.py` — three separate correctness bugs ✅

**Bug A — timestamps were clip-relative, not absolute.**
`t_pick`/`t_bag` were taken straight from the detection's `t`
(`frame_idx / fps`) and never offset by `clip_start_epoch`. ARCHITECTURE §3
specifies visual time as `t = clip_start_epoch + frame_idx / fps`. The result
was that a visual event could never fall inside a scan's window, because the
two streams lived on different clock origins (visual ≈ 0.5 s, scan ≈ 1010 s).

**Bug B — `session_id` was hardcoded to `"unknown"`.**
`gate_pair()` requires `v.session_id == s.session_id` before it will even
consider a pair. With the visual's session pinned to `"unknown"` and the
scan's session pinned to the scenario name, **every** candidate link was
rejected with `session_mismatch`. The system could never produce a `MATCHED`
decision from disk.

**Bug C — quality metrics were read from non-existent config keys.**
`n_persons_max`, `luma_mean`, and `blur_var_min` were pulled with
`cfg.get("person_box_count", 0)`, `cfg.get("luma_mean", 128.0)` and
`cfg.get("blur_var_min", 100.0)`. None of those keys exist on `Config`, so
the calls silently returned the hardcoded fallbacks — the quality gate was
scoring invented numbers rather than measured ones.

**Fixes applied:**

- `t_pick = clip_start_epoch + d.t`, `t_bag = clip_start_epoch + d.t`.
- `extract_transfer_events(...)` gained explicit `session_id` and `clip_name`
  keyword arguments, threaded through from `run_scenario()` (scenario ID
  doubles as the session key).
- `n_persons_max` is now **counted** from the person-class detections present
  in the stream instead of being read from a phantom config key.
- `luma_mean` / `blur_var_min` now default to `0.0` (conservative: a
  zero-quality frame fails the gate and yields `ABSTAIN` rather than a
  fabricated pass) and are skipped by the gate only when genuinely unmeasured.
- `cls_votes` is now a real confidence-weighted distribution over all
  eligible classes, not a single hardcoded class.
- `store_zone` is read from the zone polygon definition instead of a
  hardcoded `"aisle04"`.

**Verified output after fix:**

```
session_id: S01
t_pick: 1010.5000
t_bag:  1011.4667
t_ref:  1011.4667
n_persons_max: 0
cls_votes: {'bottle': 1.0}
```

---

### 1.3 `src/tracecart/pipeline.py` — session key threading ✅

`run_scenario()` now passes `session_id=scenario_id` into the visual
extraction, so `gate_pair()` can match visual transfers to scans.

---

## 2. High — CI Was Red on Every Push

### 2.1 `pyproject.toml` — the package was never installable ✅

**Finding.** The build backend was Poetry, but nothing in the repo ever ran
`poetry install`. The CI workflow only did `pip install -r requirements-core.txt`,
which installs **third-party dependencies only** — never `tracecart` itself.

**Impact.** Every CLI step in `.github/workflows/ci.yml` failed:

```
$ python -m tracecart.feeds.generate
ModuleNotFoundError: No module named 'tracecart'
```

The badge on the README pointed at a permanently failing workflow.

**Fix.** Rewrote `pyproject.toml` to a standard PEP 621 / setuptools build:

- `[build-system]` → `setuptools>=68.0` + `wheel`.
- Full `[project]` table: name, version, description, authors, license,
  `readme`, `requires-python = ">=3.11"`, keywords, classifiers, project URLs.
- `[project.dependencies]` mirrors `requirements-core.txt` exactly.
- `[project.optional-dependencies]` with `vision` and `dev` extras.
- `[project.scripts]` → `tracecart` and `tracecart-feeds` console entry points.
- `[tool.setuptools] package-dir = {"" = "src"}` + package discovery.
- `[tool.pytest.ini_options] pythonpath = ["src"]`.

**Result:** `pip install -e .` now works, so `python -m tracecart.run` works
from a fresh clone with no `PYTHONPATH` juggling.

---

## 3. High — Decision Reason Codes Were Wrong

### 3.1 `src/tracecart/policy.py` — `MATCHED` decisions reported `ts_invalid` ✅

**Finding.** The R10 (accepted match) branch emitted:

```python
reason_codes=[ReasonCode.EVIDENCE_QUALITY_OK if q_pass else ReasonCode.TS_INVALID]
```

A `MATCHED` decision — the *success* state, the one a judge looks at first —
was tagged `ts_invalid`. This is exactly the symptom recorded in the earlier
audit log (`MATCHED | rule=R10 | reasons=['ts_invalid']`) and it made the
output look broken on the demo screen.

**Fix.** R10 now emits `[ReasonCode.EVIDENCE_QUALITY_OK]`. The quality gate
has already been evaluated by the time R10 is reached (R12/R13 enforce it), so
`ts_invalid` was never meaningful here.

---

### 3.2 `src/tracecart/run.py` — config was silently ignored ✅

**Finding.** The CLI constructed `cfg = Config()`, the hardcoded dataclass
defaults. `configs/policy.yaml` — the pre-registered threshold file the
project's whole "frozen configuration" claim rests on — was **never loaded**
by the CLI or the server. Tuning the YAML changed nothing.

**Fix.** `cfg = Config.from_yaml(Path("configs/policy.yaml"))`. The CLI now
honours the pre-registered parameters.

---

### 3.3 `src/tracecart/run.py` — baseline ran on a different clock ✅

**Finding.** The `--baseline` path re-extracted visual events with a
*different* `clip_start_epoch` than the main pipeline used, so TraceCart and
the baseline were scored on non-identical inputs — violating ARCHITECTURE §10
("Both baselines get the same inputs and the same scoring"). The resulting
`comparison.json` was meaningless.

**Fix.** Both paths now call the shared `align_clip_start_epoch()` +
`load_visuals_from_cache()` helpers, guaranteeing identical inputs.

---

### 3.4 `src/tracecart/run.py` — `code_commit` was always `"unversioned"` ✅

The evidence packets are advertised as cryptographically verifiable, but the
commit field was hardcoded. Added `_git_commit()` which shells out to
`git rev-parse --short HEAD` and falls back to `"unversioned"` outside a repo.

---

## 4. High — API Server Security

### 4.1 Path traversal via `run_id` ✅

**Finding.** `run_id` flows from the query string straight into
`RUNS_DIR / run_id` with no validation.

**Proof (before fix):**

```
POST /api/v1/run?run_id=../../../../tmp/evil&scenario=S01
→ 200 OK, artifacts written outside the runs directory
```

**Fix.** Added `_safe_run_id()` which requires the identifier to match
`[a-zA-Z0-9_-]+`, raising HTTP 400 otherwise. Applies to `/api/v1/run`,
`/api/v1/runs/{run_id}`, and `/api/v1/runs/{run_id}/decisions`.

### 4.2 Unsanitised `scenario_id` ✅

Added `_safe_scenario_id()` requiring `[A-Z0-9_-]{2,32}` pattern across both
REST v1 and console `/api/run` routes, rejecting injection and traversal attempts.

### 4.3 Upload filename injection ✅

`save_upload()` extracts `Path(file.filename).name`, strictly enforces `.mp4`
extension, validates genuine MP4 container magic bytes (`ftyp`), and confirms
the resolved destination path cannot escape `UPLOAD_DIR`.

### 4.4 Information disclosure in error handlers ✅

`detail=f"Processing failed: {str(e)}"` and `detail=f"Upload failed: {str(e)}"`
leaked internal exception text and absolute paths to the client (OWASP A05).
Now returns a generic message and properly re-raises `HTTPException`.

### 4.5 CORS wildcard with credentials & security headers ✅

Restricted CORS origins to an explicit whitelist (`_DEFAULT_ORIGINS` +
`TRACECART_CORS_ORIGINS` env var) and attached OWASP security headers middleware
(`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
`Content-Security-Policy`).

---

## 5. Medium — Tooling & Repo Hygiene

### 5.1 `pyproject.toml` — packaging ✅

See §2.1. Fixed setuptools build backend, package-dir, and dev/vision extras.

### 5.2 Containerization & CI ✅

Added multi-stage non-root `Dockerfile`, `docker-compose.yml`, `.dockerignore`,
`ruff.toml`, and wired `pip install -e .` + `ruff check` into `.github/workflows/ci.yml`.

### 5.3 Open-source governance ✅

Added `CONTRIBUTING.md`, `SECURITY.md`, `.github/CODEOWNERS`, and GitHub PR / issue templates.

---

## 6. Verification Performed

| Check | Command | Result |
|---|---|---|
| Full test suite | `pytest tests/ -v` | **23 passed in 4.34s** (100% green) |
| Edge-case suite | `pytest tests/test_edge_cases.py` | 4/4 passed (voided scans, qty expansion, cache malformation, deduplication) |
| Security suite | `pytest tests/test_server_security.py` | 6/6 passed (path traversal, scenario injection, upload magic bytes, security headers) |
| Feed generation | `python -m tracecart.feeds.generate` | OK |
| End-to-end CLI | `python -m tracecart.run --scenario S01 --mode cache --print --eval --baseline` | **1 `MATCHED`/`R10`** |
| Cache ingestion | `python scripts/download_test_data.py --web --run` | OK (REAL01 & REAL03 validated) |
| Path traversal | `POST /api/v1/run?run_id=../../../../tmp/evil` | **400 Bad Request** |
| Interactive Console | Browser recording via subagent | Fully captured demo walkthrough video |

---

## 7. Work Still Open

- [x] Finish server hardening (§4.2, §4.3, §4.5) and add a security-headers
      middleware.
- [x] Replace the hardcoded `/api/evaluation` numbers with values measured
      from the live scenario suite.
- [x] Expand the test suite (edge cases: voided scans, qty > 1 slot
      expansion, path-traversal regression tests, cache-malformation
      regression tests).
- [x] Add `ruff`/`black` configuration and wire lint + coverage into CI.
- [x] Add a `Dockerfile` (multi-stage, non-root) and `docker-compose.yml`.
- [x] Add `CONTRIBUTING.md`, `SECURITY.md`, issue/PR templates, `CODEOWNERS`.
- [x] Source a real public dataset, run the engine against it, and record the
      measured results.
- [x] Write the final audit report and push everything.

---

*Log maintained incrementally — each entry is written as the change lands.*
