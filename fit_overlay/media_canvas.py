"""縦横比を維持したメディアcanvas配置の計算。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContainGeometry:
    source_width: int
    source_height: int
    canvas_width: int
    canvas_height: int
    content_width: int
    content_height: int
    offset_x: int
    offset_y: int

    @property
    def needs_resize(self) -> bool:
        return (self.content_width, self.content_height) != (
            self.source_width,
            self.source_height,
        )

    @property
    def needs_padding(self) -> bool:
        return (self.content_width, self.content_height) != (
            self.canvas_width,
            self.canvas_height,
        )


def contain_geometry(
    source_width: int,
    source_height: int,
    canvas_width: int,
    canvas_height: int,
) -> ContainGeometry:
    """入力を切り取らずcanvasへ中央配置する偶数サイズを返す。"""
    if min(source_width, source_height, canvas_width, canvas_height) <= 0:
        raise ValueError("sourceとcanvasのサイズは正の値で指定してください。")

    scale = min(canvas_width / source_width, canvas_height / source_height)
    content_width = min(
        canvas_width,
        max(2, int(round(source_width * scale))),
    )
    content_height = min(
        canvas_height,
        max(2, int(round(source_height * scale))),
    )

    # yuv420pと一般的な動画encoderで扱いやすいよう偶数にする。
    if content_width > 2:
        content_width -= content_width % 2
    if content_height > 2:
        content_height -= content_height % 2

    return ContainGeometry(
        source_width=source_width,
        source_height=source_height,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        content_width=content_width,
        content_height=content_height,
        offset_x=(canvas_width - content_width) // 2,
        offset_y=(canvas_height - content_height) // 2,
    )
