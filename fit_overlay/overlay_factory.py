"""type別設定からFrameMakerを生成するFactory。"""

from __future__ import annotations

import pandas as pd

from .config import (
    GraphOverlayConfig,
    MapOverlayConfig,
    MetricOverlayConfig,
    OverlayDefinition,
    TextColumnOverlayConfig,
    TextStyleConfig,
    TimeOverlayConfig,
)
from .frames import (
    FrameMaker,
    GraphFrameMaker,
    MatplotlibStripGraphFrameMaker,
    MetricFrameMaker,
    TextColumnFrameMaker,
    TimeFrameMaker,
)
from .map_frame import MapStaticFrameMaker
from .poi import PointOfInterest
from .route_margin import format_margin_seconds


class OverlayFactory:
    """Overlay設定のtypeに応じて、対応する生成クラスを作る。"""

    def __init__(
        self,
        points_of_interest: tuple[PointOfInterest, ...] = (),
        route_progress_column: str = "route_progress_m",
    ) -> None:
        self.points_of_interest = points_of_interest
        self.route_progress_column = route_progress_column

    def create(
        self,
        config: OverlayDefinition,
        data: pd.DataFrame,
    ) -> FrameMaker:
        if isinstance(config, TimeOverlayConfig):
            return self._create_time(config)
        if isinstance(config, MetricOverlayConfig):
            return self._create_metric(config, data)
        if isinstance(config, TextColumnOverlayConfig):
            return self._create_text(config, data)
        if isinstance(config, GraphOverlayConfig):
            return self._create_graph(config, data)
        if isinstance(config, MapOverlayConfig):
            return self._create_map(config, data)
        raise TypeError(f"未対応のoverlay設定です: {type(config).__name__}")

    @staticmethod
    def _text_options(
        config: TimeOverlayConfig | MetricOverlayConfig | TextColumnOverlayConfig,
    ) -> dict:
        style: TextStyleConfig = config.text
        return {
            "width": config.width,
            "height": config.height,
            "background_alpha": config.background_alpha,
            "text_position": style.position,
            "font_scale": style.font_scale,
            "font_size": style.font_size,
            "font_path": style.font_path,
            "text_color": style.color,
            "text_thickness": style.thickness,
        }

    def _create_time(self, config: TimeOverlayConfig) -> FrameMaker:
        return TimeFrameMaker(
            config.refresh_rate_hz,
            config.background,
            timezone=config.timezone,
            time_format=config.time_format,
            **self._text_options(config),
        )

    @staticmethod
    def _format_numeric_value(value_format: str, value: float) -> str:
        if value_format == "duration_margin":
            return format_margin_seconds(value)
        return value_format.format(
            value=value,
            duration_margin=format_margin_seconds(value),
        )

    def _create_metric(
        self,
        config: MetricOverlayConfig,
        data: pd.DataFrame,
    ) -> FrameMaker:
        def formatter(value: float) -> str:
            return self._format_numeric_value(
                config.value_format,
                value * config.multiplier,
            )

        color_selector = None
        if config.positive_color is not None and config.negative_color is not None:
            color_selector = (
                lambda value: config.positive_color
                if value >= 0
                else config.negative_color
            )

        return MetricFrameMaker(
            config.refresh_rate_hz,
            data,
            config.background,
            config.column,
            formatter,
            config.empty_text,
            interpolation=config.interpolation,
            max_interpolation_gap_seconds=config.max_interpolation_gap_seconds,
            color_selector=color_selector,
            background_color=config.background_color,
            **self._text_options(config),
        )

    def _create_text(
        self,
        config: TextColumnOverlayConfig,
        data: pd.DataFrame,
    ) -> FrameMaker:
        return TextColumnFrameMaker(
            config.refresh_rate_hz,
            data,
            config.background,
            config.column,
            config.empty_text,
            background_color=config.background_color,
            **self._text_options(config),
        )

    def _create_graph(
        self,
        config: GraphOverlayConfig,
        data: pd.DataFrame,
    ) -> FrameMaker:
        graph_class = (
            MatplotlibStripGraphFrameMaker
            if config.engine == "matplotlib_strip"
            else GraphFrameMaker
        )
        kwargs = {}
        if config.engine == "matplotlib_strip":
            kwargs = {
                "style_path": config.style_path,
                "strip_pixels_per_second": config.strip_pixels_per_second,
                "matplotlib_dpi": config.matplotlib_dpi,
            }
        return graph_class(
            config.refresh_rate_hz,
            data,
            config.column,
            lambda value: self._format_numeric_value(config.value_format, value),
            width=config.width,
            height=config.height,
            line_draw_style=config.line_draw_style,
            multiplier=config.multiplier,
            viewport_mode=config.viewport_mode,
            follow_anchor_ratio=config.follow_anchor_ratio,
            x_column=config.x_column,
            x_multiplier=config.x_multiplier,
            x_value_format=config.x_value_format,
            window_seconds=config.window_seconds,
            y_min=config.y_min,
            y_max=config.y_max,
            interpolation=config.interpolation,
            max_interpolation_gap_seconds=config.max_interpolation_gap_seconds,
            sample_interval_seconds=config.sample_interval_seconds,
            background_color=config.background_color,
            background_alpha=config.background_alpha,
            plot_background_color=config.plot_background_color,
            grid_color=config.grid_color,
            axis_color=config.axis_color,
            line_color=config.line_color,
            text_color=config.text_color,
            line_thickness=config.line_thickness,
            padding=config.padding,
            show_axes=config.show_axes,
            axes_layer_order=config.axes_layer_order,
            show_x_axis_labels=config.show_x_axis_labels,
            x_axis_nbins=config.x_axis_nbins,
            show_current_marker=config.show_current_marker,
            current_marker_color=config.current_marker_color,
            current_marker_thickness=config.current_marker_thickness,
            current_marker_radius=config.current_marker_radius,
            show_future_series=config.show_future_series,
            show_future_poi=config.show_future_poi,
            show_value=config.show_value,
            value_position=config.value_position,
            value_font_scale=config.value_font_scale,
            value_font_size=config.value_font_size,
            value_font_path=config.value_font_path,
            value_thickness=config.value_thickness,
            empty_text=config.empty_text,
            show_poi=config.show_poi,
            poi_font_size=config.poi_text.font_size,
            poi_font_path=config.poi_text.font_path,
            poi_color=config.poi_text.color,
            poi_thickness=config.poi_text.thickness,
            poi_icon_size=config.poi_icon_size,
            poi_match_threshold_m=config.poi_match_threshold_m,
            poi_route_progress_column=self.route_progress_column,
            points_of_interest=self.points_of_interest,
            **kwargs,
        )

    def _create_map(
        self,
        config: MapOverlayConfig,
        data: pd.DataFrame,
    ) -> FrameMaker:
        return MapStaticFrameMaker(
            config.refresh_rate_hz,
            data,
            config.icon,
            config.cache_dir,
            width=config.width,
            height=config.height,
            background_alpha=config.background_alpha,
            viewport_mode=config.viewport_mode,
            display_size_m=config.display_size_m,
            track_margin_m=config.track_margin_m,
            gpx_path=config.gpx_path,
            show_route=config.show_route,
            show_track=config.show_track,
            route_color=config.route_color,
            track_color=config.track_color,
            route_thickness=config.route_thickness,
            track_thickness=config.track_thickness,
            icon_size=config.icon_size,
            directional_icons=(
                None
                if config.directional_icons is None
                else {
                    "north": config.directional_icons.north,
                    "east": config.directional_icons.east,
                    "south": config.directional_icons.south,
                    "west": config.directional_icons.west,
                }
            ),
            use_icon=config.use_icon,
            circle_radius=config.circle_radius,
            tile_zoom=config.tile_zoom,
            interpolation=config.interpolation,
            max_interpolation_gap_seconds=config.max_interpolation_gap_seconds,
            direction_window_radius=config.direction_window_radius,
            direction_change_confirmations=(
                config.direction_change_confirmations
            ),
            direction_min_distance_m=config.direction_min_distance_m,
            debug=config.debug,
            show_poi=config.show_poi,
            poi_font_size=config.poi_text.font_size,
            poi_font_path=config.poi_text.font_path,
            poi_color=config.poi_text.color,
            poi_thickness=config.poi_text.thickness,
            poi_icon_size=config.poi_icon_size,
            points_of_interest=self.points_of_interest,
        )
