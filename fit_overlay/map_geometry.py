"""地図表示範囲と緯度経度・pixel座標の変換。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MapGeometry:
    """移動範囲から計算した静的地図の座標情報。"""

    bbox: tuple[float, float, float, float]
    center_lon: float
    center_lat: float
    half_width_m: float
    half_height_m: float
    lon_m_per_deg: float
    lat_m_per_deg: float
    width_px: int
    height_px: int
    pixels_per_meter: float

    @classmethod
    def from_positions(
        cls,
        positions: pd.DataFrame,
        *,
        pixels_per_meter: float,
        display_width_m: float,
        display_height_m: float,
        viewport_width_px: int,
        viewport_height_px: int,
        track_margin_m: float,
    ) -> MapGeometry:
        """緯度経度の移動範囲を収める地図サイズと境界を計算する。"""
        required_columns = {"position_long", "position_lat"}
        if not required_columns.issubset(positions.columns):
            missing = required_columns.difference(positions.columns)
            raise ValueError(f"位置情報の列が不足しています: {sorted(missing)}")

        valid_positions = positions[list(required_columns)].dropna()
        if valid_positions.empty:
            raise ValueError("地図生成に利用できる位置情報がありません。")

        lon_min = float(valid_positions["position_long"].min())
        lon_max = float(valid_positions["position_long"].max())
        lat_min = float(valid_positions["position_lat"].min())
        lat_max = float(valid_positions["position_lat"].max())
        center_lon = (lon_min + lon_max) / 2
        center_lat = (lat_min + lat_max) / 2

        lon_m_per_deg = max(
            1e-9,
            111320.0 * np.cos(np.radians(center_lat)),
        )
        lat_m_per_deg = 110540.0
        route_half_width = (lon_max - lon_min) * lon_m_per_deg / 2
        route_half_height = (lat_max - lat_min) * lat_m_per_deg / 2
        raw_half_width = max(
            display_width_m / 2,
            route_half_width + track_margin_m,
        )
        raw_half_height = max(
            display_height_m / 2,
            route_half_height + track_margin_m,
        )

        margin_px = int(track_margin_m * pixels_per_meter)
        width_px = max(
            cls.even_pixel_size(2 * raw_half_width, pixels_per_meter),
            viewport_width_px + margin_px,
        )
        height_px = max(
            cls.even_pixel_size(2 * raw_half_height, pixels_per_meter),
            viewport_height_px + margin_px,
        )
        width_px += width_px % 2
        height_px += height_px % 2
        half_width_m = width_px / (2 * pixels_per_meter)
        half_height_m = height_px / (2 * pixels_per_meter)
        lon_offset = half_width_m / lon_m_per_deg
        lat_offset = half_height_m / lat_m_per_deg

        return cls(
            bbox=(
                center_lon - lon_offset,
                center_lon + lon_offset,
                center_lat - lat_offset,
                center_lat + lat_offset,
            ),
            center_lon=center_lon,
            center_lat=center_lat,
            half_width_m=half_width_m,
            half_height_m=half_height_m,
            lon_m_per_deg=lon_m_per_deg,
            lat_m_per_deg=lat_m_per_deg,
            width_px=width_px,
            height_px=height_px,
            pixels_per_meter=pixels_per_meter,
        )

    @classmethod
    def fit_positions_to_viewport(
        cls,
        positions: pd.DataFrame,
        *,
        viewport_width_px: int,
        viewport_height_px: int,
        track_margin_m: float,
    ) -> MapGeometry:
        """移動範囲全体を、縦横比を保って指定viewportへ収める。"""
        required_columns = {"position_long", "position_lat"}
        if not required_columns.issubset(positions.columns):
            missing = required_columns.difference(positions.columns)
            raise ValueError(f"位置情報の列が不足しています: {sorted(missing)}")

        valid_positions = positions[list(required_columns)].dropna()
        if valid_positions.empty:
            raise ValueError("地図生成に利用できる位置情報がありません。")

        lon_min = float(valid_positions["position_long"].min())
        lon_max = float(valid_positions["position_long"].max())
        lat_min = float(valid_positions["position_lat"].min())
        lat_max = float(valid_positions["position_lat"].max())
        center_lon = (lon_min + lon_max) / 2
        center_lat = (lat_min + lat_max) / 2
        lon_m_per_deg = max(
            1e-9,
            111320.0 * np.cos(np.radians(center_lat)),
        )
        lat_m_per_deg = 110540.0
        content_width_m = (
            (lon_max - lon_min) * lon_m_per_deg + 2 * track_margin_m
        )
        content_height_m = (
            (lat_max - lat_min) * lat_m_per_deg + 2 * track_margin_m
        )
        meters_per_pixel = max(
            content_width_m / viewport_width_px,
            content_height_m / viewport_height_px,
            1e-9,
        )
        pixels_per_meter = 1 / meters_per_pixel
        half_width_m = viewport_width_px * meters_per_pixel / 2
        half_height_m = viewport_height_px * meters_per_pixel / 2

        return cls(
            bbox=(
                center_lon - half_width_m / lon_m_per_deg,
                center_lon + half_width_m / lon_m_per_deg,
                center_lat - half_height_m / lat_m_per_deg,
                center_lat + half_height_m / lat_m_per_deg,
            ),
            center_lon=center_lon,
            center_lat=center_lat,
            half_width_m=half_width_m,
            half_height_m=half_height_m,
            lon_m_per_deg=lon_m_per_deg,
            lat_m_per_deg=lat_m_per_deg,
            width_px=viewport_width_px,
            height_px=viewport_height_px,
            pixels_per_meter=pixels_per_meter,
        )

    @staticmethod
    def even_pixel_size(meters: float, pixels_per_meter: float) -> int:
        """動画エンコーダで扱いやすい偶数pixelへ切り上げる。"""
        size = int(round(meters * pixels_per_meter))
        return size + size % 2

    def position_to_pixels(
        self,
        lon: float,
        lat: float,
        *,
        image_width: int,
        image_height: int,
        clip: bool = True,
    ) -> tuple[int, int]:
        """緯度経度を静的地図画像上のpixel座標へ変換する。"""
        delta_lon = (lon - self.center_lon) * self.lon_m_per_deg
        delta_lat = (lat - self.center_lat) * self.lat_m_per_deg
        x = round((delta_lon + self.half_width_m) * self.pixels_per_meter)
        y = round((self.half_height_m - delta_lat) * self.pixels_per_meter)
        if clip:
            x = np.clip(x, 0, image_width - 1)
            y = np.clip(y, 0, image_height - 1)
        return int(x), int(y)
