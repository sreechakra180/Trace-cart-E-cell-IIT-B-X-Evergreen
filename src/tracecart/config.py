"""Configuration loading and validation.

YAML files (configs/*.yaml) with pre-registration hashes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class Config:
    """Runtime configuration loaded from YAML."""
    # Quality gate thresholds
    det_conf_min: float = 0.45
    track_continuity_min: float = 0.70
    gap_max_s_max: float = 1.0
    n_frames_min: int = 8
    n_persons_max: int = 1
    luma_min: float = 40.0
    luma_max: float = 220.0
    blur_var_min: float = 50.0

    # Association weights (λ_T, λ_Z, λ_S, λ_F)
    lambda_t: float = 0.50
    lambda_z: float = 0.15
    lambda_s: float = 0.25
    lambda_f: float = 0.10

    # Association thresholds
    tau_match: float = 0.50
    w_gate: float = 10.0
    delta_amb: float = 0.10
    w_norm: float = 10.0
    zone_strict: bool = False

    # Policy/timing
    grace_s: float = 20.0
    min_dt: float = 0.3
    max_dt: float = 15.0
    min_track_frames: int = 8
    confidence_min: float = 0.25
    fps_assumed: float = 30.0

    # Classes
    eligible_classes: List[str] = field(default_factory=lambda: [
        "bottle", "cup", "apple", "orange", "banana", "bowl", "cell phone"
    ])
    person_class: str = "person"

    # SKU map: SKU → COCO class (loaded from YAML)
    sku_to_class: Dict[str, str] = field(default_factory=dict)

    # Paths
    zones_yaml: Path = field(default_factory=lambda: Path("configs/zones.yaml"))
    skumap_yaml: Path = field(default_factory=lambda: Path("configs/skumap.yaml"))
    cache_dir: Path = field(default_factory=lambda: Path("data/cache/obs"))

    def get(self, key: str, default: Any = None) -> Any:
        """Allow dictionary-like .get() access on configuration."""
        return getattr(self, key, default)

    @classmethod
    def from_yaml(cls, path: Path | str = "configs/policy.yaml") -> "Config":
        """Load configuration from YAML file."""
        p = Path(path)
        if not p.exists():
            return cls()
        with open(p, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # Map yaml keys to Config attributes
        cfg = cls()
        for key, value in data.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
        return cfg

