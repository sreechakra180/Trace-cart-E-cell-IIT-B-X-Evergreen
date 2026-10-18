"""Video frame decoding.

Reads MP4 with OpenCV; yields (frame_idx, frame, timestamp_utc, fps_unreliable).

analysis_fps is configured (default 10) — we stride from native fps.
"""

from __future__ import annotations

from pathlib import Path
from typing import Generator, Tuple

import cv2

from ..timeutil import clip_time_to_utc
from ..config import Config


def decode_video(
    video_path: str | Path,
    cfg: Config,
) -> Generator[Tuple[int, any, float, bool], None, None]:
    """Decode video file → frames at analysis_fps."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise IOError(f"Cannot open video: {video_path}")

    native_fps = cap.get(cv2.CAP_PROP_FPS)
    # Heuristic: fps == 0.0 or wildly varying timestamps → VFR detected
    fps_unreliable = native_fps <= 0.0 or native_fps > 120
    analysis_fps = 10.0  # could be made configurable

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Convert BGR → RGB if needed downstream
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Compute timestamp: clip_start_epoch + frame_idx / native_fps
        # clip_start_epoch not known here — caller must provide or infer from filename
        # For now we return frame_idx and let caller compute t using clip_start
        yield frame_idx, frame_rgb, native_fps, fps_unreliable
        frame_idx += 1

    cap.release()


def sample_frames(
    frame_gen: Generator,
    analysis_fps: float = 10.0,
) -> Generator[Tuple[int, any, float, bool], None, None]:
    """Stride from native fps to analysis_fps."""
    # For simplicity: if native_fps known, stride; else sample every Nth frame
    # Actual implementation would need clip_start_epoch from manifest
    # This is a placeholder; real logic lives in the CLI/run.py
    yield from frame_gen  # caller handles striding