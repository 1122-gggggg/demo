#!/usr/bin/env python3
"""中央場域：雙影片、預算定位與累積語意點雲展示介面。"""
from __future__ import annotations

import math
import os
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageTk

from 展示核心 import (
    ORIGINAL_PROXY,
    PACKAGE_ROOT,
    POSE_CACHE,
    PROCESSED_PROXY,
    SEMANTIC_RGB,
    VIDEO_FPS,
    build_display_indices,
    colorize_semantic_classes,
    load_replay,
    nearest_projected_point,
    pose_index_for_time,
)


SEMANTIC_NPZ = PACKAGE_ROOT / "semantic" / "semantic_map.npz"
WINDOWS_FONTS = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
FONT_PATHS = {
    False: (
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        WINDOWS_FONTS / "msjh.ttc",
        WINDOWS_FONTS / "mingliu.ttc",
    ),
    True: (
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
        WINDOWS_FONTS / "msjhbd.ttc",
        WINDOWS_FONTS / "msjh.ttc",
    ),
}
INTERACTIVE_POINTS = 180_000
MAP_REFRESH_STRIDE = 2
SEMANTIC_POINT_RADIUS = 0
SEMANTIC_COLOR_ALPHA = 0.65
EOF_HOLD_MS = 500
RESET_HOLD_MS = 250


def should_redraw_map(frame_index: int, pose_index: int, pose_count: int) -> bool:
    if pose_count <= 0:
        raise ValueError("pose_count must be positive")
    return frame_index % MAP_REFRESH_STRIDE == 0 or pose_index == pose_count - 1


def pil_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    for font_path in FONT_PATHS[bold]:
        if font_path.is_file():
            return ImageFont.truetype(str(font_path), size=size)
    return ImageFont.load_default()


def camera_frustum_world_points(
    center: np.ndarray,
    axes: np.ndarray,
    *,
    length: float,
    hfov_deg: float = 72.0,
    aspect_ratio: float = 16.0 / 9.0,
) -> np.ndarray:
    center = np.asarray(center, dtype=np.float64)
    axes = np.asarray(axes, dtype=np.float64)
    if center.shape != (3,) or axes.shape != (3, 3):
        raise ValueError("camera center/axes shape mismatch")
    right, down, forward = axes
    face_center = center + forward * length
    half_width = length * math.tan(math.radians(hfov_deg) * 0.5)
    half_height = half_width / aspect_ratio
    corners = np.asarray([
        face_center - right * half_width - down * half_height,
        face_center + right * half_width - down * half_height,
        face_center + right * half_width + down * half_height,
        face_center - right * half_width + down * half_height,
    ])
    return np.vstack([center, face_center, corners])


