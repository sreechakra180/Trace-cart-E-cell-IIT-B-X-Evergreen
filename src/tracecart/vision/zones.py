"""Zone configuration and point-in-polygon checks.

Zones are polygons in pixel coordinates (loaded from configs/zones.yaml).
A debug overlay must draw them (render.py) because wrong zones are the most
likely silent bug.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import yaml


@dataclass
class Zone:
    name: str
    polygon: List[Tuple[float, float]]  # pixel coords, clockwise or CCW
    store_zone: Optional[str] = None  # logical zone name for matching

    def contains(self, x: float, y: float) -> bool:
        """Point-in-polygon (ray casting)."""
        poly = self.polygon
        n = len(poly)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = poly[i]
            xj, yj = poly[j]
            if ((yi > y) != (yj > y)) and (
                x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi
            ):
                inside = not inside
            j = i
        return inside

    def box_center_inside(self, box) -> bool:
        """Check if a detection box center is inside this zone.

        box is (x1, y1, x2, y2) or [x1, y1, x2, y2].
        """
        x1, y1, x2, y2 = box
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        return self.contains(cx, cy)


def load_zones(path: str | Path = "configs/zones.yaml") -> Dict[str, Zone]:
    """Load zone definitions from YAML."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    zones: Dict[str, Zone] = {}
    for name, spec in data.get("zones", {}).items():
        polygon = [(float(x), float(y)) for x, y in spec.get("polygon", [])]
        zones[name] = Zone(
            name=name,
            polygon=polygon,
            store_zone=spec.get("store_zone", name),
        )
    return zones


def zone_for_point(zones: Dict[str, Zone], x: float, y: float) -> Optional[str]:
    """Return the name of the first zone containing the point."""
    for name, zone in zones.items():
        if zone.contains(x, y):
            return name
    return None


def box_center_in_zones(zones: Dict[str, Zone], box) -> List[str]:
    """Return list of zone names whose polygon contains the box center."""
    x1, y1, x2, y2 = box
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    return [name for name, zone in zones.items() if zone.contains(cx, cy)]