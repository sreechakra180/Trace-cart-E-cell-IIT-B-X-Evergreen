"""TraceCart command-line interface.

Usage:
  python -m tracecart.run --scenario S03 --mode cache
  python -m tracecart.run --scenario S03 --mode live   # re-runs detector
  python -m tracecart.run --print                      # table output
  make demo (which calls this under the hood)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from .pipeline import run_scenario
from .config import Config
from .schema import Decision
from .policy import cfg_hash
from .packets import write_decisions, write_packets, write_metrics, write_config_snapshot
from .eval.metrics import score, MetricsReport, score_vs_baseline


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="TraceCart: Mobile Scan & Go reconciliation engine"
    )
    p.add_argument(
        "--scenario",
        required=True,
        help="Scenario ID (e.g., S01, S03, S08)",
    )
    p.add_argument(
        "--mode",
        choices=["cache", "live"],
        default="cache",
        help="cache: use committed detector output (default)\n"
             "live:  re-run detector on video (requires torch/ultralytics)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=Path("runs/demo"),
        help="Output directory for run artifacts",
    )
    p.add_argument(
        "--print",
        action="store_true",
        help="Print decisions as a table to stdout",
    )
    p.add_argument(
        "--eval",
        action="store_true",
        help="Run evaluation against ground truth and write metrics.json",
    )
    p.add_argument(
        "--baseline",
        action="store_true",
        help="Also run timestamp-only baseline for comparison",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)

    # Load config from YAML if present, falling back to defaults
    cfg = Config.from_yaml(Path("configs/policy.yaml"))

    # Determine data files
    data_dir = Path("data")
    clip_file = data_dir / "clips" / f"{args.scenario}.mp4"
    cache_file = data_dir / "cache" / "obs" / f"obs_{args.scenario}.jsonl"
    feed_file = data_dir / "feeds" / f"feed_{args.scenario}.jsonl"

    if not feed_file.exists():
        print(f"ERROR: Feed file not found: {feed_file}", file=sys.stderr)
        print("Run 'python -m tracecart.feeds.generate' or check data setup.", file=sys.stderr)
        return 1

    # Load events from cache or run detector
    if args.mode == "cache":
        if not cache_file.exists():
            print(f"ERROR: Cache file not found: {cache_file}", file=sys.stderr)
            print("Run with --mode live first, or generate cache.", file=sys.stderr)
            return 1
        cache_path = cache_file
    else:
        # Live mode: run detector on video
        from .vision.detect_track import detect_track_clip
        print(f"Running detector on {clip_file} -> {cache_file} ...")
        detect_track_clip(str(clip_file), str(cache_file), cfg)
        cache_path = cache_file

    # Run pipeline
    print(f"Running scenario {args.scenario} in {args.mode} mode ...")
    decisions: List[Decision] = run_scenario(
        scenario_id=args.scenario,
        cache_file=cache_path,
        feed_file=feed_file,
        cfg=cfg,
    )
    print(f"Generated {len(decisions)} decisions.")

    # Ensure output dir exists
    args.out.mkdir(parents=True, exist_ok=True)

    # Write decisions.jsonl, packets, and config snapshot
    write_decisions(decisions, args.out)
    write_packets(decisions, args.out, cfg_hash(cfg), _git_commit())
    write_config_snapshot({"config": cfg.__dict__}, args.out)

    # Optional: print table
    if args.print:
        headers = ["Decision", "State", "Rule", "Reasons", "Action"]
        table = []
        for d in decisions:
            table.append([
                d.decision_id,
                d.state.value,
                d.rule_id,
                "; ".join(str(r.value) for r in d.reason_codes) or "none",
                d.recommended_action[:50] + "..."
            ])
        try:
            from tabulate import tabulate
            print(tabulate(table, headers=headers))
        except ImportError:
            col_widths = [max(len(str(row[i])) for row in ([headers] + table)) for i in range(len(headers))]
            header_str = " | ".join(f"{headers[i]:<{col_widths[i]}}" for i in range(len(headers)))
            sep_str = "-+-".join("-" * col_widths[i] for i in range(len(headers)))
            print(header_str)
            print(sep_str)
            for row in table:
                print(" | ".join(f"{str(row[i]):<{col_widths[i]}}" for i in range(len(headers))))

    # Optional: run evaluation
    if args.eval:
        print("Running evaluation against ground truth ...")
        gt = _load_ground_truth(args.scenario)  # placeholder
        metrics: MetricsReport = score(decisions, gt, cfg)
        write_metrics(metrics.to_dict(), args.out / "metrics.json")
        print(f"Metrics written to {args.out / 'metrics.json'}")

        if args.baseline:
            from .baseline import run_baseline
            from .ingest import ingest_scan_events
            from .pipeline import align_clip_start_epoch, load_visuals_from_cache
            print("Running baseline ...")
            feed_events, _ = ingest_scan_events(feed_file, cfg)
            # Same clock alignment the main pipeline used, so both engines
            # see identical inputs (ARCHITECTURE §10).
            clip_start_epoch = align_clip_start_epoch(feed_events)
            visuals = load_visuals_from_cache(cache_path, cfg, clip_start_epoch)
            baseline_decisions = run_baseline(visuals, feed_events, cfg)
            comparison = score_vs_baseline(decisions, baseline_decisions, gt, cfg)
            with open(args.out / "comparison.json", "w", encoding="utf-8") as f:
                json.dump(comparison, f, indent=2)
            print(f"Comparison written to {args.out / 'comparison.json'}")

    return 0


def _git_commit() -> str:
    """Return short git commit hash, or 'unversioned' if unavailable."""
    import subprocess
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(Path(__file__).resolve().parent.parent.parent),
            stderr=subprocess.DEVNULL,
        ).decode().strip() or "unversioned"
    except Exception:
        return "unversioned"




def _load_ground_truth(scenario_id: str) -> List[dict]:
    """Load ground truth from annotations/<scenario>.csv.

    Placeholder: returns minimal truth for demo until annotations/ is populated.
    """
    # In reality, this would read data/manifests/annotations/<scenario_id>.csv
    # and produce the dicts expected by eval.metrics.score
    return [
        {
            "v_id": f"V-{scenario_id}-T01-0",
            "expected_state": "MATCHED",
            "scanned_truth": True,
            "evidence_adequate": True,
            "expected_match_s_id": None,
        },
        {
            "v_id": f"V-{scenario_id}-T02-0",
            "expected_state": "REVIEW",
            "scanned_truth": False,
            "evidence_adequate": True,
        },
    ]


if __name__ == "__main__":
    sys.exit(main())