"""オーバーレイメディア生成のユースケース。"""

from __future__ import annotations

import logging
import multiprocessing
import os
import queue
import shutil
import tempfile
import threading
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from time import perf_counter, sleep

import cv2
import ffmpeg
import numpy as np
import pandas as pd
from PIL import Image, UnidentifiedImageError

from .config import (
    GraphOverlayConfig,
    MapOverlayConfig,
    MetricOverlayConfig,
    OverlayDefinition,
    ProcessorConfig,
    TextColumnOverlayConfig,
    TimeOverlayConfig,
)
from .data import load_fit_data, prepare_overlay_data
from .frames import FrameMaker
from .grade import add_grade
from .next_poi import add_next_poi
from .overlay_factory import OverlayFactory
from .place_names import add_place_names
from .poi import load_points_of_interest
from .route_features import add_route_progress
from .route_margin import add_route_margin
from .text_draw import draw_centered_text, draw_text, font_size_from_cv_scale
from .time_utils import DISPLAY_TIMEZONE, to_utc_timestamp
from .traffic_signals import add_traffic_signal_counts


logger = logging.getLogger(__name__)
VIDEO_SUFFIXES = {".mp4"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
EXIF_DATETIME_TAGS = (
    (36867, 36881),  # DateTimeOriginal, OffsetTimeOriginal
    (36868, 36882),  # DateTimeDigitized, OffsetTimeDigitized
    (306, 36880),  # DateTime, OffsetTime
)


def _current_rss_mb() -> float | None:
    status_path = Path("/proc/self/status")
    try:
        for line in status_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                parts = line.split()
                if len(parts) >= 2:
                    return int(parts[1]) / 1024
    except OSError:
        return None
    return None


def _format_details(details: dict[str, object]) -> str:
    if not details:
        return ""
    return " " + " ".join(f"{key}={value}" for key, value in details.items())


@contextmanager
def _timed_step(name: str, **details: object):
    detail_text = _format_details(details)
    start_rss = _current_rss_mb()
    logger.info(
        "%s started%s rss_mb=%s",
        name,
        detail_text,
        f"{start_rss:.1f}" if start_rss is not None else "unknown",
    )
    start = perf_counter()
    try:
        yield
    except Exception:
        fail_rss = _current_rss_mb()
        logger.exception(
            "%s failed after %.2fs%s rss_mb=%s",
            name,
            perf_counter() - start,
            detail_text,
            f"{fail_rss:.1f}" if fail_rss is not None else "unknown",
        )
        raise
    end_rss = _current_rss_mb()
    logger.info(
        "%s finished in %.2fs%s rss_mb=%s",
        name,
        perf_counter() - start,
        detail_text,
        f"{end_rss:.1f}" if end_rss is not None else "unknown",
    )


@dataclass(frozen=True)
class OverlaySpec:
    """配置設定と生成クラスの組み合わせ。"""

    config: OverlayDefinition
    frame_maker: FrameMaker


@dataclass(frozen=True)
class _OverlayFifo:
    """オーバーレイFIFOのパスとフレームフォーマット情報。"""

    spec: OverlaySpec
    path: Path
    width: int
    height: int
    first_frame: np.ndarray  # _setup_fifosで描画済みのframe 0


@dataclass(frozen=True)
class _FrameExportPoint:
    label: str
    seconds: float


@dataclass(frozen=True)
class _MediaTimeOffsetRule:
    start_time: pd.Timestamp
    offset_seconds: float
    from_file: str


class OverlayVideoProcessor:
    """FIT読み込みから各メディアへのオーバーレイ生成、最終合成までを統括する。"""

    def __init__(self, config: ProcessorConfig) -> None:
        self.config = config
        self.overlay_factory = OverlayFactory()
        self._media_time_offset_rules: tuple[_MediaTimeOffsetRule, ...] | None = None

    def run(self) -> None:
        with _timed_step("overlay_media_processor.run"):
            self._run()

    def write_layout_preview(self, output_path: Path | None = None) -> Path:
        """重いデータ読み込みを避け、overlayの配置確認用PNGを生成する。"""
        with _timed_step("write_layout_preview"):
            return self._write_layout_preview(output_path)

    def write_frame_previews(self, preview_at: str) -> list[Path]:
        """入力ディレクトリ内の全メディアを、実データoverlay付き静止画で出力する。"""
        with _timed_step("write_frame_previews", preview_at=preview_at):
            return self._write_frame_previews(preview_at)

    def _write_layout_preview(self, output_path: Path | None) -> Path:
        enabled_overlays = [
            overlay for overlay in self.config.overlays if overlay.enabled
        ]
        if not enabled_overlays:
            raise ValueError("有効なoverlayがありません。")

        width, height = self._layout_preview_size(enabled_overlays)
        canvas = self._layout_preview_canvas(width, height)
        for overlay in enabled_overlays:
            with _timed_step("draw_layout_preview_overlay", overlay=overlay.id):
                layer = self._layout_preview_layer(overlay)
                self._overlay_rgba_at(canvas, layer, x=overlay.x, y=overlay.y)
                self._draw_layout_preview_guide(canvas, overlay)

        if output_path is None:
            output_path = self.config.output_dir / "overlay_layout_preview.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_image(output_path, canvas[:, :, :3])
        logger.info(
            "layout_preview_output path=%s size=%dx%d",
            output_path,
            width,
            height,
        )
        return output_path

    def _layout_preview_size(
        self,
        overlays: list[OverlayDefinition],
    ) -> tuple[int, int]:
        if self.config.layout.reference_resolution is not None:
            return self.config.layout.reference_resolution
        max_x = max(overlay.x + overlay.width for overlay in overlays)
        max_y = max(overlay.y + overlay.height for overlay in overlays)
        return max(1280, max_x), max(720, max_y)

    @staticmethod
    def _layout_preview_canvas(width: int, height: int) -> np.ndarray:
        canvas = np.full((height, width, 4), (28, 30, 34, 255), dtype=np.uint8)
        grid_color = (48, 52, 58, 255)
        major_grid_color = (68, 74, 84, 255)
        for x in range(0, width, 120):
            color = major_grid_color if x % 480 == 0 else grid_color
            cv2.line(canvas, (x, 0), (x, height - 1), color, 1)
        for y in range(0, height, 120):
            color = major_grid_color if y % 480 == 0 else grid_color
            cv2.line(canvas, (0, y), (width - 1, y), color, 1)
        return canvas

    def _layout_preview_layer(self, overlay: OverlayDefinition) -> np.ndarray:
        if isinstance(overlay, GraphOverlayConfig):
            return self._graph_layout_preview_layer(overlay)
        if isinstance(overlay, MapOverlayConfig):
            return self._map_layout_preview_layer(overlay)
        return self._text_layout_preview_layer(overlay)

    def _text_layout_preview_layer(
        self,
        overlay: OverlayDefinition,
    ) -> np.ndarray:
        background_path = getattr(overlay, "background", None)
        background_color = getattr(overlay, "background_color", (42, 46, 54))
        layer = self._solid_preview_layer(
            overlay.width,
            overlay.height,
            background_color,
            overlay.background_alpha,
        )
        if background_path is not None:
            background = cv2.imread(str(background_path), cv2.IMREAD_UNCHANGED)
            if background is not None:
                background = cv2.resize(background, (overlay.width, overlay.height))
                if background.ndim == 2:
                    rgb = cv2.cvtColor(background, cv2.COLOR_GRAY2RGB)
                    alpha = np.full(
                        (overlay.height, overlay.width, 1),
                        int(round(overlay.background_alpha * 255)),
                        dtype=np.uint8,
                    )
                    layer = np.concatenate([rgb, alpha], axis=2)
                elif background.shape[2] == 4:
                    layer = cv2.cvtColor(background, cv2.COLOR_BGRA2RGBA)
                else:
                    rgb = cv2.cvtColor(background, cv2.COLOR_BGR2RGB)
                    alpha = np.full(
                        (overlay.height, overlay.width, 1),
                        int(round(overlay.background_alpha * 255)),
                        dtype=np.uint8,
                    )
                    layer = np.concatenate([rgb, alpha], axis=2)

        text_style = getattr(overlay, "text", None)
        text = self._layout_preview_sample_text(overlay)
        position = getattr(
            text_style,
            "position",
            (16, min(overlay.height - 12, 44)),
        )
        font_path = getattr(text_style, "font_path", None)
        font_size = getattr(text_style, "font_size", None)
        if font_size is None:
            font_size = font_size_from_cv_scale(
                getattr(text_style, "font_scale", 1.0)
            )
        color = getattr(text_style, "color", (255, 255, 255))
        thickness = getattr(text_style, "thickness", 2)
        return draw_text(
            layer,
            text,
            position,
            color=color,
            font_path=font_path,
            font_size=font_size,
            stroke_width=max(0, thickness - 1),
            stroke_fill=(0, 0, 0),
        )

    @staticmethod
    def _layout_preview_sample_text(overlay: OverlayDefinition) -> str:
        if isinstance(overlay, TimeOverlayConfig):
            return "2026/01/01 12:34:56"
        if isinstance(overlay, MetricOverlayConfig):
            if overlay.value_format == "duration_margin":
                return "+00:00"
            try:
                return overlay.value_format.format(
                    value=12.3,
                    duration_margin="+00:00",
                )
            except (KeyError, IndexError, ValueError):
                return overlay.id
        if isinstance(overlay, TextColumnOverlayConfig):
            return overlay.column or overlay.id
        return overlay.id

    def _graph_layout_preview_layer(self, overlay: GraphOverlayConfig) -> np.ndarray:
        layer = self._solid_preview_layer(
            overlay.width,
            overlay.height,
            overlay.background_color,
            overlay.background_alpha,
        )
        padding_left, padding_top, padding_right, padding_bottom = overlay.padding
        x1 = min(overlay.width - 2, max(1, padding_left))
        y1 = min(overlay.height - 2, max(1, padding_top))
        x2 = max(x1 + 1, overlay.width - max(1, padding_right))
        y2 = max(y1 + 1, overlay.height - max(1, padding_bottom))
        plot_color = overlay.plot_background_color or (22, 24, 28)
        cv2.rectangle(layer, (x1, y1), (x2, y2), (*plot_color, 255), -1)
        for i in range(1, 4):
            x = x1 + (x2 - x1) * i // 4
            y = y1 + (y2 - y1) * i // 4
            cv2.line(layer, (x, y1), (x, y2), (*overlay.grid_color, 180), 1)
            cv2.line(layer, (x1, y), (x2, y), (*overlay.grid_color, 180), 1)
        points = []
        for i in range(24):
            x = x1 + (x2 - x1) * i // 23
            ratio = (np.sin(i / 23 * np.pi * 3.0) + 1.0) / 2.0
            y = int(y2 - ratio * (y2 - y1) * 0.8 - (y2 - y1) * 0.1)
            points.append((x, y))
        cv2.polylines(
            layer,
            [np.array(points, dtype=np.int32)],
            False,
            (*overlay.line_color, 255),
            3,
        )
        return draw_text(
            layer,
            f"{overlay.id} graph",
            (12, min(overlay.height - 10, 34)),
            color=overlay.text_color,
            font_size=24,
            stroke_width=1,
            stroke_fill=(0, 0, 0),
        )

    def _map_layout_preview_layer(self, overlay: MapOverlayConfig) -> np.ndarray:
        layer = self._solid_preview_layer(
            overlay.width,
            overlay.height,
            (46, 62, 58),
            overlay.background_alpha,
        )
        for x in range(0, overlay.width, 80):
            cv2.line(
                layer,
                (x, 0),
                (x, overlay.height - 1),
                (72, 90, 84, 255),
                1,
            )
        for y in range(0, overlay.height, 80):
            cv2.line(
                layer,
                (0, y),
                (overlay.width - 1, y),
                (72, 90, 84, 255),
                1,
            )
        route = np.array(
            [
                (overlay.width * 15 // 100, overlay.height * 70 // 100),
                (overlay.width * 35 // 100, overlay.height * 54 // 100),
                (overlay.width * 48 // 100, overlay.height * 62 // 100),
                (overlay.width * 65 // 100, overlay.height * 36 // 100),
                (overlay.width * 86 // 100, overlay.height * 28 // 100),
            ],
            dtype=np.int32,
        )
        cv2.polylines(
            layer,
            [route],
            False,
            (*overlay.route_color, 255),
            max(2, overlay.route_thickness),
        )
        cv2.circle(
            layer,
            (overlay.width // 2, overlay.height // 2),
            max(6, overlay.circle_radius),
            (255, 255, 255, 255),
            -1,
        )
        cv2.circle(
            layer,
            (overlay.width // 2, overlay.height // 2),
            max(6, overlay.circle_radius),
            (30, 80, 220, 255),
            2,
        )
        return draw_centered_text(
            layer,
            f"{overlay.id} map",
            (overlay.width // 2, max(24, overlay.height // 6)),
            color=(255, 255, 255),
            font_size=24,
            stroke_width=1,
            stroke_fill=(0, 0, 0),
        )

    @staticmethod
    def _solid_preview_layer(
        width: int,
        height: int,
        color: tuple[int, int, int],
        alpha: float,
    ) -> np.ndarray:
        rgb = np.full((height, width, 3), color, dtype=np.uint8)
        alpha_channel = np.full(
            (height, width, 1),
            int(round(alpha * 255)),
            dtype=np.uint8,
        )
        return np.concatenate([rgb, alpha_channel], axis=2)

    def _draw_layout_preview_guide(
        self,
        canvas: np.ndarray,
        overlay: OverlayDefinition,
    ) -> None:
        x1 = max(0, overlay.x)
        y1 = max(0, overlay.y)
        x2 = min(canvas.shape[1] - 1, overlay.x + overlay.width - 1)
        y2 = min(canvas.shape[0] - 1, overlay.y + overlay.height - 1)
        if x1 > x2 or y1 > y2:
            return
        color = self._layout_preview_guide_color(overlay)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), (*color, 255), 3)
        label = (
            f"{overlay.id} {overlay.type} "
            f"{overlay.x},{overlay.y} {overlay.width}x{overlay.height}"
        )
        label_y = y1 + 28 if y1 + 32 < canvas.shape[0] else y1 + 16
        label_x = min(max(4, x1 + 8), max(4, canvas.shape[1] - 520))
        draw_text(
            canvas,
            label,
            (label_x, label_y),
            color=(255, 255, 255),
            font_size=22,
            stroke_width=2,
            stroke_fill=(0, 0, 0),
        )

    @staticmethod
    def _layout_preview_guide_color(
        overlay: OverlayDefinition,
    ) -> tuple[int, int, int]:
        if isinstance(overlay, MapOverlayConfig):
            return (94, 230, 180)
        if isinstance(overlay, GraphOverlayConfig):
            return (255, 202, 88)
        if isinstance(overlay, TimeOverlayConfig):
            return (116, 185, 255)
        if isinstance(overlay, TextColumnOverlayConfig):
            return (210, 160, 255)
        return (255, 120, 120)

    def _write_frame_previews(self, preview_at: str) -> list[Path]:
        with _timed_step("validate_paths"):
            self._validate_paths()
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        overlays = self._load_overlay_specs()
        media_paths = sorted(
            p
            for p in self.config.mp4_dir.iterdir()
            if p.is_file()
            and p.suffix.lower() in VIDEO_SUFFIXES | IMAGE_SUFFIXES
        )
        logger.info(
            "preview_frame_media_paths count=%d input_dir=%s",
            len(media_paths),
            self.config.mp4_dir,
        )
        output_paths: list[Path] = []
        errors: list[tuple[Path, int | None, str | None]] = []
        for path in media_paths:
            try:
                if path.suffix.lower() in VIDEO_SUFFIXES:
                    output_paths.append(
                        self._write_video_frame_preview(path, overlays, preview_at)
                    )
                else:
                    output_paths.append(
                        self._write_image_frame_preview(path, overlays)
                    )
            except Exception:
                errors.append((path, None, traceback.format_exc()))
                logger.error("preview_frame_failed path=%s", path)
        if errors:
            raise RuntimeError(
                "プレビュー静止画生成に失敗しました: "
                + self._format_media_errors(errors)
            )
        return output_paths

    def _load_overlay_specs(self) -> list[OverlaySpec]:
        max_duration = (
            None
            if self.config.max_fit_duration_minutes is None
            else pd.Timedelta(minutes=self.config.max_fit_duration_minutes)
        )
        with _timed_step("load_fit_data", path=self.config.fit_path):
            fit_data = load_fit_data(
                self.config.fit_path,
                time_offset=pd.Timedelta(
                    seconds=self.config.fit_time_offset_seconds
                ),
                max_duration=max_duration,
            )
        logger.info(
            "load_fit_data rows=%d start=%s end=%s",
            len(fit_data),
            fit_data.index[0] if len(fit_data) else None,
            fit_data.index[-1] if len(fit_data) else None,
        )
        enabled_overlays = [
            overlay for overlay in self.config.overlays if overlay.enabled
        ]
        if not enabled_overlays:
            raise ValueError("有効なoverlayがありません。")
        logger.info(
            "enabled_overlays count=%d ids=%s",
            len(enabled_overlays),
            ",".join(overlay.id for overlay in enabled_overlays),
        )
        with _timed_step("prepare_overlay_data"):
            overlay_data = prepare_overlay_data(fit_data)
        with _timed_step("add_route_progress"):
            overlay_data = add_route_progress(
                overlay_data,
                self.config.route_progress,
            )
        with _timed_step("add_grade"):
            overlay_data = add_grade(
                overlay_data,
                self.config.grade,
            )
        with _timed_step("add_route_margin"):
            overlay_data = add_route_margin(
                overlay_data,
                self.config.route_margin,
            )
        with _timed_step("add_traffic_signal_counts"):
            overlay_data = add_traffic_signal_counts(
                overlay_data,
                self.config.traffic_signals,
            )
        with _timed_step("add_place_names"):
            overlay_data = add_place_names(
                overlay_data,
                self.config.place_names,
            )
        default_poi_gpx_path = (
            self.config.points_of_interest.gpx_path
            or self.config.route_progress.gpx_path
            or self.config.route_margin.gpx_path
            or self.config.traffic_signals.gpx_path
            or self.config.place_names.gpx_path
        )
        with _timed_step("load_points_of_interest"):
            points_of_interest = load_points_of_interest(
                self.config.points_of_interest,
                default_gpx_path=default_poi_gpx_path,
            )
        logger.info("points_of_interest count=%d", len(points_of_interest))
        with _timed_step("add_next_poi"):
            overlay_data = add_next_poi(
                overlay_data,
                self.config.next_poi,
                points_of_interest,
            )
        self.overlay_factory = OverlayFactory(
            points_of_interest,
            route_progress_column=self.config.route_progress.progress_column,
        )
        with _timed_step("create_overlay_specs"):
            overlays = self._create_overlay_specs(overlay_data)
        for spec in overlays:
            with _timed_step("warmup_overlay", overlay=spec.config.id):
                spec.frame_maker.warmup()
        return overlays

    def _write_video_frame_preview(
        self,
        video_path: Path,
        overlays: list[OverlaySpec],
        preview_at: str,
    ) -> Path:
        with _timed_step("write_video_frame_preview", path=video_path):
            with _timed_step("ffprobe", path=video_path):
                video_info = ffmpeg.probe(
                    str(video_path),
                    cmd=str(self.config.ffprobe_binary),
                )
                video_stream = next(
                    stream
                    for stream in video_info["streams"]
                    if stream["codec_type"] == "video"
                )
            video_width = int(video_stream["width"])
            video_height = int(video_stream["height"])
            video_length = float(video_stream["duration"])
            offset_seconds = self._parse_preview_at(preview_at, video_length)
            video_start = self._read_video_shot_time(video_path, video_info)
            shot_time = video_start + pd.Timedelta(seconds=offset_seconds)
            logger.info(
                "video_preview_metadata path=%s size=%dx%d duration=%.3fs "
                "offset=%.3fs shot_time=%s",
                video_path,
                video_width,
                video_height,
                video_length,
                offset_seconds,
                shot_time,
            )
            frame = self._read_video_frame(
                video_path,
                offset_seconds,
                video_width=video_width,
                video_height=video_height,
            )
            output_path = (
                self.config.output_dir
                / (
                    f"{video_path.stem}_preview_"
                    f"{self._preview_at_label(offset_seconds)}.jpg"
                )
            )
            self._write_frame_preview_output(
                video_path,
                frame,
                overlays,
                shot_time=shot_time,
                duration=1.0,
                output_path=output_path,
                source_has_alpha=False,
            )
            return output_path

    def _write_video_still_exports(
        self,
        video_paths: list[Path],
        overlays: list[OverlaySpec],
    ) -> list[Path]:
        if not self.config.still_exports.enabled:
            return []
        with _timed_step("write_video_still_exports", count=len(video_paths)):
            output_paths: list[Path] = []
            errors: list[tuple[Path, int | None, str | None]] = []
            for video_path in video_paths:
                try:
                    output_paths.extend(
                        self._write_video_still_exports_for_video(
                            video_path,
                            overlays,
                        )
                    )
                except Exception:
                    errors.append((video_path, None, traceback.format_exc()))
                    logger.error("video_still_export_failed path=%s", video_path)
            if errors:
                raise RuntimeError(
                    "動画静止画出力に失敗しました: "
                    + self._format_media_errors(errors)
                )
            return output_paths

    def _write_video_still_exports_for_video(
        self,
        video_path: Path,
        overlays: list[OverlaySpec],
    ) -> list[Path]:
        with _timed_step("write_video_still_exports_for_video", path=video_path):
            with _timed_step("ffprobe", path=video_path):
                video_info = ffmpeg.probe(
                    str(video_path),
                    cmd=str(self.config.ffprobe_binary),
                )
                video_stream = next(
                    stream
                    for stream in video_info["streams"]
                    if stream["codec_type"] == "video"
                )
            video_width = int(video_stream["width"])
            video_height = int(video_stream["height"])
            video_length = float(video_stream["duration"])
            video_start = self._read_video_shot_time(video_path, video_info)
            export_points = self._still_export_points(video_length)
            logger.info(
                "video_still_export_metadata path=%s size=%dx%d duration=%.3fs "
                "points=%d",
                video_path,
                video_width,
                video_height,
                video_length,
                len(export_points),
            )
            output_paths: list[Path] = []
            for point in export_points:
                frame = self._read_video_frame(
                    video_path,
                    point.seconds,
                    video_width=video_width,
                    video_height=video_height,
                )
                output_path = (
                    self.config.output_dir
                    / f"{video_path.stem}_still_{point.label}.jpg"
                )
                self._write_frame_preview_output(
                    video_path,
                    frame,
                    overlays,
                    shot_time=video_start + pd.Timedelta(seconds=point.seconds),
                    duration=1.0,
                    output_path=output_path,
                    source_has_alpha=False,
                )
                output_paths.append(output_path)
            return output_paths

    def _still_export_points(self, duration: float) -> list[_FrameExportPoint]:
        points: list[_FrameExportPoint] = []
        seen: set[int] = set()

        def add(label: str, seconds: float) -> None:
            key = int(round(seconds * 1000))
            if key in seen:
                return
            seen.add(key)
            points.append(_FrameExportPoint(label=label, seconds=seconds))

        for position in self.config.still_exports.positions:
            seconds = self._parse_preview_at(position, duration)
            label = (
                "middle"
                if position.strip().lower() == "middle"
                else self._still_export_label(seconds)
            )
            add(label, seconds)

        interval_seconds = self.config.still_exports.interval_seconds
        if interval_seconds is not None:
            max_seconds = max(0.0, duration - 0.001) if duration > 0 else 0.0
            seconds = 0.0
            while seconds <= max_seconds + 1e-9:
                add(self._still_export_label(seconds), seconds)
                seconds += interval_seconds
        return points

    def _write_image_frame_preview(
        self,
        image_path: Path,
        overlays: list[OverlaySpec],
    ) -> Path:
        with _timed_step("write_image_frame_preview", path=image_path):
            base_image = self._read_image(image_path)
            shot_time = self._read_image_shot_time(image_path)
            source_has_alpha = base_image.shape[2] == 4
            suffix = (
                ".png"
                if source_has_alpha or image_path.suffix.lower() == ".png"
                else ".jpg"
            )
            output_path = (
                self.config.output_dir / f"{image_path.stem}_preview{suffix}"
            )
            self._write_frame_preview_output(
                image_path,
                base_image,
                overlays,
                shot_time=shot_time,
                duration=1.0,
                output_path=output_path,
                source_has_alpha=source_has_alpha,
            )
            return output_path

    def _write_frame_preview_output(
        self,
        media_path: Path,
        base_image: np.ndarray,
        overlays: list[OverlaySpec],
        *,
        shot_time: pd.Timestamp,
        duration: float,
        output_path: Path,
        source_has_alpha: bool,
    ) -> None:
        image_height, image_width = base_image.shape[:2]
        self._log_media_data_coverage(
            media_path,
            shot_time,
            duration,
            overlays,
        )
        scale = self._layout_scale(image_width, image_height)
        for spec in overlays:
            with _timed_step(
                "prepare_overlay_preview_frame",
                media=media_path.name,
                overlay=spec.config.id,
            ):
                spec.frame_maker.prepare_video(shot_time, duration)

        output = self._compose_image_overlays(
            self._rgba_frame(base_image),
            overlays,
            layout_scale=scale,
        )
        if not source_has_alpha:
            output = output[:, :, :3]
        self._write_image(output_path, output)

    def _read_video_frame(
        self,
        video_path: Path,
        offset_seconds: float,
        *,
        video_width: int,
        video_height: int,
    ) -> np.ndarray:
        input_options: dict[str, object] = {"ss": max(0.0, offset_seconds)}
        if self.config.noautorotate:
            input_options["noautorotate"] = None
        stream = ffmpeg.input(str(video_path), **input_options).output(
            "pipe:",
            vframes=1,
            format="rawvideo",
            pix_fmt="rgb24",
        )
        stdout, _ = ffmpeg.run(
            stream,
            cmd=str(self.config.ffmpeg_binary),
            capture_stdout=True,
            capture_stderr=True,
            overwrite_output=True,
        )
        expected_bytes = video_width * video_height * 3
        if len(stdout) != expected_bytes:
            raise RuntimeError(
                f"動画フレームの読み込みサイズが不正です: {video_path} "
                f"bytes={len(stdout)} expected={expected_bytes}"
            )
        return np.frombuffer(stdout, np.uint8).reshape(
            (video_height, video_width, 3)
        )

    @staticmethod
    def _parse_preview_at(value: str, duration: float) -> float:
        text = value.strip().lower()
        if text == "middle":
            return max(0.0, duration / 2.0)
        try:
            seconds = float(text)
        except ValueError:
            parts = text.split(":")
            if len(parts) not in {2, 3}:
                raise ValueError(
                    "--preview-atは秒数、MM:SS、HH:MM:SS、middleで指定してください。"
                )
            try:
                numbers = [float(part) for part in parts]
            except ValueError as exc:
                raise ValueError(
                    "--preview-atは秒数、MM:SS、HH:MM:SS、middleで指定してください。"
                ) from exc
            if len(numbers) == 2:
                minutes, seconds_part = numbers
                seconds = minutes * 60 + seconds_part
            else:
                hours, minutes, seconds_part = numbers
                seconds = hours * 3600 + minutes * 60 + seconds_part
        if seconds < 0:
            raise ValueError("--preview-atは0以上を指定してください。")
        if duration > 0:
            return min(seconds, max(0.0, duration - 0.001))
        return seconds

    @staticmethod
    def _preview_at_label(seconds: float) -> str:
        rounded = int(round(seconds))
        hours = rounded // 3600
        minutes = (rounded % 3600) // 60
        secs = rounded % 60
        return f"{hours:02d}-{minutes:02d}-{secs:02d}"

    @staticmethod
    def _still_export_label(seconds: float) -> str:
        rounded_ms = int(round(seconds * 1000))
        total_seconds, milliseconds = divmod(rounded_ms, 1000)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        label = f"{hours:02d}-{minutes:02d}-{secs:02d}"
        if milliseconds:
            label += f"-{milliseconds:03d}"
        return label

    def _run(self) -> None:
        with _timed_step("validate_paths"):
            self._validate_paths()
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        max_duration = (
            None
            if self.config.max_fit_duration_minutes is None
            else pd.Timedelta(minutes=self.config.max_fit_duration_minutes)
        )
        with _timed_step("load_fit_data", path=self.config.fit_path):
            # FITは一度だけ読み込み、すべての入力メディアで共有する。
            # カメラとFITの時計にずれがある場合は、設定した秒数だけFIT時刻を補正する。
            fit_data = load_fit_data(
                self.config.fit_path,
                time_offset=pd.Timedelta(
                    seconds=self.config.fit_time_offset_seconds
                ),
                max_duration=max_duration,
            )
        logger.info(
            "load_fit_data rows=%d start=%s end=%s",
            len(fit_data),
            fit_data.index[0] if len(fit_data) else None,
            fit_data.index[-1] if len(fit_data) else None,
        )
        enabled_overlays = [
            overlay for overlay in self.config.overlays if overlay.enabled
        ]
        if not enabled_overlays:
            raise ValueError("有効なoverlayがありません。")
        logger.info(
            "enabled_overlays count=%d ids=%s",
            len(enabled_overlays),
            ",".join(overlay.id for overlay in enabled_overlays),
        )
        # FITの行は増やさず欠損だけ補完する。表示頻度はoverlayごとのfpsで決める。
        with _timed_step("prepare_overlay_data"):
            overlay_data = prepare_overlay_data(fit_data)
        with _timed_step("add_route_progress"):
            overlay_data = add_route_progress(
                overlay_data,
                self.config.route_progress,
            )
        with _timed_step("add_grade"):
            overlay_data = add_grade(
                overlay_data,
                self.config.grade,
            )
        with _timed_step("add_route_margin"):
            overlay_data = add_route_margin(
                overlay_data,
                self.config.route_margin,
            )
        with _timed_step("add_traffic_signal_counts"):
            overlay_data = add_traffic_signal_counts(
                overlay_data,
                self.config.traffic_signals,
            )
        with _timed_step("add_place_names"):
            overlay_data = add_place_names(
                overlay_data,
                self.config.place_names,
            )
        default_poi_gpx_path = (
            self.config.points_of_interest.gpx_path
            or self.config.route_progress.gpx_path
            or self.config.route_margin.gpx_path
            or self.config.traffic_signals.gpx_path
            or self.config.place_names.gpx_path
        )
        with _timed_step("load_points_of_interest"):
            points_of_interest = load_points_of_interest(
                self.config.points_of_interest,
                default_gpx_path=default_poi_gpx_path,
            )
        logger.info("points_of_interest count=%d", len(points_of_interest))
        with _timed_step("add_next_poi"):
            overlay_data = add_next_poi(
                overlay_data,
                self.config.next_poi,
                points_of_interest,
            )
        self.overlay_factory = OverlayFactory(
            points_of_interest,
            route_progress_column=self.config.route_progress.progress_column,
        )
        with _timed_step("create_overlay_specs"):
            overlays = self._create_overlay_specs(overlay_data)

        # route_overview などメディア間で共通な静的部分を親プロセスで事前レンダリング。
        # fork 後は動画処理の子プロセスが copy-on-write で共有する。
        for spec in overlays:
            with _timed_step("warmup_overlay", overlay=spec.config.id):
                spec.frame_maker.warmup()

        media_paths = sorted(
            p
            for p in self.config.mp4_dir.iterdir()
            if p.is_file()
            and p.suffix.lower() in VIDEO_SUFFIXES | IMAGE_SUFFIXES
        )
        video_paths = [
            path for path in media_paths if path.suffix.lower() in VIDEO_SUFFIXES
        ]
        image_paths = [
            path for path in media_paths if path.suffix.lower() in IMAGE_SUFFIXES
        ]
        logger.info(
            "media_paths videos=%d images=%d input_dir=%s max_parallel_videos=%d",
            len(video_paths),
            len(image_paths),
            self.config.mp4_dir,
            self.config.max_parallel_videos,
        )
        if self.config.max_parallel_videos <= 1:
            logger.info("video_processing_mode sequential")
            errors: list[tuple[Path, int | None, str | None]] = []
            for path in video_paths:
                try:
                    self._process_video(path, overlays)
                except Exception:
                    errors.append((path, None, traceback.format_exc()))
                    logger.error("video_processing_failed path=%s", path)
            if errors:
                raise RuntimeError(
                    "動画処理に失敗しました: " + self._format_media_errors(errors)
                )
        else:
            logger.warning(
                "video_processing_mode parallel max_parallel=%d; "
                "multiple ffmpeg encoders and map renderers may compete for CPU/GPU/I/O",
                self.config.max_parallel_videos,
            )
            self._process_videos_parallel(
                video_paths, overlays, self.config.max_parallel_videos
            )

        self._write_video_still_exports(video_paths, overlays)

        image_errors: list[tuple[Path, int | None, str | None]] = []
        for path in image_paths:
            try:
                self._process_image(path, overlays)
            except Exception:
                image_errors.append((path, None, traceback.format_exc()))
                logger.error("image_processing_failed path=%s", path)
        if image_errors:
            raise RuntimeError(
                "静止画処理に失敗しました: " + self._format_media_errors(image_errors)
            )

    def _process_videos_parallel(
        self,
        video_paths: list[Path],
        overlays: list[OverlaySpec],
        max_parallel: int,
    ) -> None:
        """fork ベースのプロセス管理で複数動画を並列処理する。

        fork が有効なのは Linux/macOS のみ。WSL2 で正常動作する。
        Process.start() はメインスレッドからだけ呼び、スレッド内forkを避ける。
        """
        ctx = multiprocessing.get_context("fork")
        errors: list[tuple[Path, int | None, str | None]] = []
        pending_paths = iter(video_paths)
        pending_exhausted = False
        running: list[
            tuple[Path, multiprocessing.Process, multiprocessing.Queue]
        ] = []

        def start_next() -> bool:
            nonlocal pending_exhausted
            if pending_exhausted:
                return False
            try:
                path = next(pending_paths)
            except StopIteration:
                pending_exhausted = True
                return False

            logger.info("queue_video_process path=%s", path)
            error_queue = ctx.Queue(maxsize=1)
            process = ctx.Process(
                target=self._process_video_worker,
                args=(path, overlays, error_queue),
            )
            logger.info("start_video_process path=%s", path)
            process.start()
            running.append((path, process, error_queue))
            return True

        def reap_finished() -> None:
            still_running = []
            for path, process, error_queue in running:
                if process.is_alive():
                    still_running.append((path, process, error_queue))
                    continue

                process.join()
                error_text = None
                try:
                    error_text = error_queue.get_nowait()
                except queue.Empty:
                    pass
                finally:
                    error_queue.close()

                logger.info(
                    "video_process_exited path=%s exitcode=%s",
                    path,
                    process.exitcode,
                )
                if process.exitcode != 0:
                    errors.append((path, process.exitcode, error_text))

            running[:] = still_running

        while not pending_exhausted or running:
            while len(running) < max_parallel and start_next():
                pass
            reap_finished()
            if running:
                sleep(0.2)

        if errors:
            raise RuntimeError(
                "動画処理に失敗しました: " + self._format_media_errors(errors)
            )

    @staticmethod
    def _format_media_errors(
        errors: list[tuple[Path, int | None, str | None]],
    ) -> str:
        return "; ".join(
            str(path)
            + (f" (exitcode={exitcode})" if exitcode is not None else "")
            + (f"\n{error_text}" if error_text else "")
            for path, exitcode, error_text in errors
        )

    def _process_video_worker(
        self,
        video_path: Path,
        overlays: list[OverlaySpec],
        error_queue: multiprocessing.Queue,
    ) -> None:
        # fork後に他スレッドが保持していたloggingロックがそのまま残るため、
        # 子プロセス開始直後にロックを再初期化してデッドロックを防ぐ。
        reinit_logging = getattr(
            logging,
            "_after_at_fork_child_reinit",
            getattr(logging, "_after_at_fork_child_reinit_locks", None),
        )
        if reinit_logging is not None:
            reinit_logging()
        try:
            self._process_video(video_path, overlays)
        except BaseException:
            error_queue.put(traceback.format_exc())
            raise

    def _validate_paths(self) -> None:
        if not self.config.mp4_dir.is_dir():
            raise NotADirectoryError(self.config.mp4_dir)
        if not self.config.fit_path.is_file():
            raise FileNotFoundError(self.config.fit_path)
        if not self.config.ffmpeg_binary.is_file():
            raise FileNotFoundError(self.config.ffmpeg_binary)
        if not self.config.ffprobe_binary.is_file():
            raise FileNotFoundError(self.config.ffprobe_binary)
        if not 0 <= self.config.video_crf <= 51:
            raise ValueError("video_crfは0から51の範囲で指定してください。")
        if not 0 <= self.config.video_cq <= 51:
            raise ValueError("video_cqは0から51の範囲で指定してください。")

    def _layout_scale(self, media_width: int, media_height: int) -> float:
        if self.config.layout.reference_resolution is None:
            return 1.0
        reference_width, reference_height = self.config.layout.reference_resolution
        if self.config.layout.scale_mode == "fit":
            return min(media_width / reference_width, media_height / reference_height)
        raise ValueError(
            f"未対応のlayout.scale_modeです: {self.config.layout.scale_mode}"
        )

    def _create_overlay_specs(self, data) -> list[OverlaySpec]:
        return [
            OverlaySpec(
                config=overlay,
                frame_maker=self.overlay_factory.create(overlay, data),
            )
            for overlay in self.config.overlays
            if overlay.enabled
        ]

    def _process_video(
        self, video_path: Path, overlays: list[OverlaySpec]
    ) -> None:
        with _timed_step("process_video", path=video_path):
            self._process_video_inner(video_path, overlays)

    def _process_video_inner(
        self, video_path: Path, overlays: list[OverlaySpec]
    ) -> None:
        with _timed_step("ffprobe", path=video_path):
            video_info = ffmpeg.probe(
                str(video_path),
                cmd=str(self.config.ffprobe_binary),
            )
            video_stream = next(
                stream
                for stream in video_info["streams"]
                if stream["codec_type"] == "video"
            )
        video_width = int(video_stream["width"])
        video_height = int(video_stream["height"])
        video_fps = self._stream_frame_rate(video_stream)
        shot_time = self._read_video_shot_time(video_path, video_info)
        video_length = float(video_stream["duration"])
        has_audio = any(
            stream["codec_type"] == "audio" for stream in video_info["streams"]
        )
        logger.info(
            "video_metadata path=%s size=%dx%d duration=%.3fs shot_time=%s has_audio=%s",
            video_path,
            video_width,
            video_height,
            video_length,
            shot_time,
            has_audio,
        )
        self._log_media_data_coverage(video_path, shot_time, video_length, overlays)
        scale = self._layout_scale(video_width, video_height)
        for spec in overlays:
            with _timed_step(
                "prepare_overlay_video",
                video=video_path.name,
                overlay=spec.config.id,
            ):
                spec.frame_maker.prepare_video(shot_time, video_length)

        fifo_dir = Path(tempfile.mkdtemp(prefix="fit_overlay_"))
        threads: list[threading.Thread] = []
        try:
            with _timed_step("setup_fifos", video=video_path.name):
                fifo_infos = self._setup_fifos(overlays, fifo_dir)
            errors: list[BaseException] = []
            errors_lock = threading.Lock()
            threads = [
                threading.Thread(
                    target=self._write_frames_to_fifo_safe,
                    args=(fi, video_length, errors, errors_lock),
                    daemon=True,
                )
                for fi in fifo_infos
            ]
            for t in threads:
                t.start()
            with _timed_step("compose_video", video=video_path.name):
                self._compose_video(
                    video_path,
                    fifo_infos,
                    video_width=video_width,
                    video_height=video_height,
                    video_length=video_length,
                    video_fps=video_fps,
                    layout_scale=scale,
                    has_audio=has_audio,
                )
            for t in threads:
                t.join()
            if errors:
                raise RuntimeError(
                    "オーバーレイフレーム生成中にエラーが発生しました"
                ) from errors[0]
        finally:
            # FIFOを削除することでブロック中のスレッドをBrokenPipeErrorで終了させる。
            shutil.rmtree(fifo_dir, ignore_errors=True)
            for t in threads:
                t.join(timeout=5.0)

    def _process_image(
        self, image_path: Path, overlays: list[OverlaySpec]
    ) -> None:
        with _timed_step("process_image", path=image_path):
            self._process_image_inner(image_path, overlays)

    def _process_image_inner(
        self, image_path: Path, overlays: list[OverlaySpec]
    ) -> None:
        base_image = self._read_image(image_path)
        image_height, image_width = base_image.shape[:2]
        shot_time = self._read_image_shot_time(image_path)
        still_duration = 1.0
        logger.info(
            "image_metadata path=%s size=%dx%d shot_time=%s mode=%s",
            image_path,
            image_width,
            image_height,
            shot_time,
            self.config.output_mode,
        )
        self._log_media_data_coverage(
            image_path,
            shot_time,
            still_duration,
            overlays,
        )
        scale = self._layout_scale(image_width, image_height)
        for spec in overlays:
            with _timed_step(
                "prepare_overlay_image",
                image=image_path.name,
                overlay=spec.config.id,
            ):
                spec.frame_maker.prepare_video(shot_time, still_duration)

        if self.config.output_mode == "transparent_overlay":
            canvas = np.zeros((image_height, image_width, 4), dtype=np.uint8)
            output_path = self.config.output_dir / f"{image_path.stem}_overlay.png"
            output = self._compose_image_overlays(
                canvas,
                overlays,
                layout_scale=scale,
            )
        else:
            source_has_alpha = base_image.shape[2] == 4
            canvas = self._rgba_frame(base_image)
            output_path = self._composited_image_output_path(
                image_path,
                source_has_alpha=source_has_alpha,
            )
            output = self._compose_image_overlays(
                canvas,
                overlays,
                layout_scale=scale,
            )
            if not source_has_alpha:
                output = output[:, :, :3]

        self._write_image(output_path, output)

    def _compose_image_overlays(
        self,
        canvas: np.ndarray,
        overlays: list[OverlaySpec],
        *,
        layout_scale: float,
    ) -> np.ndarray:
        composed = self._rgba_frame(canvas).copy()
        for spec in overlays:
            with _timed_step("make_image_overlay_frame", overlay=spec.config.id):
                frame = self._rgba_frame(spec.frame_maker.make_frame(0.0))
            if layout_scale != 1.0:
                frame = cv2.resize(
                    frame,
                    (
                        max(2, int(round(frame.shape[1] * layout_scale))),
                        max(2, int(round(frame.shape[0] * layout_scale))),
                    ),
                    interpolation=cv2.INTER_AREA,
                )
            self._overlay_rgba_at(
                composed,
                frame,
                x=max(0, int(round(spec.config.x * layout_scale))),
                y=max(0, int(round(spec.config.y * layout_scale))),
            )
        return composed

    @staticmethod
    def _overlay_rgba_at(
        background: np.ndarray,
        overlay: np.ndarray,
        *,
        x: int,
        y: int,
    ) -> None:
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(background.shape[1], x + overlay.shape[1])
        y2 = min(background.shape[0], y + overlay.shape[0])
        if x1 >= x2 or y1 >= y2:
            return

        overlay_crop = overlay[
            y1 - y : y2 - y,
            x1 - x : x2 - x,
        ].astype(np.float32)
        target = background[y1:y2, x1:x2].astype(np.float32)
        overlay_alpha = overlay_crop[..., 3:4] / 255.0
        target_alpha = target[..., 3:4] / 255.0
        output_alpha = overlay_alpha + target_alpha * (1.0 - overlay_alpha)
        numerator = (
            overlay_crop[..., :3] * overlay_alpha
            + target[..., :3] * target_alpha * (1.0 - overlay_alpha)
        )
        output_rgb = np.divide(
            numerator,
            output_alpha,
            out=np.zeros_like(numerator),
            where=output_alpha > 0,
        )
        background[y1:y2, x1:x2, :3] = np.clip(output_rgb, 0, 255).astype(np.uint8)
        background[y1:y2, x1:x2, 3:4] = np.clip(
            output_alpha * 255,
            0,
            255,
        ).astype(np.uint8)

    @staticmethod
    def _read_image(image_path: Path) -> np.ndarray:
        image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
        if image is None:
            raise FileNotFoundError(f"静止画を読み込めません: {image_path}")
        if image.ndim == 2:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        if image.ndim == 3 and image.shape[2] == 3:
            return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        if image.ndim == 3 and image.shape[2] == 4:
            return cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA)
        raise ValueError(f"未対応の静止画形式です: {image_path}")

    def _read_image_shot_time(self, image_path: Path) -> pd.Timestamp:
        exif_time = self._read_exif_shot_time(image_path)
        if exif_time is not None:
            return exif_time
        mtime = pd.Timestamp.fromtimestamp(image_path.stat().st_mtime, tz="UTC")
        logger.info(
            "image_shot_time_fallback_mtime path=%s mtime=%s",
            image_path,
            mtime,
        )
        return mtime

    @staticmethod
    def _read_exif_shot_time(image_path: Path) -> pd.Timestamp | None:
        try:
            with Image.open(image_path) as image:
                exif = image.getexif()
        except (OSError, UnidentifiedImageError):
            return None
        if not exif:
            return None

        value = None
        offset = None
        for value_tag, offset_tag in EXIF_DATETIME_TAGS:
            value = exif.get(value_tag)
            if value:
                offset = exif.get(offset_tag)
                break
        if value is None:
            return None
        try:
            timestamp = datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S")
        except ValueError:
            logger.warning(
                "invalid_exif_datetime path=%s value=%s",
                image_path,
                value,
            )
            return None

        if offset:
            try:
                return pd.Timestamp(f"{timestamp.isoformat()}{offset}").tz_convert(
                    "UTC"
                )
            except ValueError:
                logger.warning(
                    "invalid_exif_offset path=%s value=%s offset=%s",
                    image_path,
                    value,
                    offset,
                )
        return pd.Timestamp(timestamp).tz_localize(DISPLAY_TIMEZONE).tz_convert(
            "UTC"
        )

    def _composited_image_output_path(
        self,
        image_path: Path,
        *,
        source_has_alpha: bool,
    ) -> Path:
        if source_has_alpha or image_path.suffix.lower() == ".png":
            suffix = ".png"
        else:
            suffix = ".jpg"
        return self.config.output_dir / f"{image_path.stem}_output{suffix}"

    def _write_image(self, output_path: Path, image: np.ndarray) -> None:
        temp_output_path = (
            output_path.parent
            / f".{output_path.stem}.{os.getpid()}.part{output_path.suffix}"
        )
        if image.ndim != 3 or image.shape[2] not in {3, 4}:
            raise ValueError("出力静止画はRGBまたはRGBAである必要があります。")
        if image.shape[2] == 4:
            encoded = cv2.cvtColor(image, cv2.COLOR_RGBA2BGRA)
        else:
            encoded = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        if not cv2.imwrite(str(temp_output_path), encoded):
            raise RuntimeError(f"静止画を書き込めません: {temp_output_path}")
        temp_output_path.replace(output_path)

    def _read_shot_time(self, video_path: Path, video_info: dict) -> pd.Timestamp:
        creation_time = self._find_creation_time(video_info)
        if creation_time:
            return to_utc_timestamp(creation_time)
        raise ValueError(f"動画にcreation_timeメタデータがありません: {video_path}")

    def _read_video_shot_time(
        self,
        video_path: Path,
        video_info: dict,
    ) -> pd.Timestamp:
        raw_shot_time = self._read_shot_time(video_path, video_info)
        offset_seconds = self._media_time_offset_for(raw_shot_time)
        if offset_seconds == 0.0:
            return raw_shot_time
        adjusted = raw_shot_time + pd.Timedelta(seconds=offset_seconds)
        logger.info(
            "media_time_offset path=%s offset_seconds=%.3f raw_shot_time=%s "
            "shot_time=%s",
            video_path,
            offset_seconds,
            raw_shot_time,
            adjusted,
        )
        return adjusted

    def _media_time_offset_for(self, shot_time: pd.Timestamp) -> float:
        rules = self._load_media_time_offset_rules()
        offset_seconds = 0.0
        for rule in rules:
            if shot_time >= rule.start_time:
                offset_seconds = rule.offset_seconds
            else:
                break
        return offset_seconds

    def _load_media_time_offset_rules(self) -> tuple[_MediaTimeOffsetRule, ...]:
        if self._media_time_offset_rules is not None:
            return self._media_time_offset_rules
        rules: list[_MediaTimeOffsetRule] = []
        for item in self.config.media_time_offsets:
            video_path = self.config.mp4_dir / item.from_file
            if not video_path.is_file():
                raise FileNotFoundError(
                    "processing.media_time_offsets.fromの動画が見つかりません: "
                    f"{video_path}"
                )
            video_info = ffmpeg.probe(
                str(video_path),
                cmd=str(self.config.ffprobe_binary),
            )
            rules.append(
                _MediaTimeOffsetRule(
                    start_time=self._read_shot_time(video_path, video_info),
                    offset_seconds=item.offset_seconds,
                    from_file=item.from_file,
                )
            )
        rules.sort(key=lambda rule: rule.start_time)
        for previous, current in zip(rules, rules[1:]):
            if previous.start_time == current.start_time:
                raise ValueError(
                    "processing.media_time_offsets.fromの動画時刻が重複しています: "
                    f"{previous.from_file}, {current.from_file}"
                )
        self._media_time_offset_rules = tuple(rules)
        if self._media_time_offset_rules:
            logger.info(
                "media_time_offset_rules %s",
                [
                    {
                        "from": rule.from_file,
                        "start_time": str(rule.start_time),
                        "offset_seconds": rule.offset_seconds,
                    }
                    for rule in self._media_time_offset_rules
                ],
            )
        return self._media_time_offset_rules

    @staticmethod
    def _find_creation_time(video_info: dict) -> object | None:
        for stream in video_info.get("streams", ()):
            creation_time = stream.get("tags", {}).get("creation_time")
            if creation_time:
                return creation_time
        return video_info.get("format", {}).get("tags", {}).get("creation_time")

    def _log_media_data_coverage(
        self,
        media_path: Path,
        shot_time: pd.Timestamp,
        duration: float,
        overlays: list[OverlaySpec],
    ) -> None:
        data = next(
            (
                spec.frame_maker.data
                for spec in overlays
                if spec.frame_maker.data is not None
                and not spec.frame_maker.data.empty
            ),
            None,
        )
        if data is None:
            return

        end_time = shot_time + pd.Timedelta(seconds=duration)
        data_start = data.index[0]
        data_end = data.index[-1]
        if end_time < data_start or shot_time > data_end:
            logger.warning(
                "media_outside_fit_range path=%s media_start=%s media_end=%s "
                "fit_start=%s fit_end=%s",
                media_path,
                shot_time,
                end_time,
                data_start,
                data_end,
            )
            return

        missing_start_seconds = max(
            0.0,
            (data_start - shot_time).total_seconds(),
        )
        missing_end_seconds = max(
            0.0,
            (end_time - data_end).total_seconds(),
        )
        if missing_start_seconds > 0.0 or missing_end_seconds > 0.0:
            logger.warning(
                "media_partly_outside_fit_range path=%s missing_start_seconds=%.1f "
                "missing_end_seconds=%.1f media_start=%s media_end=%s "
                "fit_start=%s fit_end=%s",
                media_path,
                missing_start_seconds,
                missing_end_seconds,
                shot_time,
                end_time,
                data_start,
                data_end,
            )

    def _setup_fifos(
        self, overlays: list[OverlaySpec], fifo_dir: Path
    ) -> list[_OverlayFifo]:
        fifo_infos = []
        for spec in overlays:
            # frame 0 をここで1度だけ描画してサイズ取得に使い、スレッドへ渡す。
            with _timed_step("make_first_frame", overlay=spec.config.id):
                first_frame = spec.frame_maker.make_frame(0.0)
            if spec.frame_maker.has_alpha:
                first_frame = self._rgba_frame(first_frame)
            height, width = first_frame.shape[:2]
            fifo_path = fifo_dir / spec.config.id
            os.mkfifo(fifo_path)
            fifo_infos.append(
                _OverlayFifo(
                    spec=spec,
                    path=fifo_path,
                    width=width,
                    height=height,
                    first_frame=first_frame,
                )
            )
        return fifo_infos

    def _write_frames_to_fifo_safe(
        self,
        fi: _OverlayFifo,
        duration: float,
        errors: list[BaseException],
        errors_lock: threading.Lock,
    ) -> None:
        try:
            self._write_frames_to_fifo(fi, duration)
        except Exception as exc:
            logger.exception(
                "write_frames_to_fifo failed overlay=%s",
                fi.spec.config.id,
            )
            with errors_lock:
                errors.append(exc)

    def _write_frames_to_fifo(self, fi: _OverlayFifo, duration: float) -> None:
        frame_maker = fi.spec.frame_maker
        frame_count = max(1, int(np.ceil(duration * frame_maker.fps)))
        with _timed_step(
            "write_frames_to_fifo",
            overlay=fi.spec.config.id,
            frames=frame_count,
            fps=f"{frame_maker.fps:.3f}",
        ):
            with open(fi.path, "wb") as f:
                # _setup_fifosで描画済みのframe 0 を先頭に書き、frame 1 から再描画する。
                f.write(np.ascontiguousarray(fi.first_frame).tobytes())
                for frame_index in range(1, frame_count):
                    seconds = frame_index / frame_maker.fps
                    frame = frame_maker.make_frame(seconds)
                    if frame_maker.has_alpha:
                        frame = self._rgba_frame(frame)
                    f.write(np.ascontiguousarray(frame).tobytes())

    @staticmethod
    def _rgba_frame(frame: np.ndarray) -> np.ndarray:
        if frame.ndim != 3:
            raise ValueError("overlay frameは3次元配列である必要があります。")
        if frame.shape[2] == 4:
            return np.ascontiguousarray(frame)
        if frame.shape[2] != 3:
            raise ValueError("overlay frameはRGBまたはRGBAである必要があります。")
        alpha = np.full((*frame.shape[:2], 1), 255, dtype=np.uint8)
        return np.ascontiguousarray(np.concatenate([frame, alpha], axis=2))

    @staticmethod
    def _stream_frame_rate(video_stream: dict) -> float:
        for key in ("avg_frame_rate", "r_frame_rate"):
            value = video_stream.get(key)
            if not value or value == "0/0":
                continue
            try:
                fps = float(Fraction(str(value)))
            except (ValueError, ZeroDivisionError):
                continue
            if fps > 0:
                return fps
        return 30.0

    def _compose_video(
        self,
        video_path: Path,
        fifo_infos: list[_OverlayFifo],
        *,
        video_width: int,
        video_height: int,
        video_length: float,
        video_fps: float,
        layout_scale: float,
        has_audio: bool,
    ) -> None:
        input_options = {}
        if self.config.noautorotate:
            input_options["noautorotate"] = None
        source = ffmpeg.input(str(video_path), **input_options)
        transparent_output = self.config.output_mode == "transparent_overlay"
        if transparent_output:
            composed = ffmpeg.input(
                (
                    f"color=color=black:s={video_width}x{video_height}:"
                    f"d={video_length}:r={video_fps}"
                ),
                format="lavfi",
            ).filter("colorchannelmixer", aa=0).filter("format", "rgba")
        else:
            composed = source.video
        # JSON配列の順番を重なり順として、任意個のoverlayを合成する。
        for fi in fifo_infos:
            pix_fmt = "rgba" if fi.spec.frame_maker.has_alpha else "rgb24"
            layer = ffmpeg.input(
                str(fi.path),
                format="rawvideo",
                pix_fmt=pix_fmt,
                s=f"{fi.width}x{fi.height}",
                r=fi.spec.frame_maker.fps,
            )
            if layout_scale != 1.0:
                layer = layer.filter(
                    "scale",
                    max(2, int(round(fi.width * layout_scale))),
                    max(2, int(round(fi.height * layout_scale))),
                )
            composed = ffmpeg.overlay(
                composed,
                layer,
                x=max(0, int(round(fi.spec.config.x * layout_scale))),
                y=max(0, int(round(fi.spec.config.y * layout_scale))),
            )

        if transparent_output:
            output_path = self.config.output_dir / f"{video_path.stem}_overlay.mov"
            output_options = self._transparent_overlay_output_options()
            copy_audio = False
        else:
            output_path = self.config.output_dir / f"{video_path.stem}_output.mp4"
            output_options = self._composited_output_options()
            copy_audio = self.config.copy_audio and has_audio
        temp_output_path = (
            self.config.output_dir
            / f".{output_path.stem}.{os.getpid()}.part{output_path.suffix}"
        )
        logger.info(
            "ffmpeg_output path=%s mode=%s codec=%s copy_audio=%s",
            output_path,
            self.config.output_mode,
            output_options["vcodec"],
            copy_audio,
        )
        if copy_audio:
            # 映像だけを再エンコードし、元動画の音声は無劣化でコピーする。
            output = ffmpeg.output(
                composed,
                source.audio,
                str(temp_output_path),
                acodec="copy",
                **output_options,
            )
        else:
            output = ffmpeg.output(
                composed,
                str(temp_output_path),
                **output_options,
            )
        try:
            ffmpeg.run(
                output,
                cmd=str(self.config.ffmpeg_binary),
                overwrite_output=True,
                capture_stderr=True,
            )
            temp_output_path.replace(output_path)
        except ffmpeg.Error as exc:
            stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
            logger.error("ffmpeg failed path=%s stderr:\n%s", video_path, stderr)
            temp_output_path.unlink(missing_ok=True)
            raise

    def _composited_output_options(self) -> dict[str, object]:
        output_options: dict[str, object] = {
            "vcodec": self.config.video_codec,
            "preset": self.config.video_preset,
            "pix_fmt": self.config.pixel_format,
            "movflags": "+faststart",
        }
        if self.config.video_codec.endswith("_nvenc"):
            # NVENCはCRFではなくCQで品質を指定する。
            output_options["cq"] = self.config.video_cq
        else:
            output_options["crf"] = self.config.video_crf
        return output_options

    @staticmethod
    def _transparent_overlay_output_options() -> dict[str, object]:
        return {
            "vcodec": "qtrle",
            "pix_fmt": "argb",
            "movflags": "+faststart",
        }