class CentralDemo(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("EDM + MegaLoc 展示系統")
        self.geometry("1600x900")
        self.minsize(1180, 700)
        self.configure(bg="#111316")

        self.replay = load_replay()
        self.sample_fps = float(np.asarray(self.replay["sample_fps"]).item())
        with np.load(SEMANTIC_NPZ, allow_pickle=False) as semantic:
            self.all_points = np.asarray(semantic["points_world"], dtype=np.float32)
            self.all_original_rgb = np.asarray(semantic["original_rgb"], dtype=np.uint8)
            self.all_labels = np.asarray(semantic["final_classes"], dtype=np.int16)
        self.all_semantic_rgb = colorize_semantic_classes(
            self.all_original_rgb, self.all_labels
        )
        reveal = np.asarray(self.replay["reveal_steps"], dtype=np.int16)
        if reveal.shape != (len(self.all_points),):
            raise ValueError("reveal schedule does not match the semantic point map")

        self.interactive_indices = build_display_indices(len(self.all_points), INTERACTIVE_POINTS)
        self.display_indices: np.ndarray | None = None
        self.map_points = self.all_points
        self.original_rgb = self.all_original_rgb
        self.semantic_rgb = self.all_semantic_rgb
        self.labels = self.all_labels
        self.reveal_steps = reveal
        lo = self.all_points.min(axis=0).astype(np.float64)
        hi = self.all_points.max(axis=0).astype(np.float64)
        self.map_center = np.median(self.all_points, axis=0).astype(np.float64)
        self.default_center = self.map_center.copy()
        self.map_radius = max(1.0, float(np.max(hi - lo) * 0.5))
        self.map_yaw = 0.0
        self.map_pitch = (math.radians(78.0) + math.pi) % (2.0 * math.pi)
        self.map_roll = 0.0
        self.map_zoom = 1.0
        self.map_pan = np.asarray((-55.0, -55.0), dtype=np.float64)
        self.drag_button: int | None = None
        self.drag_last: tuple[int, int] | None = None
        self.interacting = False
        self.zoom_restore_job: str | None = None

        self.pose_step = -1
        self.frame_index = -1
        self.loop_count = 0
        self.playing = False
        self.next_deadline = time.monotonic()
        self.map_photo = None
        self.original_photo = None
        self.processed_photo = None
        self.map_render_key = None
        self.map_projection_key = None
        self.map_projection_cache = None
        self.original_cap = self._open_video(ORIGINAL_PROXY)
        self.processed_cap = self._open_video(PROCESSED_PROXY)
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(100, self._show_initial_state)

    @staticmethod
    def _open_video(path: Path) -> cv2.VideoCapture:
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            raise RuntimeError(f"cannot open demo video: {path}")
        return capture

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#111316")
        style.configure("Panel.TFrame", background="#1a1d21")

        controls = tk.Frame(self, bg="#111316")
        controls.pack(fill="x", padx=18, pady=(12, 8))
        self.start_button = tk.Button(
            controls,
            text="開始自動巡檢",
            command=self.start,
            bg="#1f6f55",
            activebackground="#2b8a6b",
            fg="#ffffff",
            activeforeground="#ffffff",
            disabledforeground="#a7b0b8",
            bd=0,
            padx=24,
            pady=8,
            font=("Noto Sans CJK TC", 12, "bold"),
            cursor="hand2",
        )
        self.start_button.pack()

        main = ttk.Frame(self)
        main.columnconfigure(0, weight=11)
        main.columnconfigure(1, weight=9)
        main.rowconfigure(0, weight=1)

        map_panel = tk.Frame(main, bg="#1a1d21", highlightbackground="#30363d", highlightthickness=1)
        map_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        map_panel.rowconfigure(1, weight=1)
        map_panel.columnconfigure(0, weight=1)
        self._panel_title(map_panel, "3D 語意點雲 · 已觀測區域累積", 0)
        self.map_canvas = tk.Canvas(map_panel, bg="#15181c", bd=0, highlightthickness=0)
        self.map_canvas.grid(row=1, column=0, sticky="nsew")
        self.map_canvas.bind("<ButtonPress-1>", self.on_map_press)
        self.map_canvas.bind("<B1-Motion>", self.on_map_drag)
        self.map_canvas.bind("<ButtonRelease-1>", self.on_map_release)
        self.map_canvas.bind("<ButtonPress-2>", self.on_map_press)
        self.map_canvas.bind("<B2-Motion>", self.on_map_drag)
        self.map_canvas.bind("<ButtonRelease-2>", self.on_map_release)
        self.map_canvas.bind("<ButtonPress-3>", self.on_map_press)
        self.map_canvas.bind("<B3-Motion>", self.on_map_drag)
        self.map_canvas.bind("<ButtonRelease-3>", self.on_map_release)
        self.map_canvas.bind("<MouseWheel>", self.on_map_wheel)
        self.map_canvas.bind("<Button-4>", self.on_map_wheel)
        self.map_canvas.bind("<Button-5>", self.on_map_wheel)
        self.map_canvas.bind("<Double-Button-1>", self.set_rotation_pivot)
        self.map_canvas.bind("<Configure>", lambda _event: self.redraw_map())

        video_column = ttk.Frame(main)
        video_column.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        video_column.columnconfigure(0, weight=1)
        video_column.rowconfigure(0, weight=1)
        video_column.rowconfigure(1, weight=1)
        self.original_canvas = self._video_panel(video_column, 0, "即時串流影像")
        self.processed_canvas = self._video_panel(video_column, 1, "即時標注後串流影像")

        main.pack(fill="both", expand=True, padx=18, pady=(0, 14))

    @staticmethod
    def _panel_title(parent: tk.Widget, text: str, row: int) -> None:
        tk.Label(
            parent, text=text, bg="#1a1d21", fg="#f0f3f5",
            font=("Noto Sans CJK TC", 11, "bold"), anchor="w", padx=12, pady=7,
        ).grid(row=row, column=0, sticky="ew")

    def _video_panel(self, parent: ttk.Frame, row: int, title: str) -> tk.Canvas:
        panel = tk.Frame(parent, bg="#1a1d21", highlightbackground="#30363d", highlightthickness=1)
        panel.grid(row=row, column=0, sticky="nsew", pady=((0, 6) if row == 0 else (6, 0)))
        panel.rowconfigure(1, weight=1)
        panel.columnconfigure(0, weight=1)
        self._panel_title(panel, title, 0)
        canvas = tk.Canvas(panel, bg="#08090b", bd=0, highlightthickness=0)
        canvas.grid(row=1, column=0, sticky="nsew")
        return canvas

    def start(self) -> None:
        if self.playing:
            return
        self.playing = True
        self.start_button.configure(text="自動巡檢中", state="disabled")
        self.next_deadline = time.monotonic()
        self.tick()

    def _show_initial_state(self) -> None:
        if self.playing:
            return
        self._render_original_map()
        ok_original, original = self.original_cap.read()
        ok_processed, processed = self.processed_cap.read()
        if not ok_original or not ok_processed:
            raise RuntimeError("cannot decode the first demo frame")
        self._render_video(self.original_canvas, original, "original_photo", 0.0)
        self._render_video(self.processed_canvas, processed, "processed_photo", 0.0)
        self.original_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self.processed_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    def _reset_loop(self) -> None:
        self.original_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self.processed_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self.frame_index = -1
        self.pose_step = -1
        self.loop_count += 1
        self.map_render_key = None
        self.next_deadline = time.monotonic() + 0.25
        self._render_original_map()

    def tick(self) -> None:
        if not self.playing:
            return
        ok_original, original = self.original_cap.read()
        ok_processed, processed = self.processed_cap.read()
        if not ok_original or not ok_processed:
            self.after(EOF_HOLD_MS, self._restart_loop)
            return
        self.frame_index += 1
        time_s = self.frame_index / VIDEO_FPS
        next_pose = pose_index_for_time(
            time_s, sample_fps=self.sample_fps, pose_count=len(self.replay["times_s"])
        )
        self._render_video(self.original_canvas, original, "original_photo", time_s)
        self._render_video(self.processed_canvas, processed, "processed_photo", time_s)
        if next_pose != self.pose_step:
            self.pose_step = next_pose
            if should_redraw_map(
                self.frame_index, next_pose, len(self.replay["times_s"])
            ):
                self.redraw_map()
        self.next_deadline += 1.0 / VIDEO_FPS
        now = time.monotonic()
        if now - self.next_deadline > 0.3:
            self.next_deadline = now
        self.after(max(1, int((self.next_deadline - now) * 1000.0)), self.tick)

    def _restart_loop(self) -> None:
        self._reset_loop()
        self.after(RESET_HOLD_MS, self.tick)

    def _render_video(self, canvas: tk.Canvas, frame_bgr: np.ndarray, photo_attr: str, time_s: float) -> None:
        width = max(320, canvas.winfo_width())
        height = max(180, canvas.winfo_height())
        source_h, source_w = frame_bgr.shape[:2]
        scale = min(width / source_w, height / source_h)
        target = (max(1, int(source_w * scale)), max(1, int(source_h * scale)))
        resized = cv2.resize(frame_bgr, target, interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        image = Image.new("RGB", (width, height), "#08090b")
        image.paste(Image.fromarray(rgb), ((width - target[0]) // 2, (height - target[1]) // 2))
        draw = ImageDraw.Draw(image)
        draw.rectangle((10, 10, 138, 38), fill="#0b0c0e")
        draw.text((18, 15), f"{time_s:06.2f}s  ·  LOOP {self.loop_count + 1}", fill="#f0f3f5", font=pil_font(13))
        self._present(canvas, photo_attr, image)

    def transform_xyz(self, xyz: np.ndarray) -> np.ndarray:
        points = np.asarray(xyz, dtype=np.float64).reshape(-1, 3) - self.map_center
        cy, sy = math.cos(self.map_yaw), math.sin(self.map_yaw)
        cp, sp = math.cos(self.map_pitch), math.sin(self.map_pitch)
        cr, sr = math.cos(self.map_roll), math.sin(self.map_roll)
        x1 = cy * points[:, 0] + sy * points[:, 2]
        z1 = -sy * points[:, 0] + cy * points[:, 2]
        y1 = points[:, 1]
        y2 = cp * y1 - sp * z1
        z2 = sp * y1 + cp * z1
        x3 = cr * x1 - sr * y2
        y3 = sr * x1 + cr * y2
        return np.stack((x3, y3, z2), axis=1)

    def project_world(self, xyz: np.ndarray, width: int, height: int) -> tuple[int, int]:
        view = self.transform_xyz(np.asarray(xyz).reshape(1, 3))[0]
        scale = min(width, height) * 0.46 * self.map_zoom / self.map_radius
        return (
            int(width * 0.5 + self.map_pan[0] + view[0] * scale),
            int(height * 0.5 + self.map_pan[1] - view[1] * scale),
        )

    def _select_map_detail(self) -> None:
        indices = self.interactive_indices if self.interacting else None
        if indices is self.display_indices:
            return
        self.display_indices = indices
        if indices is None:
            self.map_points = self.all_points
            self.original_rgb = self.all_original_rgb
            self.semantic_rgb = self.all_semantic_rgb
            self.labels = self.all_labels
            self.reveal_steps = np.asarray(self.replay["reveal_steps"], dtype=np.int16)
        else:
            self.map_points = self.all_points[indices]
            self.original_rgb = self.all_original_rgb[indices]
            self.semantic_rgb = self.all_semantic_rgb[indices]
            self.labels = self.all_labels[indices]
            self.reveal_steps = np.asarray(self.replay["reveal_steps"], dtype=np.int16)[indices]
        self.map_projection_key = None
        self.map_projection_cache = None

    def redraw_map(self) -> None:
        if not hasattr(self, "map_canvas"):
            return
        self._select_map_detail()
        width = max(420, self.map_canvas.winfo_width())
        height = max(360, self.map_canvas.winfo_height())
        key = (
            width, height, self.pose_step, self.interacting,
            round(self.map_yaw, 4), round(self.map_pitch, 4), round(self.map_roll, 4),
            round(self.map_zoom, 4), tuple(np.round(self.map_pan, 1)),
            tuple(np.round(self.map_center, 5)),
        )
        if key == self.map_render_key:
            return
        self.map_render_key = key
        image = self.render_map(width, height)
        self._present(self.map_canvas, "map_photo", image)

    def _render_original_map(self) -> None:
        self.pose_step = -1
        self.map_render_key = None
        self.redraw_map()

    def render_map(self, width: int, height: int) -> Image.Image:
        projection_key = (
            width, height, id(self.display_indices),
            round(self.map_yaw, 4), round(self.map_pitch, 4), round(self.map_roll, 4),
            round(self.map_zoom, 4), tuple(np.round(self.map_pan, 1)),
            tuple(np.round(self.map_center, 5)),
        )
        if projection_key != self.map_projection_key:
            view = self.transform_xyz(self.map_points)
            scale = min(width, height) * 0.46 * self.map_zoom / self.map_radius
            sx = (width * 0.5 + self.map_pan[0] + view[:, 0] * scale).astype(np.int32)
            sy = (height * 0.5 + self.map_pan[1] - view[:, 1] * scale).astype(np.int32)
            inside = (sx >= 0) & (sx < width) & (sy >= 0) & (sy < height)
            ordered_indices = np.flatnonzero(inside)
            ordered_indices = ordered_indices[np.argsort(view[ordered_indices, 2])]
            ordered_pixels = sy[ordered_indices] * width + sx[ordered_indices]
            _, reverse_positions = np.unique(ordered_pixels[::-1], return_index=True)
            winner_positions = len(ordered_indices) - 1 - reverse_positions
            winner_indices = ordered_indices[winner_positions]
            base = np.empty((height, width, 3), dtype=np.uint8)
            base[:] = (0x15, 0x18, 0x1C)
            base[sy[winner_indices], sx[winner_indices]] = self.original_rgb[winner_indices]
            self.map_projection_key = projection_key
            self.map_projection_cache = (sx, sy, ordered_indices, winner_indices, base)
        assert self.map_projection_cache is not None
        sx, sy, ordered_indices, _winner_indices, base = self.map_projection_cache
        array = base.copy()

        # Draw revealed semantic points after the original map. Otherwise dense
        # 1-pixel projections can overwrite the semantic color at the same pixel.
        revealed = (
            (self.reveal_steps[ordered_indices] >= 0)
            & (self.reveal_steps[ordered_indices] <= self.pose_step)
        )
        semantic_indices = ordered_indices[revealed]
        semantic_x = sx[semantic_indices]
        semantic_y = sy[semantic_indices]
        semantic_colors = np.rint(
            SEMANTIC_COLOR_ALPHA * self.semantic_rgb[semantic_indices]
            + (1.0 - SEMANTIC_COLOR_ALPHA) * self.original_rgb[semantic_indices]
        ).astype(np.uint8)
        for offset_y in range(-SEMANTIC_POINT_RADIUS, SEMANTIC_POINT_RADIUS + 1):
            target_y = semantic_y + offset_y
            valid_y = (target_y >= 0) & (target_y < height)
            for offset_x in range(-SEMANTIC_POINT_RADIUS, SEMANTIC_POINT_RADIUS + 1):
                target_x = semantic_x + offset_x
                valid = valid_y & (target_x >= 0) & (target_x < width)
                array[target_y[valid], target_x[valid]] = semantic_colors[valid]
        image = Image.fromarray(array, "RGB")
        draw = ImageDraw.Draw(image)
        font = pil_font(13)
        bold = pil_font(14, bold=True)

        axis_len = self.map_radius * 0.16
        origin = self.map_center
        ox, oy = self.project_world(origin, width, height)
        for endpoint, color, label in (
            (origin + [axis_len, 0, 0], "#ff6b5f", "X"),
            (origin + [0, -axis_len, 0], "#3fbf7f", "UP"),
            (origin + [0, 0, axis_len], "#5aa7e8", "Z"),
        ):
            ex, ey = self.project_world(np.asarray(endpoint), width, height)
            draw.line((ox, oy, ex, ey), fill=color, width=2)
            draw.text((ex + 4, ey + 2), label, fill=color, font=bold)
        draw.ellipse((ox - 7, oy - 7, ox + 7, oy + 7), outline="#e6b94f", width=2)

        if self.pose_step >= 0:
            centers = np.asarray(self.replay["centers"][: self.pose_step + 1])
            if len(centers) > 1:
                projected = [self.project_world(point, width, height) for point in centers]
                draw.line(projected, fill="#5aa7e8", width=3, joint="curve")
            center = np.asarray(self.replay["centers"][self.pose_step], dtype=np.float64)
            axes = np.asarray(self.replay["R_cw"][self.pose_step], dtype=np.float64)
            frustum = camera_frustum_world_points(
                center, axes, length=self.map_radius * (0.025 / 3.0)
            )
            projected = [self.project_world(point, width, height) for point in frustum]
            apex, face_center, *face = projected
            for corner in face:
                draw.line((*apex, *corner), fill="#00d4ff", width=2)
            draw.polygon(face, fill="#007f99")
            draw.line(face + [face[0]], fill="#d8fbff", width=2)
            draw.line((*apex, *face_center), fill="#ffffff", width=2)

        draw.rectangle((8, 8, min(width - 8, 650), 90), fill="#0b0c0e")
        draw.text(
            (16, 14),
            "左鍵360°旋轉 · 雙擊切換地圖中心 · 右鍵平移 · 滾輪縮放",
            fill="#f0f3f5", font=font,
        )
        status = "原始點雲" if self.pose_step < 0 else f"累積觀測節點 {self.pose_step + 1}/{len(self.replay['times_s'])}"
        draw.text((16, 36), status, fill="#8ef0c5", font=bold)
        draw.text((16, 60), "青色四角錐 = 目前相機位姿 · 藍線 = 已回放軌跡", fill="#a7b0b8", font=font)

        legend_x = max(10, width - 215)
        draw.rectangle((legend_x - 8, 8, width - 8, 132), fill="#0b0c0e")
        draw.text((legend_x, 14), "已觀測語意", fill="#f0f3f5", font=bold)
        for row, (class_id, name) in enumerate(((1, "樹葉"), (2, "電線"), (3, "變壓器"), (4, "電線桿"))):
            y = 40 + row * 21
            color = SEMANTIC_RGB[class_id]
            draw.rectangle((legend_x, y, legend_x + 14, y + 14), fill=color)
            draw.text((legend_x + 22, y - 2), name, fill="#d8dee4", font=font)
        return image

    @staticmethod
    def _present(canvas: tk.Canvas, photo_attr: str, image: Image.Image) -> None:
        app = canvas.winfo_toplevel()
        photo = getattr(app, photo_attr, None)
        if photo is not None and (photo.width(), photo.height()) == image.size:
            photo.paste(image)
            return
        photo = ImageTk.PhotoImage(image)
        setattr(app, photo_attr, photo)
        canvas.delete("frame")
        canvas.create_image(0, 0, image=photo, anchor="nw", tags="frame")

    def on_map_press(self, event) -> None:
        if self.zoom_restore_job is not None:
            self.after_cancel(self.zoom_restore_job)
            self.zoom_restore_job = None
        self.drag_button = int(event.num)
        self.drag_last = (int(event.x), int(event.y))
        self.interacting = True

    def on_map_drag(self, event) -> None:
        if self.drag_last is None:
            return
        x, y = int(event.x), int(event.y)
        dx, dy = x - self.drag_last[0], y - self.drag_last[1]
        self.drag_last = (x, y)
        if self.drag_button == 1:
            self.map_yaw -= dx * 0.008
            self.map_pitch = (self.map_pitch + dy * 0.008) % (2.0 * math.pi)
        elif self.drag_button == 2:
            self.map_roll = (self.map_roll + dx * 0.008) % (2.0 * math.pi)
        elif self.drag_button == 3:
            self.map_pan += (dx, dy)
        self.map_render_key = None
        self.redraw_map()

    def on_map_release(self, _event) -> None:
        self.drag_button = None
        self.drag_last = None
        self.interacting = False
        self.map_render_key = None
        self.redraw_map()

    def on_map_wheel(self, event) -> None:
        if self.zoom_restore_job is not None:
            self.after_cancel(self.zoom_restore_job)
        self.interacting = True
        factor = 1.12 if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0 else 1.0 / 1.12
        self.map_zoom = float(np.clip(self.map_zoom * factor, 0.08, 30.0))
        self.map_render_key = None
        self.redraw_map()
        self.zoom_restore_job = self.after(180, self._finish_zoom)

    def _finish_zoom(self) -> None:
        self.zoom_restore_job = None
        if self.drag_button is not None:
            return
        self.interacting = False
        self.map_render_key = None
        self.redraw_map()

    def set_rotation_pivot(self, event) -> None:
        if self.map_projection_cache is None:
            self.map_render_key = None
            self.redraw_map()
        assert self.map_projection_cache is not None
        sx, sy, _ordered_indices, winner_indices, _base = self.map_projection_cache
        local = nearest_projected_point(
            np.column_stack((sx[winner_indices], sy[winner_indices])),
            (float(event.x), float(event.y)),
        )
        if local is None:
            return
        world = self.map_points[winner_indices[local]].astype(np.float64)
        width = max(420, self.map_canvas.winfo_width())
        height = max(360, self.map_canvas.winfo_height())
        self.map_center = world
        self.map_pan[:] = (float(event.x) - width * 0.5, float(event.y) - height * 0.5)
        self.map_render_key = None
        self.redraw_map()

    def reset_map_view(self, _event=None) -> None:
        self.map_center = self.default_center.copy()
        self.map_yaw = 0.0
        self.map_pitch = (math.radians(78.0) + math.pi) % (2.0 * math.pi)
        self.map_roll = 0.0
        self.map_zoom = 1.0
        self.map_pan[:] = (-55.0, -55.0)
        self.map_render_key = None
        self.redraw_map()

    def close(self) -> None:
        self.playing = False
        self.original_cap.release()
        self.processed_cap.release()
        self.destroy()


def main() -> None:
    required = (POSE_CACHE, ORIGINAL_PROXY, PROCESSED_PROXY, SEMANTIC_NPZ)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit(
            "展示資料尚未下載，請先執行 python scripts/download_demo_assets.py\n"
            + "\n".join(missing)
        )
    app = CentralDemo()
    app.mainloop()


if __name__ == "__main__":
    main()
