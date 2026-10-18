"""Vision front end: decode → zones → detect+track → transfer events → quality."""

from .decode import decode_video
from .zones import load_zones, Zone
from .events import extract_transfer_events, Detection, Track
from .quality import compute_frame_quality, track_quality_from_frames, track_quality_from_cache

__all__ = [
    "decode_video",
    "load_zones",
    "Zone",
    "extract_transfer_events",
    "Detection",
    "Track",
    "compute_frame_quality",
    "track_quality_from_frames",
    "track_quality_from_cache",
]