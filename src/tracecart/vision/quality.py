"""Visual-quality metrics computation (blur/luma).

Computes frame-quality proxies for a track's spanned frames:
  - luma_mean: mean luminance (Y channel in YUV/YCrCb)
  - blur_var_min: minimum Laplacian variance over the track (sharpness proxy)

If frames unavailable, returns conservative defaults that will likely
fail the quality gate (leading to ABSTAIN) — better than pretending quality is good.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

import cv2
import numpy as np


def compute_frame_quality(
    frame: np.ndarray,
    box: Tuple[float, float, float, float],
) -> Tuple[float, float]:
    """Return (luma_mean, blur_var_min) for a detection box in an RGB frame."""
    x1, y1, x2, y2 = map(int, box)
    h, w = frame.shape[:2]
    x1 = max(0, min(x1, w-1))
    x2 = max(0, min(x2, w-1))
    y1 = max(0, min(y1, h-1))
    y2 = max(0, min(y2, h-1))
    if x2 <= x1 or y2 <= y1:
        return 0.0, 0.0

    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0, 0.0

    # Convert RGB → YCrCb, take Y channel
    ycc = cv2.cvtColor(roi, cv2.COLOR_RGB2YCrCb)
    y_channel = ycc[:, :, 0]
    luma_mean = float(y_channel.mean())

    # Blur proxy: variance of Laplacian (higher = sharper)
    gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    blur_var = float(laplacian.var())

    return luma_mean, blur_var


def track_quality_from_frames(
    frame_reader: Callable[[int], Optional[np.ndarray]],
    track_boxes: List[Tuple[float, float, float, float]],
    fps: float,
) -> Tuple[float, float]:
    """Compute (luma_mean, blur_var_min) over a track's spanned frames.

    frame_reader(frame_idx) → RGB ndarray or None if unavailable.
    track_boxes: list of (x1,y1,x2,y2) per frame in track order.
    """
    lumas: List[float] = []
    blurs: List[float] = []

    for idx, box in enumerate(track_boxes):
        frame = frame_reader(idx)
        if frame is not None:
            luma, blur = compute_frame_quality(frame, box)
            lumas.append(luma)
            blurs.append(blur)

    if not lumas:
        # No frames available → conservative defaults that will fail quality gate
        return 0.0, 0.0

    luma_mean = float(np.mean(lumas))
    blur_var_min = float(np.min(blurs)) if blurs else 0.0
    return luma_mean, blur_var_min


def track_quality_from_cache(
    cache_entries: List[dict],
) -> Tuple[float, float]:
    """Extract luma/blur from cached observations if they were saved there.

    Expects cache entries to have optional 'luma_mean' and 'blur_var_min'.
    """
    lumas = [e.get("luma_mean") for e in cache_entries if e.get("luma_mean") is not None]
    blurs = [e.get("blur_var_min") for e in cache_entries if e.get("blur_var_min") is not None]

    if not lumas:
        return 0.0, 0.0

    luma_mean = float(np.mean(lumas))
    blur_var_min = float(np.min(blurs)) if blurs else 0.0
    return luma_mean, blur_var_min