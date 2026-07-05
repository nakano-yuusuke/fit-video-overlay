"""RGBAアイコンの読み込みと合成ユーティリティ。"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def load_rgba_icon(
    path: Path,
    icon_size: tuple[int, int] | None = None,
) -> np.ndarray:
    """PNGなどの画像をRGBA配列として読み込む。"""
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise FileNotFoundError(f"アイコン画像を読み込めません: {path}")

    if image.ndim == 2:
        rgba = cv2.cvtColor(image, cv2.COLOR_GRAY2RGBA)
    elif image.ndim == 3 and image.shape[2] == 3:
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        alpha = np.full((*rgb.shape[:2], 1), 255, dtype=np.uint8)
        rgba = np.concatenate([rgb, alpha], axis=2)
    elif image.ndim == 3 and image.shape[2] == 4:
        rgba = cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA)
    else:
        raise ValueError(f"未対応のアイコン画像形式です: {path}")

    if icon_size is not None:
        rgba = cv2.resize(rgba, icon_size, interpolation=cv2.INTER_AREA)
    return rgba


def overlay_rgba_center(
    background: np.ndarray,
    icon: np.ndarray,
    cx: int,
    cy: int,
) -> None:
    """RGBAアイコンを中心座標指定でRGB/RGBA画像へ合成する。"""
    icon_height, icon_width = icon.shape[:2]
    x0 = cx - icon_width // 2
    y0 = cy - icon_height // 2
    x1 = max(0, x0)
    y1 = max(0, y0)
    x2 = min(background.shape[1], x0 + icon_width)
    y2 = min(background.shape[0], y0 + icon_height)
    if x1 >= x2 or y1 >= y2:
        return

    icon_crop = icon[
        y1 - y0 : y2 - y0,
        x1 - x0 : x2 - x0,
    ]
    alpha = icon_crop[..., 3:4].astype(np.float32) / 255.0
    target = background[y1:y2, x1:x2].astype(np.float32)
    if background.shape[2] == 4:
        target_alpha = target[..., 3:4] / 255.0
        output_alpha = alpha + target_alpha * (1.0 - alpha)
        numerator = (
            icon_crop[..., :3].astype(np.float32) * alpha
            + target[..., :3] * target_alpha * (1.0 - alpha)
        )
        output_rgb = np.divide(
            numerator,
            output_alpha,
            out=np.zeros_like(numerator),
            where=output_alpha > 0,
        )
        background[y1:y2, x1:x2, :3] = output_rgb.astype(np.uint8)
        background[y1:y2, x1:x2, 3:4] = (
            output_alpha * 255
        ).astype(np.uint8)
        return

    blended = (
        icon_crop[..., :3].astype(np.float32) * alpha
        + target * (1 - alpha)
    )
    background[y1:y2, x1:x2] = blended.astype(np.uint8)
