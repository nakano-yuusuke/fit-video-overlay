"""時刻・距離・高度・速度のフレーム生成。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

import cv2
import matplotlib
import numpy as np
import pandas as pd
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.ticker import FuncFormatter, MaxNLocator

from .poi import PointOfInterest
from .poi_rendering import draw_poi_marker, load_poi_icons
from .time_utils import DISPLAY_TIMEZONE, to_utc_timestamp
from .text_draw import draw_text, font_size_from_cv_scale


Formatter = Callable[[float], str]
ColorSelector = Callable[[float], tuple[int, int, int]]


class FrameMaker(ABC):
    """動画時刻から表示対象の実時刻を求めるフレーム生成の基底クラス。"""

    def __init__(self, fps: float, data: pd.DataFrame | None = None) -> None:
        self.fps = fps
        self.data = data
        self._shot_time: pd.Timestamp | None = None

    @property
    def has_alpha(self) -> bool:
        return False

    @property
    def shot_time(self) -> pd.Timestamp:
        if self._shot_time is None:
            raise RuntimeError("shot_timeが設定されていません。")
        return self._shot_time

    @shot_time.setter
    def shot_time(self, value: pd.Timestamp) -> None:
        self._shot_time = to_utc_timestamp(value)

    def frame_time(self, seconds: float) -> pd.Timestamp:
        # MoviePyから渡される秒数を一度フレーム番号へ丸めることで、
        # 浮動小数点の微小なずれによる表示値の揺れを避ける。
        frame_number = round(seconds * self.fps)
        return self.shot_time + pd.Timedelta(
            seconds=frame_number / self.fps
        )

    def prepare_video(self, shot_time: pd.Timestamp, duration: float) -> None:
        """動画ごとの事前準備。必要なサブクラスだけ上書きする。"""
        self.shot_time = shot_time

    def values_at(
        self,
        frame_time: pd.Timestamp,
        columns: list[str],
        *,
        interpolation: str,
        max_interpolation_gap_seconds: float,
    ) -> pd.Series | None:
        """指定時刻の値を、直前値または前後レコードの線形補間で返す。"""
        if self.data is None or self.data.empty:
            return None
        if any(column not in self.data.columns for column in columns):
            return None

        previous_index = self.data.index.searchsorted(
            frame_time,
            side="right",
        ) - 1
        if previous_index < 0:
            return None

        previous_values = self.data.iloc[previous_index][columns]
        if (
            interpolation != "linear"
            or previous_index >= len(self.data) - 1
            or self.data.index[previous_index] == frame_time
        ):
            return previous_values

        next_index = previous_index + 1
        previous_time = self.data.index[previous_index]
        next_time = self.data.index[next_index]
        gap_seconds = (next_time - previous_time).total_seconds()
        if (
            gap_seconds <= 0
            or gap_seconds > max_interpolation_gap_seconds
        ):
            return previous_values

        next_values = self.data.iloc[next_index][columns]
        if previous_values.isna().any() or next_values.isna().any():
            return previous_values

        elapsed_seconds = (frame_time - previous_time).total_seconds()
        ratio = elapsed_seconds / gap_seconds
        return previous_values + (next_values - previous_values) * ratio

    @abstractmethod
    def make_frame(self, seconds: float) -> np.ndarray:
        raise NotImplementedError

    def warmup(self) -> None:
        """fork 前に親プロセスで実行する静的事前レンダリング。デフォルトは何もしない。"""


class TextFrameMaker(FrameMaker):
    """背景画像へ文字を描画するオーバーレイの共通処理。"""

    def __init__(
        self,
        fps: float,
        background_path: Path | None,
        data: pd.DataFrame | None = None,
        *,
        width: int | None = None,
        height: int | None = None,
        background_color: tuple[int, int, int] | None = None,
        background_alpha: float = 1.0,
        text_position: tuple[int, int] = (20, 70),
        font_scale: float = 2.0,
        font_size: int | None = None,
        font_path: Path | None = None,
        text_color: tuple[int, int, int] = (255, 255, 255),
        text_thickness: int = 3,
    ) -> None:
        super().__init__(fps, data)
        self.background_alpha = background_alpha
        if background_path is None:
            if width is None or height is None:
                raise ValueError("単色背景にはwidth/heightが必要です。")
            rgb_background = np.full(
                (height, width, 3),
                background_color or (32, 32, 32),
                dtype=np.uint8,
            )
        else:
            # 背景画像は全フレーム共通なので、毎回ディスクから読まず保持する。
            background = cv2.imread(str(background_path))
            if background is None:
                raise FileNotFoundError(f"背景画像を読み込めません: {background_path}")
            if width is not None and height is not None:
                background = cv2.resize(background, (width, height))
            rgb_background = cv2.cvtColor(background, cv2.COLOR_BGR2RGB)
        if self.has_alpha:
            alpha = np.full(
                (*rgb_background.shape[:2], 1),
                int(round(self.background_alpha * 255)),
                dtype=np.uint8,
            )
            self.background = np.concatenate([rgb_background, alpha], axis=2)
        else:
            self.background = rgb_background
        self.text_position = text_position
        self.font_scale = font_scale
        self.font_size = font_size or font_size_from_cv_scale(font_scale)
        self.font_path = font_path
        self.text_color = text_color
        self.text_thickness = text_thickness
        self._last_text_cache_key: tuple[str, tuple[int, int, int]] | None = None
        self._last_text_frame: np.ndarray | None = None

    @property
    def has_alpha(self) -> bool:
        return self.background_alpha < 1.0

    def draw_text(self, text: str) -> np.ndarray:
        cache_key = (text, self.text_color)
        if (
            self._last_text_cache_key == cache_key
            and self._last_text_frame is not None
        ):
            return self._last_text_frame.copy()
        # 元画像を変更しないよう、フレームごとにコピーしてから文字を描く。
        frame = self.background.copy()
        rendered = draw_text(
            frame,
            text,
            self.text_position,
            color=self.text_color,
            font_path=self.font_path,
            font_size=self.font_size,
            stroke_width=max(0, self.text_thickness - 1),
        )
        self._last_text_cache_key = cache_key
        self._last_text_frame = rendered
        return rendered.copy()

    def draw_text_with_color(
        self,
        text: str,
        color: tuple[int, int, int],
    ) -> np.ndarray:
        cache_key = (text, color)
        if (
            self._last_text_cache_key == cache_key
            and self._last_text_frame is not None
        ):
            return self._last_text_frame.copy()
        frame = self.background.copy()
        rendered = draw_text(
            frame,
            text,
            self.text_position,
            color=color,
            font_path=self.font_path,
            font_size=self.font_size,
            stroke_width=max(0, self.text_thickness - 1),
        )
        self._last_text_cache_key = cache_key
        self._last_text_frame = rendered
        return rendered.copy()


class TimeFrameMaker(TextFrameMaker):
    def __init__(
        self,
        fps: float,
        background_path: Path | None,
        *,
        timezone: str = DISPLAY_TIMEZONE,
        time_format: str = "%Y/%m/%d %H:%M:%S",
        **kwargs,
    ) -> None:
        super().__init__(fps, background_path, **kwargs)
        self.timezone = timezone
        self.time_format = time_format

    def make_frame(self, seconds: float) -> np.ndarray:
        text = self.frame_time(seconds).tz_convert(self.timezone).strftime(
            self.time_format
        )
        return self.draw_text(text)


class MetricFrameMaker(TextFrameMaker):
    """指定したFIT列を、書式変換して表示する汎用フレーム生成クラス。"""

    def __init__(
        self,
        fps: float,
        data: pd.DataFrame,
        background_path: Path | None,
        column: str,
        formatter: Formatter,
        empty_text: str = "-",
        interpolation: str = "linear",
        max_interpolation_gap_seconds: float = 2.0,
        color_selector: ColorSelector | None = None,
        **kwargs,
    ) -> None:
        super().__init__(fps, background_path, data, **kwargs)
        self.column = column
        self.has_column = column in data.columns
        self.formatter = formatter
        self.empty_text = empty_text
        self.interpolation = interpolation
        self.max_interpolation_gap_seconds = max_interpolation_gap_seconds
        self.color_selector = color_selector

    def make_frame(self, seconds: float) -> np.ndarray:
        if not self.has_column:
            return self.draw_text(f"No {self.column} data")
        frame_time = self.frame_time(seconds)
        values = self.values_at(
            frame_time,
            [self.column],
            interpolation=self.interpolation,
            max_interpolation_gap_seconds=self.max_interpolation_gap_seconds,
        )
        if values is None:
            return self.draw_text(self.empty_text)

        value = values[self.column]
        if pd.isna(value):
            return self.draw_text(self.empty_text)
        numeric_value = float(value)
        text = self.formatter(numeric_value)
        if self.color_selector is None:
            return self.draw_text(text)
        return self.draw_text_with_color(text, self.color_selector(numeric_value))


class TextColumnFrameMaker(TextFrameMaker):
    """指定した文字列列を直前値で表示するフレーム生成クラス。"""

    def __init__(
        self,
        fps: float,
        data: pd.DataFrame,
        background_path: Path | None,
        column: str,
        empty_text: str = "-",
        **kwargs,
    ) -> None:
        super().__init__(fps, background_path, data, **kwargs)
        self.column = column
        self.has_column = column in data.columns
        self.empty_text = empty_text

    def make_frame(self, seconds: float) -> np.ndarray:
        if not self.has_column:
            return self.draw_text(f"No {self.column} data")
        if self.data is None or self.data.empty:
            return self.draw_text(self.empty_text)

        frame_time = self.frame_time(seconds)
        previous_index = self.data.index.searchsorted(
            frame_time,
            side="right",
        ) - 1
        if previous_index < 0:
            return self.draw_text(self.empty_text)

        value = self.data.iloc[previous_index][self.column]
        if pd.isna(value) or str(value) == "":
            return self.draw_text(self.empty_text)
        return self.draw_text(str(value))


class GraphFrameMaker(FrameMaker):
    """指定したFIT列を時系列グラフとして表示するフレーム生成クラス。"""

    def __init__(
        self,
        fps: float,
        data: pd.DataFrame,
        column: str,
        formatter: Formatter,
        *,
        width: int,
        height: int,
        line_draw_style: str = "auto",
        multiplier: float = 1.0,
        viewport_mode: str = "follow",
        follow_anchor_ratio: float = 1.0,
        x_column: str | None = None,
        x_multiplier: float = 1.0,
        x_value_format: str | None = None,
        window_seconds: float | None = 300.0,
        y_min: float | None = None,
        y_max: float | None = None,
        interpolation: str = "linear",
        max_interpolation_gap_seconds: float = 2.0,
        sample_interval_seconds: float | None = None,
        background_color: tuple[int, int, int] = (16, 16, 16),
        background_alpha: float = 1.0,
        plot_background_color: tuple[int, int, int] | None = None,
        grid_color: tuple[int, int, int] = (64, 64, 64),
        axis_color: tuple[int, int, int] = (180, 180, 180),
        line_color: tuple[int, int, int] = (80, 220, 255),
        text_color: tuple[int, int, int] = (255, 255, 255),
        line_thickness: int = 3,
        padding: tuple[int, int, int, int] = (50, 20, 20, 40),
        show_axes: bool = False,
        axes_layer_order: str = "front",
        show_x_axis_labels: bool = False,
        x_axis_nbins: int = 5,
        show_current_marker: bool = False,
        current_marker_color: tuple[int, int, int] = (255, 80, 80),
        current_marker_thickness: int = 2,
        current_marker_radius: int = 5,
        show_future_series: bool = True,
        show_future_poi: bool = True,
        show_value: bool = True,
        value_position: tuple[int, int] = (12, 34),
        value_font_scale: float = 0.9,
        value_font_size: int | None = None,
        value_font_path: Path | None = None,
        value_thickness: int = 2,
        empty_text: str = "-",
        show_poi: bool = False,
        poi_font_size: int | None = None,
        poi_font_path: Path | None = None,
        poi_color: tuple[int, int, int] = (255, 255, 255),
        poi_thickness: int = 2,
        poi_icon_size: tuple[int, int] | None = None,
        poi_match_threshold_m: float = 300.0,
        poi_route_progress_column: str = "route_progress_m",
        points_of_interest: tuple[PointOfInterest, ...] = (),
    ) -> None:
        super().__init__(fps, data)
        self.column = column
        self.has_column = column in data.columns
        self.has_x_column = x_column is None or x_column in data.columns
        self.formatter = formatter
        self.line_draw_style = line_draw_style
        self.width = width
        self.height = height
        self.multiplier = multiplier
        self.viewport_mode = viewport_mode
        self.follow_anchor_ratio = follow_anchor_ratio
        self.x_column = x_column
        self.x_multiplier = x_multiplier
        self.x_value_format = x_value_format
        self.window_seconds = window_seconds
        self.y_min = y_min
        self.y_max = y_max
        self.interpolation = interpolation
        self.max_interpolation_gap_seconds = max_interpolation_gap_seconds
        self.sample_interval_seconds = sample_interval_seconds
        self.background_color = background_color
        self.background_alpha = background_alpha
        self.plot_background_color = plot_background_color or background_color
        self.grid_color = grid_color
        self.axis_color = axis_color
        self.line_color = line_color
        self.text_color = text_color
        self.line_thickness = line_thickness
        self.padding = padding
        self.show_axes = show_axes
        self.axes_layer_order = axes_layer_order
        self.show_x_axis_labels = show_x_axis_labels
        self.x_axis_nbins = x_axis_nbins
        self.show_current_marker = show_current_marker
        self.current_marker_color = current_marker_color
        self.current_marker_thickness = current_marker_thickness
        self.current_marker_radius = current_marker_radius
        self.show_future_series = show_future_series
        self.show_future_poi = show_future_poi
        self.show_value = show_value
        self.value_position = value_position
        self.value_font_scale = value_font_scale
        self.value_font_size = value_font_size or font_size_from_cv_scale(
            value_font_scale
        )
        self.value_font_path = value_font_path
        self.value_thickness = value_thickness
        self.empty_text = empty_text
        self.show_poi = show_poi
        self.poi_font_size = poi_font_size or 22
        self.poi_font_path = poi_font_path
        self.poi_color = poi_color
        self.poi_thickness = poi_thickness
        self.poi_match_threshold_m = poi_match_threshold_m
        self.poi_route_progress_column = poi_route_progress_column
        self.points_of_interest = points_of_interest
        self.poi_icons = (
            load_poi_icons(
                points_of_interest,
                icon_size_override=poi_icon_size,
            )
            if show_poi
            else {}
        )
        self._poi_timestamp_cache: dict[str, pd.Timestamp | None] = {}

    @property
    def has_alpha(self) -> bool:
        return self.background_alpha < 1.0

    def make_frame(self, seconds: float) -> np.ndarray:
        frame_time = self.frame_time(seconds)
        frame = self._new_frame()
        if not self.has_column or not self.has_x_column:
            self._draw_value(frame, self._missing_data_text())
            return frame
        left, top, right, bottom = self.padding
        plot_left = min(left, self.width - 2)
        plot_top = min(top, self.height - 2)
        plot_right = max(plot_left + 1, self.width - right - 1)
        plot_bottom = max(plot_top + 1, self.height - bottom - 1)

        self._draw_grid(frame, plot_left, plot_top, plot_right, plot_bottom)
        series = self._series_until(frame_time)
        if series.empty:
            self._draw_value(frame, self.empty_text)
            return frame

        y_min, y_max = self._value_range(series)
        if y_min == y_max:
            y_min -= 1.0
            y_max += 1.0
        points = self._points(
            series,
            frame_time,
            y_min,
            y_max,
            plot_left,
            plot_top,
            plot_right,
            plot_bottom,
        )
        if len(points) >= 2:
            cv2.polylines(
                frame,
                [np.array(points, dtype=np.int32)],
                False,
                self._opaque_color(self.line_color),
                self.line_thickness,
                cv2.LINE_AA,
            )
        elif len(points) == 1:
            cv2.circle(
                frame,
                points[0],
                self.line_thickness + 1,
                self._opaque_color(self.line_color),
                -1,
            )

        if self.show_value:
            current_text = self._current_text(frame_time)
            self._draw_value(frame, current_text)
        return frame

    def _series_until(self, frame_time: pd.Timestamp) -> pd.Series:
        if not self.has_column:
            return pd.Series(dtype=float)
        start_time = (
            self.data.index[0]
            if self.window_seconds is None
            else frame_time - pd.Timedelta(seconds=self.window_seconds)
        )
        series = self.data.loc[start_time:frame_time, self.column]
        series = series.dropna() * self.multiplier
        return series.astype(float)

    def _value_range(self, series: pd.Series) -> tuple[float, float]:
        y_min = float(series.min()) if self.y_min is None else self.y_min
        y_max = float(series.max()) if self.y_max is None else self.y_max
        margin = (y_max - y_min) * 0.08
        if self.y_min is None:
            y_min -= margin
        if self.y_max is None:
            y_max += margin
        return y_min, y_max

    def _points(
        self,
        series: pd.Series,
        frame_time: pd.Timestamp,
        y_min: float,
        y_max: float,
        plot_left: int,
        plot_top: int,
        plot_right: int,
        plot_bottom: int,
    ) -> list[tuple[int, int]]:
        if self.window_seconds is None:
            start_time = self.data.index[0]
            total_seconds = max(
                (frame_time - start_time).total_seconds(),
                1.0,
            )
        else:
            start_time = frame_time - pd.Timedelta(seconds=self.window_seconds)
            total_seconds = self.window_seconds
        plot_width = plot_right - plot_left
        plot_height = plot_bottom - plot_top
        value_span = y_max - y_min
        x_values = self._point_x_values(series.index, frame_time)
        x_min, x_max = self._point_x_range(x_values, frame_time)
        x_span = max(x_max - x_min, 1e-9)
        points: list[tuple[int, int]] = []
        for (timestamp, value), x_value in zip(series.items(), x_values):
            if self.x_column is None:
                x_ratio = (timestamp - start_time).total_seconds() / total_seconds
            else:
                x_ratio = (x_value - x_min) / x_span
            y_ratio = (float(value) - y_min) / value_span
            x = int(round(plot_left + min(max(x_ratio, 0.0), 1.0) * plot_width))
            y = int(round(plot_bottom - min(max(y_ratio, 0.0), 1.0) * plot_height))
            points.append((x, y))
        return points

    def _point_x_values(
        self,
        index: pd.Index,
        frame_time: pd.Timestamp,
    ) -> list[float]:
        if self.x_column is None:
            return [0.0 for _ in index]
        x_series = self._x_series()
        if x_series.empty:
            return [0.0 for _ in index]
        aligned = x_series.reindex(index, method="nearest")
        return [float(value) for value in aligned]

    def _point_x_range(
        self,
        x_values: list[float],
        frame_time: pd.Timestamp,
    ) -> tuple[float, float]:
        if self.x_column is None:
            return 0.0, 1.0
        if not x_values:
            current_x = self._x_value_at(frame_time)
            if current_x is None:
                return 0.0, 1.0
            return current_x - 0.5, current_x + 0.5
        x_min = min(x_values)
        x_max = max(x_values)
        if x_min == x_max:
            return x_min - 0.5, x_max + 0.5
        return x_min, x_max

    def _x_series(self) -> pd.Series:
        if self.x_column is None or not self.has_x_column:
            return pd.Series(dtype=float)
        return (self.data[self.x_column].dropna() * self.x_multiplier).astype(float)

    def _x_value_at(self, timestamp: pd.Timestamp) -> float | None:
        if self.x_column is None or not self.has_x_column:
            return None
        values = self.values_at(
            timestamp,
            [self.x_column],
            interpolation=self.interpolation,
            max_interpolation_gap_seconds=self.max_interpolation_gap_seconds,
        )
        if values is None or pd.isna(values[self.x_column]):
            return None
        return float(values[self.x_column]) * self.x_multiplier

    def _current_text(self, frame_time: pd.Timestamp) -> str:
        if not self.has_column:
            return self._missing_data_text()
        values = self.values_at(
            frame_time,
            [self.column],
            interpolation=self.interpolation,
            max_interpolation_gap_seconds=self.max_interpolation_gap_seconds,
        )
        if values is None or pd.isna(values[self.column]):
            return self.empty_text
        return self.formatter(float(values[self.column]) * self.multiplier)

    def _missing_data_text(self) -> str:
        missing_columns = []
        if not self.has_column:
            missing_columns.append(self.column)
        if not self.has_x_column and self.x_column is not None:
            missing_columns.append(self.x_column)
        return f"No {'/'.join(missing_columns)} data"

    def _draw_grid(
        self,
        frame: np.ndarray,
        plot_left: int,
        plot_top: int,
        plot_right: int,
        plot_bottom: int,
    ) -> None:
        for index in range(1, 4):
            x = plot_left + (plot_right - plot_left) * index // 4
            cv2.line(
                frame,
                (x, plot_top),
                (x, plot_bottom),
                self._opaque_color(self.grid_color),
                1,
            )
        for index in range(1, 4):
            y = plot_top + (plot_bottom - plot_top) * index // 4
            cv2.line(
                frame,
                (plot_left, y),
                (plot_right, y),
                self._opaque_color(self.grid_color),
                1,
            )
        cv2.rectangle(
            frame,
            (plot_left, plot_top),
            (plot_right, plot_bottom),
            self._opaque_color(self.axis_color),
            1,
        )

    def _draw_value(self, frame: np.ndarray, text: str) -> None:
        rendered = draw_text(
            frame,
            text,
            self.value_position,
            color=self.text_color,
            font_path=self.value_font_path,
            font_size=self.value_font_size,
            stroke_width=max(0, self.value_thickness - 1),
        )
        frame[:, :] = rendered

    def _new_frame(self) -> np.ndarray:
        if not self.has_alpha:
            return np.full(
                (self.height, self.width, 3),
                self.background_color,
                dtype=np.uint8,
            )
        alpha = int(round(self.background_alpha * 255))
        return np.full(
            (self.height, self.width, 4),
            (*self.background_color, alpha),
            dtype=np.uint8,
        )

    def _opaque_color(self, color: tuple[int, int, int]) -> tuple[int, ...]:
        if self.has_alpha:
            return (*color, 255)
        return color


class MatplotlibStripGraphFrameMaker(GraphFrameMaker):
    """matplotlibで長尺グラフを事前生成し、各フレームで切り出す。"""

    def __init__(
        self,
        *args,
        style_path: Path | None = None,
        strip_pixels_per_second: float | None = None,
        matplotlib_dpi: int = 100,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.style_path = style_path
        self.strip_pixels_per_second = strip_pixels_per_second
        self.matplotlib_dpi = matplotlib_dpi
        self._plot_bounds = self._plot_bounds_from_padding()
        self._strip: np.ndarray | None = None
        self._strip_start_time: pd.Timestamp | None = None
        self._strip_end_time: pd.Timestamp | None = None
        self._pixels_per_second: float = 1.0
        self._axes_layer: np.ndarray | None = None
        self._y_range: tuple[float, float] = (0.0, 1.0)
        self._strip_x_min: float = 0.0
        self._strip_x_max: float = 1.0
        self._strip_cache_key: tuple | None = None

    def prepare_video(self, shot_time: pd.Timestamp, duration: float) -> None:
        super().prepare_video(shot_time, duration)
        self._prepare_strip(duration)

    def warmup(self) -> None:
        """動画間で共通な長尺グラフをfork前に生成して共有する。"""
        if self.data is None or self.data.empty:
            return
        if self.viewport_mode == "overview" and self.window_seconds is not None:
            self._prepare_strip(self.window_seconds)

    def make_frame(self, seconds: float) -> np.ndarray:
        frame_time = self.frame_time(seconds)
        frame = self._new_frame()
        plot_left, plot_top, plot_right, plot_bottom = self._plot_bounds
        if not self.show_axes:
            self._draw_grid(frame, plot_left, plot_top, plot_right, plot_bottom)
        axes_layer = self._current_axes_layer(frame_time)
        if axes_layer is not None and self.axes_layer_order == "behind":
            self._blend_axes_layer(frame, axes_layer)
        if self._strip is not None and self.viewport_mode == "overview":
            strip = self._overview_strip_until(frame_time)
            if strip is not None:
                self._blend_rgba(
                    frame[plot_top:plot_bottom, plot_left:plot_right],
                    strip,
                )
        elif self._strip is not None:
            crop = self._crop_strip(frame_time)
            if crop is not None:
                self._blend_rgba(
                    frame[plot_top:plot_bottom, plot_left:plot_right],
                    crop,
                )
        if axes_layer is not None and self.axes_layer_order == "front":
            self._blend_axes_layer(frame, axes_layer)
        if self.show_current_marker:
            self._draw_current_marker(frame, frame_time)
        if not self.show_axes:
            cv2.rectangle(
                frame,
                (plot_left, plot_top),
                (plot_right, plot_bottom),
                self._opaque_color(self.axis_color),
                1,
            )
        if self.show_poi:
            self._draw_poi_markers(frame, frame_time)
        if self.show_value:
            self._draw_value(frame, self._current_text(frame_time))
        return frame

    def _prepare_strip(self, duration: float) -> None:
        plot_left, plot_top, plot_right, plot_bottom = self._plot_bounds
        plot_width = plot_right - plot_left
        plot_height = plot_bottom - plot_top
        data_start = self.data.index[0]
        data_end = self.data.index[-1]
        full_duration = (data_end - data_start).total_seconds()
        effective_window_seconds = (
            max(full_duration, 1.0)
            if self.viewport_mode == "overview"
            else max(self.window_seconds or duration, 1.0)
        )
        self.window_seconds = effective_window_seconds
        if self.viewport_mode == "overview":
            self._strip_start_time = data_start
            self._strip_end_time = data_end
        else:
            video_start = self.shot_time
            video_end = video_start + pd.Timedelta(seconds=duration)
            past_seconds = effective_window_seconds * self.follow_anchor_ratio
            future_seconds = effective_window_seconds * (
                1.0 - self.follow_anchor_ratio
            )
            self._strip_start_time = max(
                data_start,
                video_start - pd.Timedelta(seconds=past_seconds),
            )
            self._strip_end_time = min(
                data_end,
                video_end + pd.Timedelta(seconds=future_seconds),
            )
        if self.viewport_mode == "overview":
            self._pixels_per_second = plot_width / self._x_span()
        else:
            self._pixels_per_second = self._follow_pixels_per_unit(
                effective_window_seconds,
                plot_width,
            )
        strip_duration = (
            self._strip_end_time - self._strip_start_time
        ).total_seconds()
        if self.x_column is not None:
            self._strip_x_min, self._strip_x_max = self._x_range_for_time_range(
                self._strip_start_time,
                self._strip_end_time,
            )
            strip_span = max(self._strip_x_max - self._strip_x_min, 1.0)
            strip_width = max(
                plot_width,
                int(round(strip_span * self._pixels_per_second)),
            )
        else:
            self._strip_x_min = 0.0
            self._strip_x_max = max(strip_duration, 1.0)
            strip_width = max(
                plot_width,
                int(round(strip_duration * self._pixels_per_second)),
            )
        if self.viewport_mode == "overview":
            strip_width = plot_width
        cache_key = (
            self.viewport_mode,
            self._strip_start_time,
            self._strip_end_time,
            plot_width,
            plot_height,
            strip_width,
            round(self._pixels_per_second, 8),
            round(self._strip_x_min, 8),
            round(self._strip_x_max, 8),
            self.column,
            self.multiplier,
            self.x_column,
            self.x_multiplier,
            self.y_min,
            self.y_max,
            self.interpolation,
            self.max_interpolation_gap_seconds,
            self.sample_interval_seconds,
            self.line_draw_style,
            self.style_path,
            self.matplotlib_dpi,
            self.show_axes,
            self.axes_layer_order,
            self.show_x_axis_labels,
        )
        if self._strip_cache_key == cache_key:
            return
        series = self._strip_series()
        if series.empty:
            self._strip = np.full(
                (plot_height, strip_width, 4),
                (0, 0, 0, 0),
                dtype=np.uint8,
            )
            self._axes_layer = self._render_axes_layer(0.0, 1.0)
            self._strip_cache_key = cache_key
            return
        y_min, y_max = self._value_range(series)
        if y_min == y_max:
            y_min -= 1.0
            y_max += 1.0
        self._y_range = (y_min, y_max)
        self._strip = self._render_strip(series, strip_width, plot_height, y_min, y_max)
        self._axes_layer = (
            None
            if self._uses_dynamic_follow_x_axis()
            else self._render_axes_layer(y_min, y_max)
        )
        self._strip_cache_key = cache_key

    def _follow_pixels_per_unit(
        self,
        effective_window_seconds: float,
        plot_width: int,
    ) -> float:
        if self.x_column is None:
            return (
                self.strip_pixels_per_second
                if self.strip_pixels_per_second is not None
                else plot_width / effective_window_seconds
            )
        if self._strip_start_time is None or self._strip_end_time is None:
            return 1.0
        strip_duration = max(
            (self._strip_end_time - self._strip_start_time).total_seconds(),
            1.0,
        )
        x_min, x_max = self._x_range_for_time_range(
            self._strip_start_time,
            self._strip_end_time,
        )
        strip_x_span = max(x_max - x_min, 1.0)
        visible_x_span = max(
            strip_x_span * effective_window_seconds / strip_duration,
            1.0,
        )
        return plot_width / visible_x_span

    def _strip_series(self) -> pd.Series:
        if self._strip_start_time is None or self._strip_end_time is None:
            return pd.Series(dtype=float)
        return self._sample_series(
            self._strip_start_time,
            self._strip_end_time,
        )

    def _sample_series(
        self,
        start_time: pd.Timestamp,
        end_time: pd.Timestamp,
    ) -> pd.Series:
        if end_time < start_time:
            return pd.Series(dtype=float)
        sample_seconds = (
            self.sample_interval_seconds
            if self.sample_interval_seconds is not None
            else max(1.0 / max(self._pixels_per_second, 1.0), 0.2)
        )
        interval = pd.Timedelta(seconds=sample_seconds)
        timestamps = pd.date_range(
            start_time,
            end_time,
            freq=interval,
        )
        if timestamps.empty or timestamps[-1] < end_time:
            timestamps = timestamps.append(pd.DatetimeIndex([end_time]))
        values: list[float] = []
        valid_timestamps: list[pd.Timestamp] = []
        for timestamp in timestamps:
            row = self.values_at(
                timestamp,
                [self.column],
                interpolation=self.interpolation,
                max_interpolation_gap_seconds=self.max_interpolation_gap_seconds,
            )
            if row is None or pd.isna(row[self.column]):
                continue
            values.append(float(row[self.column]) * self.multiplier)
            valid_timestamps.append(timestamp)
        return pd.Series(values, index=valid_timestamps, dtype=float)

    def _render_strip(
        self,
        series: pd.Series,
        strip_width: int,
        plot_height: int,
        y_min: float,
        y_max: float,
    ) -> np.ndarray:
        style_context = (
            plt.style.context(str(self.style_path))
            if self.style_path is not None
            else plt.style.context({})
        )
        with style_context:
            figure = plt.Figure(
                figsize=(
                    strip_width / self.matplotlib_dpi,
                    plot_height / self.matplotlib_dpi,
                ),
                dpi=self.matplotlib_dpi,
                frameon=False,
            )
            canvas = FigureCanvasAgg(figure)
            axes = figure.add_axes((0, 0, 1, 1))
            axes.set_axis_off()
            axes.set_xlim(0, strip_width - 1)
            axes.set_ylim(y_min, y_max)
            axes.patch.set_alpha(0.0)
            figure.patch.set_alpha(0.0)
            x_values = self._strip_x_values(series.index)
            axes.plot(
                x_values,
                series.to_numpy(dtype=float),
                drawstyle=self._matplotlib_drawstyle(),
            )
            canvas.draw()
            rgba = np.asarray(canvas.buffer_rgba())
        rendered = rgba.copy()
        if rendered.shape[0] != plot_height or rendered.shape[1] != strip_width:
            rendered = cv2.resize(
                rendered,
                (strip_width, plot_height),
                interpolation=cv2.INTER_AREA,
            )
        return rendered

    def _matplotlib_drawstyle(self) -> str:
        if self.line_draw_style == "linear":
            return "default"
        if self.line_draw_style == "steps-post":
            return "steps-post"
        return "steps-post" if self.interpolation == "previous" else "default"

    def _crop_strip(self, frame_time: pd.Timestamp) -> np.ndarray | None:
        if self._strip is None or self._strip_start_time is None:
            return None
        plot_left, _, plot_right, _ = self._plot_bounds
        plot_width = plot_right - plot_left
        anchor_x = self._frame_strip_x(frame_time)
        left_x = int(round(anchor_x - plot_width * self.follow_anchor_ratio))
        output = np.full(
            (self._strip.shape[0], plot_width, 4),
            (0, 0, 0, 0),
            dtype=np.uint8,
        )
        source_left = max(left_x, 0)
        source_right = min(left_x + plot_width, self._strip.shape[1])
        if source_left >= source_right:
            return output
        dest_left = source_left - left_x
        dest_right = dest_left + (source_right - source_left)
        output[:, dest_left:dest_right] = self._strip[:, source_left:source_right]
        return output

    def _overview_strip_until(self, frame_time: pd.Timestamp) -> np.ndarray | None:
        if self._strip is None:
            return None
        if self.show_future_series:
            return self._strip
        plot_width = self._strip.shape[1]
        current_x = min(max(self._frame_x(frame_time), 0), plot_width - 1)
        output = np.full_like(self._strip, (0, 0, 0, 0))
        output[:, : current_x + 1] = self._strip[:, : current_x + 1]
        return output

    def _time_to_strip_x(self, timestamp: pd.Timestamp) -> int:
        if self._strip_start_time is None:
            return 0
        seconds = (timestamp - self._strip_start_time).total_seconds()
        return int(round(seconds * self._pixels_per_second))

    def _frame_strip_x(self, timestamp: pd.Timestamp) -> int:
        if self.x_column is None:
            return self._time_to_strip_x(timestamp)
        value = self._x_value_at(timestamp)
        if value is None:
            return 0
        return self._x_value_to_strip_x(value)

    def _x_value_to_strip_x(self, value: float) -> int:
        return int(round((value - self._strip_x_min) * self._pixels_per_second))

    def _draw_current_marker(
        self,
        frame: np.ndarray,
        frame_time: pd.Timestamp,
    ) -> None:
        plot_left, plot_top, plot_right, plot_bottom = self._plot_bounds
        if self.viewport_mode == "overview":
            x = plot_left + self._frame_x(frame_time)
        else:
            x = plot_left + int(
                round((plot_right - plot_left) * self.follow_anchor_ratio)
            )
        x = min(max(x, plot_left), plot_right - 1)
        cv2.line(
            frame,
            (x, plot_top),
            (x, plot_bottom),
            self._opaque_color(self.current_marker_color),
            self.current_marker_thickness,
            cv2.LINE_AA,
        )
        values = self.values_at(
            frame_time,
            [self.column],
            interpolation=self.interpolation,
            max_interpolation_gap_seconds=self.max_interpolation_gap_seconds,
        )
        if values is None or pd.isna(values[self.column]):
            return
        y_min, y_max = self._y_range
        if y_min == y_max:
            return
        value = float(values[self.column]) * self.multiplier
        y_ratio = (value - y_min) / (y_max - y_min)
        y = int(round(plot_bottom - min(max(y_ratio, 0.0), 1.0) * (plot_bottom - plot_top)))
        cv2.circle(
            frame,
            (x, y),
            self.current_marker_radius,
            self._opaque_color(self.current_marker_color),
            -1,
            cv2.LINE_AA,
        )

    def _plot_bounds_from_padding(self) -> tuple[int, int, int, int]:
        left, top, right, bottom = self.padding
        plot_left = min(left, self.width - 2)
        plot_top = min(top, self.height - 2)
        plot_right = max(plot_left + 1, self.width - right - 1)
        plot_bottom = max(plot_top + 1, self.height - bottom - 1)
        return plot_left, plot_top, plot_right, plot_bottom

    def _current_axes_layer(self, frame_time: pd.Timestamp) -> np.ndarray | None:
        if not self._uses_dynamic_follow_x_axis():
            return self._axes_layer
        return self._render_axes_layer(*self._y_range, frame_time=frame_time)

    def _uses_dynamic_follow_x_axis(self) -> bool:
        return self.viewport_mode == "follow" and self.x_column is not None

    def _render_axes_layer(
        self,
        y_min: float,
        y_max: float,
        *,
        frame_time: pd.Timestamp | None = None,
    ) -> np.ndarray | None:
        if not self.show_axes:
            return None
        plot_left, plot_top, plot_right, plot_bottom = self._plot_bounds
        figure_width = max(self.width, 2)
        figure_height = max(self.height, 2)
        style_context = (
            plt.style.context(str(self.style_path))
            if self.style_path is not None
            else plt.style.context({})
        )
        with style_context:
            figure = plt.Figure(
                figsize=(
                    figure_width / self.matplotlib_dpi,
                    figure_height / self.matplotlib_dpi,
                ),
                dpi=self.matplotlib_dpi,
                frameon=False,
            )
            canvas = FigureCanvasAgg(figure)
            figure.patch.set_alpha(0.0)
            axes = figure.add_axes(
                (
                    plot_left / figure_width,
                    (figure_height - plot_bottom) / figure_height,
                    (plot_right - plot_left) / figure_width,
                    (plot_bottom - plot_top) / figure_height,
                )
            )
            axes.patch.set_alpha(0.0)
            axes.set_xlim(self._axis_limits(frame_time))
            axes.set_ylim(y_min, y_max)
            axes.grid(True)
            axes.tick_params(axis="x", labelbottom=self.show_x_axis_labels)
            axes.xaxis.set_major_locator(MaxNLocator(nbins=self.x_axis_nbins))
            axes.xaxis.set_major_formatter(
                FuncFormatter(self._x_tick_formatter())
            )
            canvas.draw()
            rgba = np.asarray(canvas.buffer_rgba())
        rendered = rgba.copy()
        if rendered.shape[0] != figure_height or rendered.shape[1] != figure_width:
            rendered = cv2.resize(
                rendered,
                (figure_width, figure_height),
                interpolation=cv2.INTER_AREA,
            )
        return rendered

    def _x_tick_formatter(self) -> FuncFormatter:
        if self.x_column is not None:
            return FuncFormatter(lambda value, _: self._format_x_value(value))
        return self._elapsed_tick_formatter()

    def _elapsed_tick_formatter(self) -> FuncFormatter:
        if self.viewport_mode == "overview":
            x_min = 0.0
            x_max = float(self.window_seconds)
        else:
            x_min = -float(self.window_seconds)
            x_max = 0.0
        edge_margin = max((x_max - x_min) * 0.02, 1.0)

        def formatter(value: float, _: int) -> str:
            if value <= x_min + edge_margin or value >= x_max - edge_margin:
                return ""
            return self._format_elapsed_tick(value)

        return FuncFormatter(formatter)

    def _format_x_value(self, value: float) -> str:
        if self.x_value_format is not None:
            return self.x_value_format.format(value=value)
        return f"{value:g}"

    def _x_series(self) -> pd.Series | None:
        if self.x_column is None or not self.has_x_column:
            return None
        return (self.data[self.x_column].dropna() * self.x_multiplier).astype(float)

    def _x_range(self) -> tuple[float, float]:
        x_series = self._x_series()
        if x_series is None or x_series.empty:
            return 0.0, self.window_seconds or 1.0
        return float(x_series.iloc[0]), float(x_series.iloc[-1])

    def _x_range_for_time_range(
        self,
        start_time: pd.Timestamp,
        end_time: pd.Timestamp,
    ) -> tuple[float, float]:
        x_series = self._x_series()
        if x_series is None or x_series.empty:
            return 0.0, self.window_seconds or 1.0
        window = x_series.loc[start_time:end_time].dropna()
        if window.empty:
            start_value = self._x_value_at(start_time)
            end_value = self._x_value_at(end_time)
            values = [
                value
                for value in (start_value, end_value)
                if value is not None and np.isfinite(value)
            ]
            if not values:
                return self._x_range()
            return min(values), max(values)
        return float(window.iloc[0]), float(window.iloc[-1])

    def _x_value_at(self, timestamp: pd.Timestamp) -> float | None:
        if self.x_column is None or not self.has_x_column:
            return None
        values = self.values_at(
            timestamp,
            [self.x_column],
            interpolation=self.interpolation,
            max_interpolation_gap_seconds=self.max_interpolation_gap_seconds,
        )
        if values is None or pd.isna(values[self.x_column]):
            return None
        return float(values[self.x_column]) * self.x_multiplier

    def _x_span(self) -> float:
        x_min, x_max = self._x_range()
        return max(x_max - x_min, 1.0)

    def _axis_limits(
        self,
        frame_time: pd.Timestamp | None = None,
    ) -> tuple[float, float]:
        if self.viewport_mode == "overview":
            return self._overview_axis_limits()
        if self.x_column is not None and frame_time is not None:
            return self._follow_x_axis_limits(frame_time)
        return -float(self.window_seconds), 0.0

    def _overview_axis_limits(self) -> tuple[float, float]:
        if self.x_column is None:
            return 0.0, self.window_seconds
        return self._x_range()

    def _follow_x_axis_limits(
        self,
        frame_time: pd.Timestamp,
    ) -> tuple[float, float]:
        current_x = self._x_value_at(frame_time)
        if current_x is None:
            left_x = self._strip_x_min
        else:
            anchor_x = self._x_value_to_strip_x(current_x)
            plot_left, _, plot_right, _ = self._plot_bounds
            plot_width = plot_right - plot_left
            left_pixel = anchor_x - plot_width * self.follow_anchor_ratio
            left_x = self._strip_x_min + left_pixel / self._pixels_per_second
        plot_left, _, plot_right, _ = self._plot_bounds
        visible_span = (plot_right - plot_left) / max(self._pixels_per_second, 1e-9)
        return left_x, left_x + visible_span

    def _strip_x_values(self, index: pd.Index) -> list[float]:
        if self.x_column is None:
            return [self._time_to_strip_x(timestamp) for timestamp in index]
        x_series = self._x_series()
        if x_series is None or x_series.empty:
            return [0.0 for _ in index]
        aligned = x_series.reindex(index, method="nearest")
        return [self._x_value_to_strip_x(float(value)) for value in aligned]

    def _frame_x(self, frame_time: pd.Timestamp) -> int:
        if self.x_column is None:
            return self._time_to_strip_x(frame_time)
        value = self._x_value_at(frame_time)
        if value is None:
            return 0
        x_min, x_max = self._x_range()
        plot_left, _, plot_right, _ = self._plot_bounds
        plot_width = plot_right - plot_left
        span = max(x_max - x_min, 1.0)
        return int(round(min(max((value - x_min) / span, 0.0), 1.0) * plot_width))

    def _draw_poi_markers(
        self,
        frame: np.ndarray,
        frame_time: pd.Timestamp,
    ) -> None:
        if not self.points_of_interest:
            return
        plot_left, plot_top, plot_right, plot_bottom = self._plot_bounds
        label_rows = max(
            1,
            (plot_bottom - plot_top) // max(self.poi_font_size + 4, 1),
        )

        displayed_index = 0
        for poi in self.points_of_interest:
            x = self._poi_frame_x(poi, frame_time)
            if x is None or x < plot_left or x > plot_right:
                continue
            cv2.line(
                frame,
                (x, plot_top),
                (x, plot_bottom),
                self._opaque_color(self.poi_color),
                1,
                cv2.LINE_AA,
            )
            label_offset = draw_poi_marker(
                frame,
                poi,
                x,
                plot_top + 6,
                icons=self.poi_icons,
                color=self.poi_color,
                font_path=self.poi_font_path,
                font_size=self.poi_font_size,
                thickness=self.poi_thickness,
            )
            row = displayed_index % min(label_rows, 3)
            y = plot_top + self.poi_font_size + 3 + row * (self.poi_font_size + 4)
            rendered = draw_text(
                frame,
                poi.display_text,
                (x + label_offset, y),
                color=self.poi_color,
                font_path=self.poi_font_path,
                font_size=self.poi_font_size,
                stroke_width=max(0, self.poi_thickness - 1),
                stroke_fill=(0, 0, 0),
            )
            frame[:, :] = rendered
            displayed_index += 1

    def _poi_frame_x(
        self,
        poi: PointOfInterest,
        frame_time: pd.Timestamp,
    ) -> int | None:
        if self.viewport_mode == "overview":
            return self._poi_overview_x(poi, frame_time)
        return self._poi_follow_x(poi, frame_time)

    def _poi_overview_x(
        self,
        poi: PointOfInterest,
        frame_time: pd.Timestamp,
    ) -> int | None:
        plot_left, _, plot_right, _ = self._plot_bounds
        plot_width = plot_right - plot_left
        if self.x_column is None:
            timestamp = self._poi_timestamp(poi)
            if timestamp is None:
                return None
            if not self.show_future_poi and timestamp > frame_time:
                return None
            x_offset = self._time_to_strip_x(timestamp)
            if x_offset < 0 or x_offset > plot_width:
                return None
            return plot_left + x_offset

        value = self._poi_x_value(poi)
        if value is None:
            return None
        if not self.show_future_poi:
            current_values = self.values_at(
                frame_time,
                [self.x_column],
                interpolation=self.interpolation,
                max_interpolation_gap_seconds=self.max_interpolation_gap_seconds,
            )
            if current_values is None or pd.isna(current_values[self.x_column]):
                return None
            current_value = float(current_values[self.x_column]) * self.x_multiplier
            if value > current_value:
                return None
        x_min, x_max = self._x_range()
        if value < x_min or value > x_max:
            return None
        span = max(x_max - x_min, 1.0)
        return int(round(plot_left + (value - x_min) / span * plot_width))

    def _poi_follow_x(
        self,
        poi: PointOfInterest,
        frame_time: pd.Timestamp,
    ) -> int | None:
        plot_left, _, plot_right, _ = self._plot_bounds
        plot_width = plot_right - plot_left
        anchor_x = self._frame_strip_x(frame_time)
        left_x = int(round(anchor_x - plot_width * self.follow_anchor_ratio))
        if self.x_column is not None:
            value = self._poi_x_value(poi)
            if value is None:
                return None
            x_offset = self._x_value_to_strip_x(value) - left_x
        else:
            timestamp = self._poi_timestamp(poi)
            if timestamp is None:
                return None
            x_offset = self._time_to_strip_x(timestamp) - left_x
        if x_offset < 0 or x_offset > plot_width:
            return None
        return plot_left + int(round(x_offset))

    def _poi_x_value(self, poi: PointOfInterest) -> float | None:
        if poi.distance_m is None or self.x_column is None:
            return None
        if self.x_column in self._route_progress_column_names():
            return float(poi.distance_m) * self.x_multiplier

        timestamp = self._poi_timestamp(poi)
        if timestamp is None:
            return None
        values = self.values_at(
            timestamp,
            [self.x_column],
            interpolation=self.interpolation,
            max_interpolation_gap_seconds=self.max_interpolation_gap_seconds,
        )
        if values is None or pd.isna(values[self.x_column]):
            return None
        return float(values[self.x_column]) * self.x_multiplier

    def _poi_timestamp(self, poi: PointOfInterest) -> pd.Timestamp | None:
        if poi.id in self._poi_timestamp_cache:
            return self._poi_timestamp_cache[poi.id]
        timestamp = self._match_poi_timestamp(poi)
        self._poi_timestamp_cache[poi.id] = timestamp
        return timestamp

    def _match_poi_timestamp(self, poi: PointOfInterest) -> pd.Timestamp | None:
        if poi.distance_m is None:
            return None
        route_progress_column = self._route_progress_column()
        if route_progress_column is None:
            return None
        progress = self.data[route_progress_column].dropna().astype(float)
        if progress.empty:
            return None
        distances = (progress - float(poi.distance_m)).abs()
        nearest_position = int(distances.to_numpy().argmin())
        nearest_timestamp = distances.index[nearest_position]
        if float(distances.iloc[nearest_position]) > self.poi_match_threshold_m:
            return None
        return nearest_timestamp

    def _route_progress_column(self) -> str | None:
        if self.poi_route_progress_column in self.data.columns:
            return self.poi_route_progress_column
        if "route_progress_m" in self.data.columns:
            return "route_progress_m"
        return None

    def _route_progress_column_names(self) -> set[str]:
        return {
            "route_progress_m",
            self.poi_route_progress_column,
        }

    @staticmethod
    def _format_elapsed_tick(value: float) -> str:
        total_seconds = int(round(abs(value)))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        sign = "-" if value < 0 else ""
        if hours:
            return f"{sign}{hours}:{minutes:02d}:{seconds:02d}"
        return f"{sign}{minutes}:{seconds:02d}"

    def _blend_axes_layer(self, frame: np.ndarray, axes_layer: np.ndarray) -> None:
        self._blend_rgba(frame, axes_layer)

    @staticmethod
    def _blend_rgba(frame: np.ndarray, overlay: np.ndarray) -> None:
        alpha = overlay[:, :, 3].astype(float) / 255.0
        mask = alpha > 0
        alpha_3d = alpha[:, :, np.newaxis]
        if frame.shape[2] == 4:
            frame_rgb = frame[:, :, :3].astype(float)
            frame_alpha = frame[:, :, 3:4].astype(float) / 255.0
            output_alpha = alpha_3d + frame_alpha * (1.0 - alpha_3d)
            numerator = (
                overlay[:, :, :3].astype(float) * alpha_3d
                + frame_rgb * frame_alpha * (1.0 - alpha_3d)
            )
            output_rgb = np.divide(
                numerator,
                output_alpha,
                out=np.zeros_like(numerator),
                where=output_alpha > 0,
            )
            frame[:, :, :3][mask] = output_rgb[mask].astype(np.uint8)
            frame[:, :, 3][mask] = (
                output_alpha[:, :, 0][mask] * 255
            ).astype(np.uint8)
            return

        blended = (
            frame.astype(float) * (1.0 - alpha_3d)
            + overlay[:, :, :3].astype(float) * alpha_3d
        )
        frame[mask] = blended[mask].astype(np.uint8)
