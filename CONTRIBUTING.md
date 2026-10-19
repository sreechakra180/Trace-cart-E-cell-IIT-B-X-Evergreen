# Contributing to TraceCart

Thank you for your interest in contributing to TraceCart! This project is an evidence-first vision AI reconciliation engine for retail scan & go, developed for the E-Cell IIT Bombay × Everseen Retail Loss Prevention Challenge.

---

## Code of Conduct & Core Principles

1. **Truth in Engineering**: Never report simulated or hardcoded metrics as measured. Every reported latency, recall, or precision figure must be computed directly by the scorer.
2. **Zero Biometrics Guarantee**: TraceCart processes bounding geometry and product classes only. Do not introduce facial recognition, person re-identification, or persistent biometric tracking embeddings.
3. **Deterministic State Machine**: `pipeline.run(visuals, feed, cfg)` must remain a pure function given typed events.

---

## Development Setup

### 1. Clone & Virtual Environment

```bash
git clone https://github.com/sreechakra180/Trace-cart-E-cell-IIT-B-X-Evergreen.git
cd Trace-cart-E-cell-IIT-B-X-Evergreen
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install --upgrade pip
pip install -e ".[dev]"
```

### 3. Generate Scenario Feeds & Run Test Suite

```bash
# Generate deterministic test feeds
python -m tracecart.feeds.generate

# Run full test suite (23 tests)
pytest tests/ -v
```

### 4. Code Formatting & Linting

We enforce linting using `ruff`:

```bash
ruff check src/ tests/ app/
ruff format --check src/ tests/ app/
```

---

## Submitting Pull Requests

1. Create a feature branch: `git checkout -b feat/your-feature-name`
2. Ensure all 23 tests pass: `pytest tests/ -v`
3. Verify CLI end-to-end: `python -m tracecart.run --scenario S01 --mode cache --print`
4. Commit your changes with clear, descriptive commit messages.
5. Submit a Pull Request targeting `main`.
