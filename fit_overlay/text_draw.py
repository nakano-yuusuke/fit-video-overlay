"""Pillowによるテキスト描画ユーティリティ。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def draw_text(
    frame: np.ndarray,
    text: str,
    position: tuple[int, int],
    *,
    color: tuple[int, int, int],
    font_path: Path | None = None,
    font_size: int = 32,
    stroke_width: int = 0,
    stroke_fill: tuple[int, int, int] | None = None,
) -> np.ndarray:
    """RGBのnumpy画像へPillowでテキストを描画して返す。"""
    image = Image.fromarray(frame)
    draw = ImageDraw.Draw(image)
    fill = _fill_color(frame, color)
    stroke = _fill_color(frame, stroke_fill or color)
    draw.text(
        position,
        text,
        font=_load_font(font_path, font_size),
        fill=fill,
        anchor="ls",
        stroke_width=stroke_width,
        stroke_fill=stroke,
    )
    return np.asarray(image)


def draw_centered_text(
    frame: np.ndarray,
    text: str,
    center: tuple[int, int],
    *,
    color: tuple[int, int, int],
    font_path: Path | None = None,
    font_size: int = 32,
    stroke_width: int = 0,
    stroke_fill: tuple[int, int, int] | None = None,
) -> np.ndarray:
    """RGBのnumpy画像へ中央揃えでテキストを描画して返す。"""
    image = Image.fromarray(frame)
    draw = ImageDraw.Draw(image)
    font = _load_font(font_path, font_size)
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    x = center[0] - (bbox[2] - bbox[0]) // 2 - bbox[0]
    y = center[1] - (bbox[3] - bbox[1]) // 2 - bbox[1]
    fill = _fill_color(frame, color)
    stroke = _fill_color(frame, stroke_fill or color)
    draw.text(
        (x, y),
        text,
        font=font,
        fill=fill,
        stroke_width=stroke_width,
        stroke_fill=stroke,
    )
    return np.asarray(image)


def font_size_from_cv_scale(font_scale: float) -> int:
    """既存のOpenCV font_scaleから大まかなPillowサイズへ変換する。"""
    return max(1, int(round(font_scale * 32)))


def _load_font(font_path: Path | None, font_size: int) -> ImageFont.ImageFont:
    if font_path is not None:
        return ImageFont.truetype(str(font_path), font_size)
    try:
        return ImageFont.truetype("DejaVuSans.ttf", font_size)
    except OSError:
        return ImageFont.load_default()


def _fill_color(
    frame: np.ndarray,
    color: tuple[int, int, int],
) -> tuple[int, ...]:
    if frame.ndim == 3 and frame.shape[2] == 4:
        return (*color, 255)
    return color
