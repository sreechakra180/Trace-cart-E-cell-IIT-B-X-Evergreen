"""Debug render: overlay zone polygons on a frame.

Critical: wrong zones are the most likely silent bug (RISK-005 in Risk Register).
A debug render must overlay them so the human can verify before running tracking.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np


@dataclass
class DebugRender:
    frame: np.ndarray  # RGB uint8
    zones: List[Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int], Tuple[int, int]]]
    overlay_color: Tuple[int, int, int] = (0, 255, 0)  # BGR in OpenCV
    line_thickness: int = 3

    def render(self) -> np.ndarray:
        """Return frame with zone polygons drawn."""
        out = self.frame.copy()
        for poly in self.zones:
            # poly: ((x1,y1), (x2,y2), ..., (xn,yn)) in pixel coords
            pts = np.array(poly, dtype=np.int32).reshape(-1, 1, 2)
            cv2.polylines(out, [pts], isClosed=True, color=self.overlay_color, thickness=self.line_thickness)
            # Label first vertex
            if poly:
                cv2.putText(out, zone_name_from_poly(poly[0]), (poly[0][0] + 5, poly[0][1] - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        return out


def zone_name_from_poly(pt: Tuple[int, int]) -> str:
    return "zone"  # placeholder; real label from config


def overlay_frames(
    frame_rgb: np.ndarray,
    zones: List[dict],
    overlay_color: Tuple[int, int, int] = (0, 255, 0),
) -> np.ndarray:
    """Produce a debug frame with zone polygons overlaid.

    zones: list of dicts with "polygon" key, polygon = [(x,y), ...]
    """
    out = frame_rgb.copy()
    for z in zones:
        poly = z.get("polygon", [])
        if len(poly) >= 3:
            pts = np.array(poly, dtype=np.int32).reshape(-1, 1, 2)
            cv2.polylines(out, [pts], isClosed=True, color=overlay_color, thickness=3)
    return out