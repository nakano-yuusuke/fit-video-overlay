"""POIマーカー描画の共通処理。"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import cv2
import numpy as np

from .image_overlay import load_rgba_icon, overlay_rgba_center
from .poi import PointOfInterest
from .text_draw import draw_centered_text


def load_poi_icons(
    points_of_interest: tuple[PointOfInterest, ...],
    *,
    icon_size_override: tuple[int, int] | None = None,
) -> dict[str, np.ndarray]:
    """POIごとのPNGアイコンを読み込む。"""
    icons: dict[str, np.ndarray] = {}
    cache: dict[tuple[Path, tuple[int, int] | None], np.ndarray] = {}
    for poi in points_of_interest:
        if poi.icon_path is None:
            continue
        icon_size = icon_size_override or poi.icon_size
        key = (poi.icon_path, icon_size)
        if key not in cache:
            cache[key] = load_rgba_icon(poi.icon_path, icon_size)
        icons[poi.id] = cache[key]
    return icons


def draw_poi_marker(
    image: np.ndarray,
    poi: PointOfInterest,
    x: int,
    y: int,
    *,
    icons: Mapping[str, np.ndarray],
    color: tuple[int, int, int],
    font_path: Path | None,
    font_size: int,
    thickness: int,
) -> int:
    """POIマーカーを描き、ラベル開始位置のXオフセットを返す。"""
    icon = icons.get(poi.id)
    if icon is not None:
        overlay_rgba_center(image, icon, x, y)
        return max(7, icon.shape[1] // 2 + 6)

    if poi.emoji:
        rendered = draw_centered_text(
            image,
            poi.emoji,
            (x, y),
            color=color,
            font_path=font_path,
            font_size=font_size,
            stroke_width=max(0, thickness - 1),
            stroke_fill=(0, 0, 0),
        )
        image[:, :] = rendered
        return max(7, font_size // 2 + 8)

    cv2.circle(image, (x, y), 5, _draw_color(image, (0, 0, 0)), -1, cv2.LINE_AA)
    cv2.circle(image, (x, y), 4, _draw_color(image, color), -1, cv2.LINE_AA)
    return 7


def _draw_color(image: np.ndarray, color: tuple[int, int, int]) -> tuple[int, ...]:
    if image.ndim == 3 and image.shape[2] == 4:
        return (*color, 255)
    return color
