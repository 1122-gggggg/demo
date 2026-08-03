#!/usr/bin/env python3
"""中央場域展示版的小型共用資料契約。"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
LOCALIZATION_ROOT = Path(
    os.environ.get("LOCALIZATION_ROOT", ROOT.parent / "localization")
).expanduser().resolve()
PACKAGE_ROOT = ROOT / "定位所需資料" / "central_p1370137_edm_semantic_20260803"
ORIGINAL_VIDEO = ROOT / "P1370137.MP4"
PROCESSED_VIDEO = ROOT / "P1370137_sam3_processed.mp4"
REPLAY_DIR = ROOT / "定位回放"
POSE_CACHE = REPLAY_DIR / "central_p1370137_poses.npz"
RECEIPT = REPLAY_DIR / "central_p1370137_precompute_receipt.json"
ORIGINAL_PROXY = REPLAY_DIR / "P1370137_demo_960x540.mp4"
PROCESSED_PROXY = REPLAY_DIR / "P1370137_sam3_demo_960x540.mp4"

VIDEO_FPS = 24000.0 / 1001.0
DEMO_FRAME_COUNT = 2710
SEMANTIC_FPS = 3.0
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
CAMERA_PARAMS = (931.2057783503648, 931.2057783503648, 640.0, 360.0)

SEMANTIC_RGB = {
    1: (0, 255, 0),
    2: (255, 128, 0),
    3: (255, 255, 0),
    4: (0, 128, 255),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def camera_center(R_cw: np.ndarray, t_cw: np.ndarray) -> np.ndarray:
    rotation = np.asarray(R_cw, dtype=np.float64)
    translation = np.asarray(t_cw, dtype=np.float64)
    if rotation.shape != (3, 3) or translation.shape != (3,):
        raise ValueError("R_cw/t_cw shape mismatch")
    return -(rotation.T @ translation)


def pose_index_for_time(time_s: float, *, sample_fps: float, pose_count: int) -> int:
    if pose_count <= 0 or sample_fps <= 0:
        raise ValueError("pose_count and sample_fps must be positive")
    return int(np.clip(round(max(0.0, float(time_s)) * sample_fps), 0, pose_count - 1))


def build_display_indices(point_count: int, max_points: int) -> np.ndarray:
    if point_count <= 0 or max_points <= 0:
        raise ValueError("point_count and max_points must be positive")
    step = max(1, int(np.ceil(point_count / max_points)))
    return np.arange(0, point_count, step, dtype=np.int64)


def nearest_projected_point(
    screen_xy: np.ndarray,
    cursor_xy: tuple[float, float],
    *,
    max_distance_px: float = 45.0,
) -> int | None:
    points = np.asarray(screen_xy, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 2:
        raise ValueError("screen_xy must have shape (N, 2)")
    if not len(points):
        return None
    cursor = np.asarray(cursor_xy, dtype=np.float64)
    if cursor.shape != (2,) or max_distance_px <= 0:
        raise ValueError("cursor must be 2D and max_distance_px positive")
    distances2 = np.sum((points - cursor) ** 2, axis=1)
    index = int(np.argmin(distances2))
    return index if float(distances2[index]) <= max_distance_px**2 else None


def colorize_semantic_classes(original_rgb: np.ndarray, labels: np.ndarray) -> np.ndarray:
    original = np.asarray(original_rgb, dtype=np.uint8)
    classes = np.asarray(labels)
    if original.ndim != 2 or original.shape[1] != 3:
        raise ValueError("original_rgb must have shape (N, 3)")
    if classes.shape != (len(original),):
        raise ValueError("labels must have shape (N,)")
    colors = original.copy()
    for class_id, color in SEMANTIC_RGB.items():
        colors[classes == class_id] = color
    return colors


def progressive_colors(
    original_rgb: np.ndarray,
    semantic_rgb: np.ndarray,
    reveal_steps: np.ndarray,
    current_step: int,
) -> np.ndarray:
    original = np.asarray(original_rgb, dtype=np.uint8)
    semantic = np.asarray(semantic_rgb, dtype=np.uint8)
    reveal = np.asarray(reveal_steps)
    if original.shape != semantic.shape or original.ndim != 2 or original.shape[1] != 3:
        raise ValueError("RGB arrays must share shape (N, 3)")
    if reveal.shape != (len(original),):
        raise ValueError("reveal_steps must have shape (N,)")
    colors = original.copy()
    visible = (reveal >= 0) & (reveal <= int(current_step))
    colors[visible] = semantic[visible]
    return colors


def load_replay(path: Path = POSE_CACHE) -> dict[str, np.ndarray | float]:
    with np.load(path, allow_pickle=False) as artifact:
        required = {
            "times_s", "R_cw", "t_cw", "centers", "valid_edm", "pose_source",
            "inliers", "reproj_rms", "states", "reveal_steps", "sample_fps",
        }
        missing = sorted(required - set(artifact.files))
        if missing:
            raise ValueError(f"pose cache missing arrays: {', '.join(missing)}")
        result = {name: artifact[name] for name in required}
    count = len(result["times_s"])
    if count <= 0:
        raise ValueError("pose cache is empty")
    if np.asarray(result["R_cw"]).shape != (count, 3, 3):
        raise ValueError("R_cw shape mismatch")
    if np.asarray(result["t_cw"]).shape != (count, 3):
        raise ValueError("t_cw shape mismatch")
    if np.asarray(result["centers"]).shape != (count, 3):
        raise ValueError("centers shape mismatch")
    if float(np.asarray(result["sample_fps"]).item()) <= 0:
        raise ValueError("sample_fps must be positive")
    return result
