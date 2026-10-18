"""Evidence packet JSON writer.

Mechanism D minimal from ARCHITECTURE §121:
  Packet = decision + candidates + terms + rule_id + warnings + thresholds hash

Packets are written to a run directory, one JSON file per decision.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from .schema import Decision, DecisionState
from .policy import cfg_hash


def write_packets(
    decisions: List[Decision],
    run_dir: str | Path,
    config_hash: str,
    code_commit: str,
) -> None:
    """Write evidence packets to run_dir/packets/<decision_id>.json."""
    run_dir = Path(run_dir)
    packets_dir = run_dir / "packets"
    packets_dir.mkdir(parents=True, exist_ok=True)

    for d in decisions:
        # Ensure config_hash and code_commit are up to date
        packet = d.model_dump(exclude_none=True)
        packet["config_hash"] = config_hash
        packet["code_commit"] = code_commit

        # Ensure JSON-serializable
        for key in ("timing", "visual", "association", "evidence_quality"):
            if key in packet and hasattr(packet[key], "model_dump"):
                packet[key] = packet[key].model_dump(exclude_none=True)

        # Write to file
        out_path = packets_dir / f"{d.decision_id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(packet, f, indent=2)


def write_decisions(decisions: List[Decision], run_dir: str | Path) -> None:
    """Write decisions.jsonl to run_dir."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    decisions_path = run_dir / "decisions.jsonl"
    with open(decisions_path, "w", encoding="utf-8") as f:
        for d in decisions:
            f.write(json.dumps(d.model_dump(exclude_none=True)) + "\n")


def write_metrics(metrics: dict, run_dir_or_file: str | Path) -> None:
    """Write metrics.json to run_dir or target file."""
    p = Path(run_dir_or_file)
    if p.suffix == ".json":
        p.parent.mkdir(parents=True, exist_ok=True)
        metrics_path = p
    else:
        p.mkdir(parents=True, exist_ok=True)
        metrics_path = p / "metrics.json"

    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)


def write_config_snapshot(cfg_dict: dict, run_dir: str | Path) -> None:
    """Write config_snapshot.yaml to run_dir."""
    import yaml
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    config_path = run_dir / "config_snapshot.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(cfg_dict, f, sort_keys=False)