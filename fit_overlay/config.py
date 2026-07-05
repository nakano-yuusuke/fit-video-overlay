"""JSONから読み込むアプリケーション設定。"""

from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any


Color = tuple[int, int, int]


@dataclass(frozen=True)
class BackgroundStyleConfig:
    path: Path | None = None
    color: Color = (32, 32, 32)
    alpha: float = 1.0


@dataclass(frozen=True)
class TextStyleConfig:
    position: tuple[int, int] = (20, 70)
    font_scale: float = 2.0
    font_size: int | None = None
    font_path: Path | None = None
    color: Color = (255, 255, 255)
    thickness: int = 3


@dataclass(frozen=True)
class StylesConfig:
    background: BackgroundStyleConfig = BackgroundStyleConfig()
    text: TextStyleConfig = TextStyleConfig()


@dataclass(frozen=True)
class ResourceConfig:
    fit_path: Path | None = None
    route_gpx_path: Path | None = None
    osm_pbf_path: Path | None = None


@dataclass(frozen=True)
class OverlayConfig:
    id: str
    type: str
    x: int
    y: int
    width: int
    height: int
    refresh_rate_hz: float
    enabled: bool = True
    background_alpha: float = 1.0


@dataclass(frozen=True)
class TimeOverlayConfig(OverlayConfig):
    background: Path | None = None
    background_color: Color = (32, 32, 32)
    timezone: str = "Asia/Tokyo"
    time_format: str = "%Y/%m/%d %H:%M:%S"
    text: TextStyleConfig = TextStyleConfig()


@dataclass(frozen=True)
class MetricOverlayConfig(OverlayConfig):
    background: Path | None = None
    background_color: Color = (32, 32, 32)
    column: str = ""
    multiplier: float = 1.0
    value_format: str = "{value:.1f}"
    empty_text: str = "-"
    interpolation: str = "linear"
    max_interpolation_gap_seconds: float = 2.0
    positive_color: Color | None = None
    negative_color: Color | None = None
    text: TextStyleConfig = TextStyleConfig()


@dataclass(frozen=True)
class TextColumnOverlayConfig(OverlayConfig):
    background: Path | None = None
    background_color: Color = (32, 32, 32)
    column: str = ""
    empty_text: str = "-"
    text: TextStyleConfig = TextStyleConfig()


@dataclass(frozen=True)
class GraphOverlayConfig(OverlayConfig):
    style_path: Path | None = None
    engine: str = "opencv"
    plot_type: str = "line"
    line_draw_style: str = "auto"
    viewport_mode: str = "follow"
    follow_anchor_ratio: float = 1.0
    x_column: str | None = None
    x_multiplier: float = 1.0
    x_value_format: str | None = None
    column: str = ""
    multiplier: float = 1.0
    value_format: str = "{value:.1f}"
    window_seconds: float | None = 300.0
    y_min: float | None = None
    y_max: float | None = None
    interpolation: str = "linear"
    max_interpolation_gap_seconds: float = 2.0
    sample_interval_seconds: float | None = None
    background_color: Color = (16, 16, 16)
    plot_background_color: Color | None = None
    grid_color: Color = (64, 64, 64)
    axis_color: Color = (180, 180, 180)
    line_color: Color = (80, 220, 255)
    text_color: Color = (255, 255, 255)
    line_thickness: int = 3
    padding: tuple[int, int, int, int] = (50, 20, 20, 40)
    strip_pixels_per_second: float | None = None
    matplotlib_dpi: int = 100
    show_axes: bool = False
    axes_layer_order: str = "front"
    show_x_axis_labels: bool = False
    x_axis_nbins: int = 5
    show_current_marker: bool = False
    current_marker_color: Color = (255, 80, 80)
    current_marker_thickness: int = 2
    current_marker_radius: int = 5
    show_future_series: bool = True
    show_future_poi: bool = True
    show_value: bool = True
    value_position: tuple[int, int] = (12, 34)
    value_font_scale: float = 0.9
    value_font_size: int | None = None
    value_font_path: Path | None = None
    value_thickness: int = 2
    empty_text: str = "-"
    show_poi: bool = False
    poi_icon_size: tuple[int, int] | None = None
    poi_match_threshold_m: float = 300.0
    poi_text: TextStyleConfig = TextStyleConfig(
        position=(0, 0),
        font_size=22,
        color=(255, 255, 255),
        thickness=2,
    )


@dataclass(frozen=True)
class DirectionalIconsConfig:
    north: Path
    east: Path
    south: Path
    west: Path


@dataclass(frozen=True)
class MapOverlayConfig(OverlayConfig):
    viewport_mode: str = "follow"
    display_size_m: float = 200.0
    track_margin_m: float | None = None
    gpx_path: Path | None = None
    show_route: bool = False
    show_track: bool = False
    route_color: Color = (255, 180, 0)
    track_color: Color = (0, 255, 255)
    route_thickness: int = 4
    track_thickness: int = 4
    cache_dir: Path = Path("cache/tiles")
    icon: Path = Path("icon.png")
    icon_size: tuple[int, int] | None = None
    directional_icons: DirectionalIconsConfig | None = None
    use_icon: bool = False
    circle_radius: int = 12
    tile_zoom: int = 18
    interpolation: str = "linear"
    max_interpolation_gap_seconds: float = 2.0
    direction_window_radius: int = 3
    direction_change_confirmations: int = 3
    direction_min_distance_m: float = 2.0
    debug: bool = False
    show_poi: bool = False
    poi_icon_size: tuple[int, int] | None = None
    poi_text: TextStyleConfig = TextStyleConfig(
        position=(0, 0),
        font_size=20,
        color=(255, 255, 255),
        thickness=3,
    )


@dataclass(frozen=True)
class RouteProgressFeatureConfig:
    enabled: bool = False
    gpx_path: Path | None = None
    add_route_altitude: bool = False
    off_route_threshold_m: float = 150.0
    search_ahead_m: float = 5000.0
    search_behind_m: float = 300.0
    progress_column: str = "route_progress_m"
    altitude_column: str = "route_altitude_m"


@dataclass(frozen=True)
class RouteMarginFeatureConfig:
    enabled: bool = False
    gpx_path: Path | None = None
    target_speed_kmh: float = 15.0
    deadline_time: str = "21:30"
    timezone: str = "Asia/Tokyo"
    off_route_threshold_m: float = 150.0
    search_ahead_m: float = 5000.0
    search_behind_m: float = 300.0
    progress_column: str = "route_progress_m"
    column: str = "route_margin_seconds"


@dataclass(frozen=True)
class GradeSeriesConfig:
    enabled: bool = False
    distance_column: str = "distance"
    altitude_column: str = "altitude"
    column: str = "grade_percent"
    window_m: float = 200.0


@dataclass(frozen=True)
class GradeFeatureConfig:
    enabled: bool = False
    ride: GradeSeriesConfig = GradeSeriesConfig()
    route: GradeSeriesConfig = GradeSeriesConfig(
        distance_column="route_progress_m",
        altitude_column="route_altitude_m",
        column="route_grade_percent",
    )


@dataclass(frozen=True)
class TrafficSignalsFeatureConfig:
    enabled: bool = False
    route_source: str = "gpx"
    gpx_path: Path | None = None
    cache_dir: Path = Path("cache/osm_features")
    bucket_distance_m: float = 1000.0
    signal_match_threshold_m: float = 50.0
    route_match_threshold_m: float = 150.0
    bbox_margin_m: float = 1000.0
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    column: str = "traffic_signal_count_per_km"


@dataclass(frozen=True)
class PlaceNamesFeatureConfig:
    enabled: bool = False
    source: str = "osm_pbf"
    route_source: str = "gpx"
    gpx_path: Path | None = None
    pbf_path: Path | None = None
    cache_dir: Path = Path("cache/osm_features")
    admin_levels: tuple[int, ...] = (7,)
    bbox_margin_m: float = 5000.0
    name_tags: tuple[str, ...] = ("name:ja", "name", "name:en")
    column: str = "place_name"


@dataclass(frozen=True)
class PointOfInterestSourceConfig:
    type: str
    gpx_path: Path
    emoji: str = ""
    icon: Path | None = None
    icon_size: tuple[int, int] | None = None


@dataclass(frozen=True)
class PointOfInterestItemConfig:
    id: str
    label: str | None = None
    name: str | None = None
    emoji: str = ""
    icon: Path | None = None
    icon_size: tuple[int, int] | None = None
    distance_m: float | None = None
    lat: float | None = None
    lon: float | None = None


@dataclass(frozen=True)
class PointsOfInterestConfig:
    enabled: bool = False
    gpx_path: Path | None = None
    sources: tuple[PointOfInterestSourceConfig, ...] = ()
    items: tuple[PointOfInterestItemConfig, ...] = ()


@dataclass(frozen=True)
class LayoutConfig:
    reference_resolution: tuple[int, int] | None = None
    scale_mode: str = "fit"


@dataclass(frozen=True)
class StillExportConfig:
    enabled: bool = False
    positions: tuple[str, ...] = ()
    interval_seconds: float | None = None


@dataclass(frozen=True)
class MediaTimeOffsetConfig:
    from_file: str
    offset_seconds: float


OverlayDefinition = (
    TimeOverlayConfig
    | MetricOverlayConfig
    | TextColumnOverlayConfig
    | GraphOverlayConfig
    | MapOverlayConfig
)


@dataclass(frozen=True)
class ProcessorConfig:
    """入力、エンコード、オーバーレイ定義をまとめた実行設定。"""

    mp4_dir: Path
    fit_path: Path
    output_dir: Path
    overlays: tuple[OverlayDefinition, ...]
    route_progress: RouteProgressFeatureConfig = RouteProgressFeatureConfig()
    route_margin: RouteMarginFeatureConfig = RouteMarginFeatureConfig()
    grade: GradeFeatureConfig = GradeFeatureConfig()
    traffic_signals: TrafficSignalsFeatureConfig = TrafficSignalsFeatureConfig()
    place_names: PlaceNamesFeatureConfig = PlaceNamesFeatureConfig()
    points_of_interest: PointsOfInterestConfig = PointsOfInterestConfig()
    layout: LayoutConfig = LayoutConfig()
    still_exports: StillExportConfig = StillExportConfig()
    default_refresh_rate_hz: float = 59.94 / 4
    fit_time_offset_seconds: float = 0.0
    media_time_offsets: tuple[MediaTimeOffsetConfig, ...] = ()
    max_fit_duration_minutes: float | None = 60.0
    video_codec: str = "libx265"
    video_crf: int = 18
    video_cq: int = 20
    video_preset: str = "medium"
    pixel_format: str = "yuv420p"
    copy_audio: bool = True
    output_mode: str = "composited"
    noautorotate: bool = False
    ffmpeg_binary: Path = Path("/usr/bin/ffmpeg")
    ffprobe_binary: Path = Path("/usr/bin/ffprobe")
    max_parallel_videos: int = 1


def load_processor_config(path: Path) -> ProcessorConfig:
    """JSON設定を読み込み、type別の設定クラスへ変換する。"""
    config_path = path.resolve()
    with config_path.open(encoding="utf-8") as file:
        raw = json.load(file)
    if not isinstance(raw, dict):
        raise ValueError("設定JSONのルートはオブジェクトである必要があります。")

    base_dir = config_path.parent
    input_config = _mapping(raw, "input")
    resources = _parse_resources(raw.get("resources"))
    processing = _mapping(raw, "processing", required=False)
    encoding = _mapping(raw, "encoding", required=False)
    features = _mapping(raw, "features", required=False)
    layout = _parse_layout(raw.get("layout"))
    still_exports = _parse_still_exports(raw.get("still_exports"))
    styles = _parse_styles(raw.get("styles"), base_dir)
    overlay_items = raw.get("overlays")
    if not isinstance(overlay_items, list) or not overlay_items:
        raise ValueError("overlaysには1件以上の配列を指定してください。")

    default_refresh_rate_hz = _positive_float(
        processing.get("default_refresh_rate_hz", 59.94 / 4),
        "processing.default_refresh_rate_hz",
    )
    overlays = tuple(
        _parse_overlay(
            item,
            base_dir=base_dir,
            default_refresh_rate_hz=default_refresh_rate_hz,
            styles=styles,
            resources=resources,
        )
        for item in overlay_items
    )
    overlay_ids = [overlay.id for overlay in overlays]
    if len(overlay_ids) != len(set(overlay_ids)):
        raise ValueError("overlayのidは重複できません。")

    route_progress = _parse_route_progress_feature(
        features.get("route_progress"),
        base_dir,
        resources.route_gpx_path,
    )
    route_margin = _parse_route_margin_feature(
        features.get("route_margin"),
        base_dir,
        resources.route_gpx_path,
    )
    grade = _parse_grade_feature(features.get("grade"))
    traffic_signals = _parse_traffic_signals_feature(
        features.get("traffic_signals"),
        base_dir,
        resources.route_gpx_path,
    )
    place_names = _parse_place_names_feature(
        features.get("place_names"),
        base_dir,
        resources.route_gpx_path,
        resources.osm_pbf_path,
    )
    points_of_interest = _parse_points_of_interest(
        raw.get("points_of_interest"),
        base_dir,
        resources.route_gpx_path,
    )
    _validate_feature_dependencies(
        overlays,
        route_progress,
        route_margin,
        grade,
        traffic_signals,
        place_names,
    )

    max_duration = processing.get("max_fit_duration_minutes", 60.0)
    if max_duration is not None:
        max_duration = _positive_float(
            max_duration,
            "processing.max_fit_duration_minutes",
        )

    output_mode = str(encoding.get("output_mode", "composited"))
    if output_mode not in {"composited", "transparent_overlay"}:
        raise ValueError(
            "encoding.output_modeはcompositedまたはtransparent_overlayを指定してください。"
        )

    return ProcessorConfig(
        mp4_dir=_resolve_path(base_dir, _required(input_config, "mp4_dir")),
        fit_path=_resolve_path(
            base_dir,
            input_config.get("fit_path", resources.fit_path)
            if resources.fit_path is not None
            else _required(input_config, "fit_path"),
        ),
        output_dir=_resolve_path(base_dir, _required(input_config, "output_dir")),
        overlays=overlays,
        route_progress=route_progress,
        route_margin=route_margin,
        grade=grade,
        traffic_signals=traffic_signals,
        place_names=place_names,
        points_of_interest=points_of_interest,
        layout=layout,
        still_exports=still_exports,
        default_refresh_rate_hz=default_refresh_rate_hz,
        fit_time_offset_seconds=float(
            processing.get("fit_time_offset_seconds", 0.0)
        ),
        media_time_offsets=_parse_media_time_offsets(
            processing.get("media_time_offsets")
        ),
        max_fit_duration_minutes=max_duration,
        video_codec=str(encoding.get("codec", "libx265")),
        video_crf=int(encoding.get("crf", 18)),
        video_cq=int(encoding.get("cq", 20)),
        video_preset=str(encoding.get("preset", "medium")),
        pixel_format=str(encoding.get("pixel_format", "yuv420p")),
        copy_audio=bool(encoding.get("copy_audio", True)),
        output_mode=output_mode,
        noautorotate=bool(encoding.get("noautorotate", False)),
        ffmpeg_binary=_resolve_path(
            base_dir,
            encoding.get("ffmpeg_binary", "/usr/bin/ffmpeg"),
        ),
        ffprobe_binary=_resolve_path(
            base_dir,
            encoding.get("ffprobe_binary", "/usr/bin/ffprobe"),
        ),
        max_parallel_videos=int(processing.get("max_parallel_videos", 1)),
    )


def _parse_still_exports(raw: Any) -> StillExportConfig:
    if raw is None:
        return StillExportConfig()
    if not isinstance(raw, dict):
        raise ValueError("still_exportsはオブジェクトで指定してください。")
    unknown = set(raw).difference({"enabled", "positions", "interval_seconds"})
    if unknown:
        raise ValueError(f"still_exportsに未対応の設定があります: {sorted(unknown)}")

    positions_raw = raw.get("positions", ())
    if positions_raw is None:
        positions: tuple[str, ...] = ()
    elif isinstance(positions_raw, list):
        parsed_positions = tuple(str(item).strip() for item in positions_raw)
        if any(not position for position in parsed_positions):
            raise ValueError("still_exports.positionsには空文字を指定できません。")
        positions = parsed_positions
    else:
        raise ValueError("still_exports.positionsは配列で指定してください。")

    interval_seconds = (
        None
        if raw.get("interval_seconds") is None
        else _positive_float(
            raw.get("interval_seconds"),
            "still_exports.interval_seconds",
        )
    )
    enabled = bool(raw.get("enabled", False))
    if enabled and not positions and interval_seconds is None:
        raise ValueError(
            "still_exports.enabled=trueの場合はpositionsまたは"
            "interval_secondsを指定してください。"
        )
    return StillExportConfig(
        enabled=enabled,
        positions=positions,
        interval_seconds=interval_seconds,
    )


def _parse_media_time_offsets(raw: Any) -> tuple[MediaTimeOffsetConfig, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("processing.media_time_offsetsは配列で指定してください。")

    offsets: list[MediaTimeOffsetConfig] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        path = f"processing.media_time_offsets[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{path}はオブジェクトで指定してください。")
        unknown = set(item).difference({"from", "offset_seconds"})
        if unknown:
            raise ValueError(f"{path}に未対応の設定があります: {sorted(unknown)}")

        from_file = str(_required(item, "from")).strip()
        if not from_file:
            raise ValueError(f"{path}.fromは空にできません。")
        if "/" in from_file or "\\" in from_file:
            raise ValueError(f"{path}.fromはファイル名だけで指定してください。")
        if from_file in seen:
            raise ValueError(
                "processing.media_time_offsets.fromが重複しています: "
                f"{from_file}"
            )
        seen.add(from_file)

        offsets.append(
            MediaTimeOffsetConfig(
                from_file=from_file,
                offset_seconds=float(_required(item, "offset_seconds")),
            )
        )
    return tuple(offsets)


def _parse_resources(raw: Any) -> ResourceConfig:
    if raw is None:
        return ResourceConfig()
    if not isinstance(raw, dict):
        raise ValueError("resourcesはオブジェクトで指定してください。")
    unknown = set(raw).difference(
        {
            "fit_path",
            "route_gpx_path",
            "osm_pbf_path",
        }
    )
    if unknown:
        raise ValueError(f"resourcesに未対応の設定があります: {sorted(unknown)}")
    return ResourceConfig(
        fit_path=_optional_absolute_path(raw.get("fit_path"), "resources.fit_path"),
        route_gpx_path=_optional_absolute_path(
            raw.get("route_gpx_path"),
            "resources.route_gpx_path",
        ),
        osm_pbf_path=_optional_absolute_path(
            raw.get("osm_pbf_path"),
            "resources.osm_pbf_path",
        ),
    )


def default_overlay_configs(
    asset_dir: Path,
    refresh_rate_hz: float,
) -> tuple[OverlayDefinition, ...]:
    """JSON未使用時に、従来レイアウトを再現する設定を返す。"""
    time_size = (954, 100)
    metric_size = (500, 100)
    return (
        TimeOverlayConfig(
            id="time",
            type="time",
            x=50,
            y=50,
            width=time_size[0],
            height=time_size[1],
            refresh_rate_hz=refresh_rate_hz,
            background=asset_dir / "time_background.png",
        ),
        MetricOverlayConfig(
            id="speed",
            type="metric",
            x=50,
            y=200,
            width=metric_size[0],
            height=metric_size[1],
            refresh_rate_hz=refresh_rate_hz,
            background=asset_dir / "speed_background.png",
            column="speed",
            multiplier=3.6,
            value_format="{value:.1f}",
        ),
        MetricOverlayConfig(
            id="distance",
            type="metric",
            x=50,
            y=350,
            width=metric_size[0],
            height=metric_size[1],
            refresh_rate_hz=refresh_rate_hz,
            background=asset_dir / "dist_background.png",
            column="distance",
            multiplier=0.001,
            value_format="{value:.1f}",
            empty_text="0.0",
        ),
        MetricOverlayConfig(
            id="altitude",
            type="metric",
            x=50,
            y=500,
            width=metric_size[0],
            height=metric_size[1],
            refresh_rate_hz=refresh_rate_hz,
            background=asset_dir / "alt_background.png",
            column="altitude",
            value_format="{value:.0f}",
        ),
        MapOverlayConfig(
            id="map",
            type="map",
            x=3000,
            y=50,
            width=400,
            height=400,
            refresh_rate_hz=3,
            icon=asset_dir / "icon.png",
            cache_dir=asset_dir / "cache" / "tiles",
        ),
    )


def _parse_overlay(
    raw: Any,
    *,
    base_dir: Path,
    default_refresh_rate_hz: float,
    styles: StylesConfig,
    resources: ResourceConfig = ResourceConfig(),
) -> OverlayDefinition:
    if not isinstance(raw, dict):
        raise ValueError("overlaysの各要素はオブジェクトである必要があります。")
    overlay_type = str(_required(raw, "type"))
    common = _parse_common(raw, overlay_type, default_refresh_rate_hz)

    if overlay_type == "time":
        _check_keys(
            raw,
            common=_COMMON_KEYS,
            specific={
                "background",
                "background_color",
                "timezone",
                "time_format",
                "text",
            },
        )
        background = _parse_overlay_background(raw, base_dir, styles.background)
        common["background_alpha"] = background.alpha
        return TimeOverlayConfig(
            **common,
            background=background.path,
            background_color=background.color,
            timezone=str(raw.get("timezone", "Asia/Tokyo")),
            time_format=str(raw.get("time_format", "%Y/%m/%d %H:%M:%S")),
            text=_parse_text_style(raw.get("text"), base_dir, styles.text),
        )
    if overlay_type == "metric":
        _check_keys(
            raw,
            common=_COMMON_KEYS,
            specific={
                "background",
                "background_color",
                "column",
                "multiplier",
                "value_format",
                "empty_text",
                "interpolation",
                "max_interpolation_gap_seconds",
                "positive_color",
                "negative_color",
                "text",
            },
        )
        background = _parse_overlay_background(raw, base_dir, styles.background)
        common["background_alpha"] = background.alpha
        return MetricOverlayConfig(
            **common,
            background=background.path,
            background_color=background.color,
            column=str(_required(raw, "column")),
            multiplier=float(raw.get("multiplier", 1.0)),
            value_format=str(raw.get("value_format", "{value:.1f}")),
            empty_text=str(raw.get("empty_text", "-")),
            interpolation=_interpolation(raw.get("interpolation", "linear")),
            max_interpolation_gap_seconds=_positive_float(
                raw.get("max_interpolation_gap_seconds", 2.0),
                f"overlays.{common['id']}.max_interpolation_gap_seconds",
            ),
            positive_color=(
                None
                if raw.get("positive_color") is None
                else _color(raw.get("positive_color"))
            ),
            negative_color=(
                None
                if raw.get("negative_color") is None
                else _color(raw.get("negative_color"))
            ),
            text=_parse_text_style(raw.get("text"), base_dir, styles.text),
        )
    if overlay_type == "text":
        _check_keys(
            raw,
            common=_COMMON_KEYS,
            specific={
                "background",
                "background_color",
                "column",
                "empty_text",
                "text",
            },
        )
        background = _parse_overlay_background(raw, base_dir, styles.background)
        common["background_alpha"] = background.alpha
        return TextColumnOverlayConfig(
            **common,
            background=background.path,
            background_color=background.color,
            column=str(_required(raw, "column")),
            empty_text=str(raw.get("empty_text", "-")),
            text=_parse_text_style(raw.get("text"), base_dir, styles.text),
        )
    if overlay_type == "graph":
        style_path_value = raw.get("style_path")
        style_path = (
            None
            if style_path_value is None
            else _resolve_path(base_dir, style_path_value)
        )
        _check_keys(
            raw,
            common=_COMMON_KEYS,
            specific={
                "style_path",
                "engine",
                "plot_type",
                "line_draw_style",
                "viewport_mode",
                "follow_anchor_ratio",
                "x_column",
                "x_multiplier",
                "x_value_format",
                "column",
                "multiplier",
                "value_format",
                "window_seconds",
                "y_min",
                "y_max",
                "interpolation",
                "max_interpolation_gap_seconds",
                "sample_interval_seconds",
                "background",
                "background_color",
                "background_alpha",
                "plot_background_color",
                "grid_color",
                "axis_color",
                "line_color",
                "text_color",
                "line_thickness",
                "padding",
                "strip_pixels_per_second",
                "matplotlib_dpi",
                "show_axes",
                "axes_layer_order",
                "show_x_axis_labels",
                "x_axis_nbins",
                "show_current_marker",
                "current_marker_color",
                "current_marker_thickness",
                "current_marker_radius",
                "show_future_series",
                "show_future_poi",
                "show_value",
                "value_text",
                "value_position",
                "value_font_scale",
                "value_font_size",
                "value_font_path",
                "value_thickness",
                "empty_text",
                "show_poi",
                "poi_icon_size",
                "poi_match_threshold_m",
                "poi_text",
            },
        )
        engine = str(raw.get("engine", "opencv"))
        if engine not in {"opencv", "matplotlib_strip"}:
            raise ValueError(
                "graphのengineはopencvまたはmatplotlib_stripを指定してください。"
            )
        plot_type = str(raw.get("plot_type", "line"))
        if plot_type != "line":
            raise ValueError("現在graphのplot_typeはlineのみ対応しています。")
        line_draw_style = str(raw.get("line_draw_style", "auto"))
        if line_draw_style not in {"auto", "linear", "steps-post"}:
            raise ValueError(
                "graphのline_draw_styleはauto、linear、steps-postを指定してください。"
            )
        viewport_mode = str(raw.get("viewport_mode", "follow"))
        if viewport_mode not in {"follow", "overview"}:
            raise ValueError(
                "graphのviewport_modeはfollowまたはoverviewを指定してください。"
            )
        follow_anchor_ratio = float(raw.get("follow_anchor_ratio", 1.0))
        if not 0.0 <= follow_anchor_ratio <= 1.0:
            raise ValueError(
                "graphのfollow_anchor_ratioは0.0から1.0で指定してください。"
            )
        axes_layer_order = str(raw.get("axes_layer_order", "front"))
        if axes_layer_order not in {"front", "behind"}:
            raise ValueError(
                "graphのaxes_layer_orderはfrontまたはbehindを指定してください。"
            )
        background = _parse_overlay_background(
            raw,
            base_dir,
            styles.background,
        )
        common["background_alpha"] = background.alpha
        value_text = _parse_graph_value_text(raw, base_dir, styles.text)
        y_min = _optional_float(raw.get("y_min"))
        y_max = _optional_float(raw.get("y_max"))
        if y_min is not None and y_max is not None and y_min >= y_max:
            raise ValueError(
                f"overlays.{common['id']}.y_minはy_maxより小さくしてください。"
            )
        window_seconds = raw.get("window_seconds", 300.0)
        return GraphOverlayConfig(
            **common,
            style_path=style_path,
            engine=engine,
            plot_type=plot_type,
            line_draw_style=line_draw_style,
            viewport_mode=viewport_mode,
            follow_anchor_ratio=follow_anchor_ratio,
            x_column=(
                None
                if raw.get("x_column") is None
                else str(raw.get("x_column"))
            ),
            x_multiplier=float(raw.get("x_multiplier", 1.0)),
            x_value_format=(
                None
                if raw.get("x_value_format") is None
                else str(raw.get("x_value_format"))
            ),
            column=str(_required(raw, "column")),
            multiplier=float(raw.get("multiplier", 1.0)),
            value_format=str(raw.get("value_format", "{value:.1f}")),
            window_seconds=(
                None
                if window_seconds is None
                else _positive_float(
                    window_seconds,
                    f"overlays.{common['id']}.window_seconds",
                )
            ),
            y_min=y_min,
            y_max=y_max,
            interpolation=_interpolation(raw.get("interpolation", "linear")),
            max_interpolation_gap_seconds=_positive_float(
                raw.get("max_interpolation_gap_seconds", 2.0),
                f"overlays.{common['id']}.max_interpolation_gap_seconds",
            ),
            sample_interval_seconds=(
                None
                if raw.get("sample_interval_seconds") is None
                else _positive_float(
                    raw.get("sample_interval_seconds"),
                    f"overlays.{common['id']}.sample_interval_seconds",
                )
            ),
            background_color=background.color,
            plot_background_color=(
                None
                if raw.get("plot_background_color") is None
                else _color(raw.get("plot_background_color"))
            ),
            grid_color=_color(raw.get("grid_color", [64, 64, 64])),
            axis_color=_color(raw.get("axis_color", [180, 180, 180])),
            line_color=_color(raw.get("line_color", [80, 220, 255])),
            text_color=value_text.color,
            line_thickness=_positive_int(
                raw.get("line_thickness", 3),
                f"overlays.{common['id']}.line_thickness",
            ),
            padding=_quad(
                raw.get("padding", [50, 20, 20, 40]),
                "graph.padding",
            ),
            strip_pixels_per_second=(
                None
                if raw.get("strip_pixels_per_second") is None
                else _positive_float(
                    raw.get("strip_pixels_per_second"),
                    f"overlays.{common['id']}.strip_pixels_per_second",
                )
            ),
            matplotlib_dpi=_positive_int(
                raw.get("matplotlib_dpi", 100),
                f"overlays.{common['id']}.matplotlib_dpi",
            ),
            show_axes=bool(raw.get("show_axes", False)),
            axes_layer_order=axes_layer_order,
            show_x_axis_labels=bool(raw.get("show_x_axis_labels", False)),
            x_axis_nbins=_positive_int(
                raw.get("x_axis_nbins", 5),
                f"overlays.{common['id']}.x_axis_nbins",
            ),
            show_current_marker=bool(raw.get("show_current_marker", False)),
            current_marker_color=_color(
                raw.get("current_marker_color", [255, 80, 80])
            ),
            current_marker_thickness=_positive_int(
                raw.get("current_marker_thickness", 2),
                f"overlays.{common['id']}.current_marker_thickness",
            ),
            current_marker_radius=_positive_int(
                raw.get("current_marker_radius", 5),
                f"overlays.{common['id']}.current_marker_radius",
            ),
            show_future_series=bool(raw.get("show_future_series", True)),
            show_future_poi=bool(raw.get("show_future_poi", True)),
            show_value=bool(raw.get("show_value", True)),
            value_position=value_text.position,
            value_font_scale=value_text.font_scale,
            value_font_size=value_text.font_size,
            value_font_path=value_text.font_path,
            value_thickness=value_text.thickness,
            empty_text=str(raw.get("empty_text", "-")),
            show_poi=bool(raw.get("show_poi", False)),
            poi_icon_size=_optional_size(
                raw.get("poi_icon_size"),
                f"overlays.{common['id']}.poi_icon_size",
            ),
            poi_match_threshold_m=_positive_float(
                raw.get("poi_match_threshold_m", 300.0),
                f"overlays.{common['id']}.poi_match_threshold_m",
            ),
            poi_text=_parse_poi_text_style(
                raw.get("poi_text"),
                base_dir,
                default_font_size=22,
                default_thickness=2,
            ),
        )
    if overlay_type == "map":
        _check_keys(
            raw,
            common=_COMMON_KEYS,
            specific={
                "background",
                "viewport_mode",
                "display_size_m",
                "track_margin_m",
                "gpx_path",
                "show_route",
                "show_track",
                "route_color",
                "track_color",
                "route_thickness",
                "track_thickness",
                "cache_dir",
                "icon",
                "icon_size",
                "directional_icons",
                "use_icon",
                "circle_radius",
                "tile_zoom",
                "interpolation",
                "max_interpolation_gap_seconds",
                "direction_window_radius",
                "direction_change_confirmations",
                "direction_min_distance_m",
                "debug",
                "show_poi",
                "poi_icon_size",
                "poi_text",
            },
        )
        display_size_m = _positive_float(
            raw.get("display_size_m", 200.0),
            f"overlays.{common['id']}.display_size_m",
        )
        track_margin = raw.get("track_margin_m")
        viewport_mode = str(raw.get("viewport_mode", "follow"))
        if viewport_mode not in {"follow", "route_overview"}:
            raise ValueError(
                "viewport_modeはfollowまたはroute_overviewを指定してください。"
            )
        show_route = bool(raw.get("show_route", False))
        gpx_path_value = raw.get("gpx_path")
        gpx_path = (
            resources.route_gpx_path
            if gpx_path_value is None
            else _resolve_path(base_dir, gpx_path_value)
        )
        if show_route and gpx_path is None:
            raise ValueError(
                f"overlays.{common['id']}.show_routeにはgpx_pathまたは"
                "resources.route_gpx_pathが必要です。"
            )
        background = _parse_overlay_background(raw, base_dir, styles.background)
        common["background_alpha"] = background.alpha
        return MapOverlayConfig(
            **common,
            viewport_mode=viewport_mode,
            display_size_m=display_size_m,
            track_margin_m=(
                None
                if track_margin is None
                else _positive_float(
                    track_margin,
                    f"overlays.{common['id']}.track_margin_m",
                )
            ),
            gpx_path=gpx_path,
            show_route=show_route,
            show_track=bool(raw.get("show_track", False)),
            route_color=_color(raw.get("route_color", [255, 180, 0])),
            track_color=_color(raw.get("track_color", [0, 255, 255])),
            route_thickness=_positive_int(
                raw.get("route_thickness", 4),
                f"overlays.{common['id']}.route_thickness",
            ),
            track_thickness=_positive_int(
                raw.get("track_thickness", 4),
                f"overlays.{common['id']}.track_thickness",
            ),
            cache_dir=_resolve_path(
                base_dir,
                raw.get("cache_dir", "cache/tiles"),
            ),
            icon=_resolve_path(base_dir, raw.get("icon", "icon.png")),
            icon_size=_optional_size(raw.get("icon_size"), "icon_size"),
            directional_icons=_parse_directional_icons(
                raw.get("directional_icons"),
                base_dir,
            ),
            use_icon=bool(raw.get("use_icon", False)),
            circle_radius=int(raw.get("circle_radius", 12)),
            tile_zoom=int(raw.get("tile_zoom", 18)),
            interpolation=_interpolation(raw.get("interpolation", "linear")),
            max_interpolation_gap_seconds=_positive_float(
                raw.get("max_interpolation_gap_seconds", 2.0),
                f"overlays.{common['id']}.max_interpolation_gap_seconds",
            ),
            direction_window_radius=_positive_int(
                raw.get("direction_window_radius", 3),
                f"overlays.{common['id']}.direction_window_radius",
            ),
            direction_change_confirmations=_positive_int(
                raw.get("direction_change_confirmations", 3),
                f"overlays.{common['id']}.direction_change_confirmations",
            ),
            direction_min_distance_m=_positive_float(
                raw.get("direction_min_distance_m", 2.0),
                f"overlays.{common['id']}.direction_min_distance_m",
            ),
            debug=bool(raw.get("debug", False)),
            show_poi=bool(raw.get("show_poi", False)),
            poi_icon_size=_optional_size(
                raw.get("poi_icon_size"),
                f"overlays.{common['id']}.poi_icon_size",
            ),
            poi_text=_parse_poi_text_style(
                raw.get("poi_text"),
                base_dir,
                default_font_size=20,
                default_thickness=3,
            ),
        )
    raise ValueError(f"未対応のoverlay typeです: {overlay_type}")


_COMMON_KEYS = {
    "id",
    "type",
    "enabled",
    "x",
    "y",
    "width",
    "height",
    "refresh_rate_hz",
    "background_alpha",
}


def _parse_layout(raw: Any) -> LayoutConfig:
    if raw is None:
        return LayoutConfig()
    if not isinstance(raw, dict):
        raise ValueError("layoutはオブジェクトで指定してください。")
    unknown = set(raw).difference({"reference_resolution", "scale_mode"})
    if unknown:
        raise ValueError(f"layoutに未対応の設定があります: {sorted(unknown)}")
    reference_resolution = _optional_size(
        raw.get("reference_resolution"),
        "layout.reference_resolution",
    )
    scale_mode = str(raw.get("scale_mode", "fit"))
    if scale_mode != "fit":
        raise ValueError("layout.scale_modeはfitを指定してください。")
    return LayoutConfig(
        reference_resolution=reference_resolution or (3840, 2160),
        scale_mode=scale_mode,
    )


def _parse_styles(raw: Any, base_dir: Path) -> StylesConfig:
    if raw is None:
        return StylesConfig()
    if not isinstance(raw, dict):
        raise ValueError("stylesはオブジェクトで指定してください。")
    unknown = set(raw).difference({"background", "text"})
    if unknown:
        raise ValueError(f"stylesに未対応の設定があります: {sorted(unknown)}")
    default = StylesConfig()
    return StylesConfig(
        background=_parse_background_style(
            raw.get("background"),
            base_dir,
            default.background,
        ),
        text=_parse_text_style(raw.get("text"), base_dir, default.text),
    )


def _parse_overlay_background(
    raw: dict[str, Any],
    base_dir: Path,
    default: BackgroundStyleConfig,
) -> BackgroundStyleConfig:
    background = _parse_background_style(raw.get("background"), base_dir, default)
    if raw.get("background_color") is not None:
        background = replace(background, color=_color(raw.get("background_color")))
        if raw.get("background") is None:
            background = replace(background, path=None)
    if raw.get("background_alpha") is not None:
        background = replace(
            background,
            alpha=_alpha(
                raw.get("background_alpha"),
                "background_alpha",
            ),
        )
    return background


def _parse_background_style(
    raw: Any,
    base_dir: Path,
    default: BackgroundStyleConfig,
) -> BackgroundStyleConfig:
    if raw is None:
        return default
    if isinstance(raw, str):
        return replace(default, path=_resolve_path(base_dir, raw))
    if not isinstance(raw, dict):
        raise ValueError("backgroundは文字列またはオブジェクトで指定してください。")
    unknown = set(raw).difference({"type", "path", "color", "alpha"})
    if unknown:
        raise ValueError(f"backgroundに未対応の設定があります: {sorted(unknown)}")

    background_type = raw.get("type")
    if background_type is not None and background_type not in {"image", "solid"}:
        raise ValueError("background.typeはimageまたはsolidを指定してください。")

    style = default
    if raw.get("path") is not None:
        style = replace(style, path=_resolve_path(base_dir, raw.get("path")))
    if raw.get("color") is not None:
        style = replace(style, color=_color(raw.get("color")))
        if raw.get("path") is None and background_type != "image":
            style = replace(style, path=None)
    if raw.get("alpha") is not None:
        style = replace(style, alpha=_alpha(raw.get("alpha"), "background.alpha"))

    if background_type == "solid":
        style = replace(style, path=None)
    elif background_type == "image" and style.path is None:
        raise ValueError("background.type=imageにはpathが必要です。")
    return style


def _parse_common(
    raw: dict[str, Any],
    overlay_type: str,
    default_refresh_rate_hz: float,
) -> dict[str, Any]:
    overlay_id = str(_required(raw, "id"))
    if not re.fullmatch(r"[A-Za-z0-9_-]+", overlay_id):
        raise ValueError(
            f"overlay idには英数字、_、-だけを使用してください: {overlay_id}"
        )
    background_alpha = _alpha(
        raw.get("background_alpha", 1.0),
        f"overlays.{overlay_id}.background_alpha",
    )
    return {
        "id": overlay_id,
        "type": overlay_type,
        "enabled": bool(raw.get("enabled", True)),
        "x": int(_required(raw, "x")),
        "y": int(_required(raw, "y")),
        "width": _even_positive_int(
            _required(raw, "width"),
            f"{overlay_id}.width",
        ),
        "height": _even_positive_int(
            _required(raw, "height"),
            f"{overlay_id}.height",
        ),
        "refresh_rate_hz": _positive_float(
            raw.get("refresh_rate_hz", default_refresh_rate_hz),
            f"{overlay_id}.refresh_rate_hz",
        ),
        "background_alpha": background_alpha,
    }


def _parse_text_style(
    raw: Any,
    base_dir: Path | None = None,
    default: TextStyleConfig | None = None,
) -> TextStyleConfig:
    default = default or TextStyleConfig()
    if raw is None:
        return default
    if not isinstance(raw, dict):
        raise ValueError("textはオブジェクトで指定してください。")
    unknown = set(raw).difference(
        {
            "position",
            "font_scale",
            "font_size",
            "font_path",
            "color",
            "thickness",
        }
    )
    if unknown:
        raise ValueError(f"textに未対応の設定があります: {sorted(unknown)}")
    return TextStyleConfig(
        position=_pair(raw.get("position", list(default.position)), "text.position"),
        font_scale=float(raw.get("font_scale", default.font_scale)),
        font_size=(
            default.font_size
            if raw.get("font_size") is None
            else _positive_int(raw.get("font_size"), "text.font_size")
        ),
        font_path=(
            default.font_path
            if raw.get("font_path") is None
            else _resolve_path(base_dir or Path.cwd(), raw.get("font_path"))
        ),
        color=_color(raw.get("color", list(default.color))),
        thickness=_positive_int(
            raw.get("thickness", default.thickness),
            "text.thickness",
        ),
    )


def _parse_poi_text_style(
    raw: Any,
    base_dir: Path,
    *,
    default_font_size: int,
    default_thickness: int,
) -> TextStyleConfig:
    if raw is None:
        return TextStyleConfig(
            position=(0, 0),
            font_size=default_font_size,
            color=(255, 255, 255),
            thickness=default_thickness,
        )
    if not isinstance(raw, dict):
        raise ValueError("poi_textはオブジェクトで指定してください。")
    merged = {
        "position": [0, 0],
        "font_size": default_font_size,
        "color": [255, 255, 255],
        "thickness": default_thickness,
    }
    merged.update(raw)
    return _parse_text_style(merged, base_dir)


def _parse_route_progress_feature(
    raw: Any,
    base_dir: Path,
    default_gpx_path: Path | None,
) -> RouteProgressFeatureConfig:
    if raw is None:
        return RouteProgressFeatureConfig()
    if not isinstance(raw, dict):
        raise ValueError("features.route_progressはオブジェクトで指定してください。")
    unknown = set(raw).difference(
        {
            "enabled",
            "gpx_path",
            "add_route_altitude",
            "off_route_threshold_m",
            "search_ahead_m",
            "search_behind_m",
            "progress_column",
            "altitude_column",
        }
    )
    if unknown:
        raise ValueError(
            f"features.route_progressに未対応の設定があります: {sorted(unknown)}"
        )
    gpx_path = _resolve_optional_path(
        base_dir,
        raw.get("gpx_path"),
        default_gpx_path,
    )
    if bool(raw.get("enabled", False)) and gpx_path is None:
        raise ValueError(
            "features.route_progressにはgpx_pathまたは"
            "resources.route_gpx_pathが必要です。"
        )
    return RouteProgressFeatureConfig(
        enabled=bool(raw.get("enabled", False)),
        gpx_path=gpx_path,
        add_route_altitude=bool(raw.get("add_route_altitude", False)),
        off_route_threshold_m=_positive_float(
            raw.get("off_route_threshold_m", 150.0),
            "features.route_progress.off_route_threshold_m",
        ),
        search_ahead_m=_positive_float(
            raw.get("search_ahead_m", 5000.0),
            "features.route_progress.search_ahead_m",
        ),
        search_behind_m=_positive_float(
            raw.get("search_behind_m", 300.0),
            "features.route_progress.search_behind_m",
        ),
        progress_column=str(raw.get("progress_column", "route_progress_m")),
        altitude_column=str(raw.get("altitude_column", "route_altitude_m")),
    )


def _parse_route_margin_feature(
    raw: Any,
    base_dir: Path,
    default_gpx_path: Path | None,
) -> RouteMarginFeatureConfig:
    if raw is None:
        return RouteMarginFeatureConfig()
    if not isinstance(raw, dict):
        raise ValueError("features.route_marginはオブジェクトで指定してください。")
    unknown = set(raw).difference(
        {
            "enabled",
            "gpx_path",
            "target_speed_kmh",
            "deadline_time",
            "timezone",
            "off_route_threshold_m",
            "search_ahead_m",
            "search_behind_m",
            "progress_column",
            "column",
        }
    )
    if unknown:
        raise ValueError(
            f"features.route_marginに未対応の設定があります: {sorted(unknown)}"
        )
    gpx_path = _resolve_optional_path(
        base_dir,
        raw.get("gpx_path"),
        default_gpx_path,
    )
    enabled = bool(raw.get("enabled", False))
    if enabled and gpx_path is None:
        raise ValueError(
            "features.route_marginにはgpx_pathまたは"
            "resources.route_gpx_pathが必要です。"
        )
    deadline_time = str(raw.get("deadline_time", "21:30"))
    _validate_clock_time(deadline_time)
    return RouteMarginFeatureConfig(
        enabled=enabled,
        gpx_path=gpx_path,
        target_speed_kmh=_positive_float(
            raw.get("target_speed_kmh", 15.0),
            "features.route_margin.target_speed_kmh",
        ),
        deadline_time=deadline_time,
        timezone=str(raw.get("timezone", "Asia/Tokyo")),
        off_route_threshold_m=_positive_float(
            raw.get("off_route_threshold_m", 150.0),
            "features.route_margin.off_route_threshold_m",
        ),
        search_ahead_m=_positive_float(
            raw.get("search_ahead_m", 5000.0),
            "features.route_margin.search_ahead_m",
        ),
        search_behind_m=_positive_float(
            raw.get("search_behind_m", 300.0),
            "features.route_margin.search_behind_m",
        ),
        progress_column=str(raw.get("progress_column", "route_progress_m")),
        column=str(raw.get("column", "route_margin_seconds")),
    )


def _parse_grade_feature(raw: Any) -> GradeFeatureConfig:
    if raw is None:
        return GradeFeatureConfig()
    if not isinstance(raw, dict):
        raise ValueError("features.gradeはオブジェクトで指定してください。")
    unknown = set(raw).difference({"enabled", "ride", "route"})
    if unknown:
        raise ValueError(f"features.gradeに未対応の設定があります: {sorted(unknown)}")
    enabled = bool(raw.get("enabled", False))
    return GradeFeatureConfig(
        enabled=enabled,
        ride=_parse_grade_series(
            raw.get("ride"),
            defaults=GradeSeriesConfig(),
            path="features.grade.ride",
        ),
        route=_parse_grade_series(
            raw.get("route"),
            defaults=GradeFeatureConfig().route,
            path="features.grade.route",
        ),
    )


def _parse_grade_series(
    raw: Any,
    *,
    defaults: GradeSeriesConfig,
    path: str,
) -> GradeSeriesConfig:
    if raw is None:
        return defaults
    if not isinstance(raw, dict):
        raise ValueError(f"{path}はオブジェクトで指定してください。")
    unknown = set(raw).difference(
        {
            "enabled",
            "distance_column",
            "altitude_column",
            "column",
            "window_m",
        }
    )
    if unknown:
        raise ValueError(f"{path}に未対応の設定があります: {sorted(unknown)}")
    return GradeSeriesConfig(
        enabled=bool(raw.get("enabled", defaults.enabled)),
        distance_column=str(raw.get("distance_column", defaults.distance_column)),
        altitude_column=str(raw.get("altitude_column", defaults.altitude_column)),
        column=str(raw.get("column", defaults.column)),
        window_m=_positive_float(
            raw.get("window_m", defaults.window_m),
            f"{path}.window_m",
        ),
    )


def _parse_points_of_interest(
    raw: Any,
    base_dir: Path,
    default_gpx_path: Path | None,
) -> PointsOfInterestConfig:
    if raw is None:
        return PointsOfInterestConfig()
    if not isinstance(raw, dict):
        raise ValueError("points_of_interestはオブジェクトで指定してください。")
    unknown = set(raw).difference({"enabled", "gpx_path", "sources", "items"})
    if unknown:
        raise ValueError(
            f"points_of_interestに未対応の設定があります: {sorted(unknown)}"
        )
    enabled = bool(raw.get("enabled", True))
    if not enabled:
        return PointsOfInterestConfig(enabled=False)
    gpx_path = _resolve_optional_path(
        base_dir,
        raw.get("gpx_path"),
        default_gpx_path,
    )
    sources = _parse_poi_sources(raw.get("sources", []), base_dir, gpx_path)
    items = _parse_poi_items(raw.get("items", []), base_dir)
    return PointsOfInterestConfig(
        enabled=enabled,
        gpx_path=gpx_path,
        sources=sources,
        items=items,
    )


def _parse_poi_sources(
    raw: Any,
    base_dir: Path,
    default_gpx_path: Path | None,
) -> tuple[PointOfInterestSourceConfig, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("points_of_interest.sourcesは配列で指定してください。")
    sources: list[PointOfInterestSourceConfig] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError("points_of_interest.sourcesの各要素はオブジェクトです。")
        unknown = set(item).difference(
            {"type", "gpx_path", "emoji", "icon", "icon_size"}
        )
        if unknown:
            raise ValueError(
                "points_of_interest.sourcesに未対応の設定があります: "
                f"{sorted(unknown)}"
        )
        source_type = str(_required(item, "type"))
        if source_type != "gpx_wpt":
            raise ValueError(
                "points_of_interest.sources.typeはgpx_wptを指定してください。"
            )
        source_gpx_path = (
            default_gpx_path
            if item.get("gpx_path") is None
            else _resolve_path(base_dir, item.get("gpx_path"))
        )
        if source_gpx_path is None:
            raise ValueError(
                f"points_of_interest.sources[{index}]にはgpx_pathが必要です。"
            )
        sources.append(
            PointOfInterestSourceConfig(
                type=source_type,
                gpx_path=source_gpx_path,
                emoji=str(item.get("emoji", "")),
                icon=(
                    None
                    if item.get("icon") is None
                    else _resolve_path(base_dir, item.get("icon"))
                ),
                icon_size=_optional_size(
                    item.get("icon_size"),
                    f"points_of_interest.sources[{index}].icon_size",
                ),
            )
        )
    return tuple(sources)


def _parse_poi_items(
    raw: Any,
    base_dir: Path,
) -> tuple[PointOfInterestItemConfig, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("points_of_interest.itemsは配列で指定してください。")
    items: list[PointOfInterestItemConfig] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError("points_of_interest.itemsの各要素はオブジェクトです。")
        unknown = set(item).difference(
            {
                "id",
                "label",
                "name",
                "emoji",
                "icon",
                "icon_size",
                "distance_m",
                "lat",
                "lon",
            }
        )
        if unknown:
            raise ValueError(
                f"points_of_interest.itemsに未対応の設定があります: {sorted(unknown)}"
            )
        point_id = str(_required(item, "id"))
        if not re.fullmatch(r"[A-Za-z0-9_-]+", point_id):
            raise ValueError(
                "points_of_interest.items.idには英数字、_、-だけを使用してください: "
                f"{point_id}"
            )
        lat = None if item.get("lat") is None else float(item.get("lat"))
        lon = None if item.get("lon") is None else float(item.get("lon"))
        if (lat is None) != (lon is None):
            raise ValueError(
                f"points_of_interest.items[{index}]のlat/lonは両方指定してください。"
            )
        distance_m = (
            None
            if item.get("distance_m") is None
            else _non_negative_float(
                item.get("distance_m"),
                f"points_of_interest.items[{index}].distance_m",
            )
        )
        if distance_m is None and lat is None:
            raise ValueError(
                f"points_of_interest.items[{index}]にはdistance_mまたはlat/lonが必要です。"
            )
        items.append(
            PointOfInterestItemConfig(
                id=point_id,
                label=(
                    None
                    if item.get("label") is None
                    else str(item.get("label"))
                ),
                name=None if item.get("name") is None else str(item.get("name")),
                emoji=str(item.get("emoji", "")),
                icon=(
                    None
                    if item.get("icon") is None
                    else _resolve_path(base_dir, item.get("icon"))
                ),
                icon_size=_optional_size(
                    item.get("icon_size"),
                    f"points_of_interest.items[{index}].icon_size",
                ),
                distance_m=distance_m,
                lat=lat,
                lon=lon,
            )
        )
    return tuple(items)


def _parse_traffic_signals_feature(
    raw: Any,
    base_dir: Path,
    default_gpx_path: Path | None,
) -> TrafficSignalsFeatureConfig:
    if raw is None:
        return TrafficSignalsFeatureConfig()
    if not isinstance(raw, dict):
        raise ValueError("features.traffic_signalsはオブジェクトで指定してください。")
    unknown = set(raw).difference(
        {
            "enabled",
            "route_source",
            "gpx_path",
            "cache_dir",
            "bucket_distance_m",
            "signal_match_threshold_m",
            "route_match_threshold_m",
            "bbox_margin_m",
            "overpass_url",
            "column",
        }
    )
    if unknown:
        raise ValueError(
            f"features.traffic_signalsに未対応の設定があります: {sorted(unknown)}"
        )
    route_source = str(raw.get("route_source", "gpx"))
    if route_source not in {"gpx", "fit"}:
        raise ValueError("traffic_signals.route_sourceはgpxまたはfitを指定してください。")
    gpx_path = _resolve_optional_path(
        base_dir,
        raw.get("gpx_path"),
        default_gpx_path,
    )
    if bool(raw.get("enabled", False)) and route_source == "gpx" and gpx_path is None:
        raise ValueError(
            "traffic_signals.route_source=gpxにはgpx_pathまたは"
            "resources.route_gpx_pathが必要です。"
        )
    return TrafficSignalsFeatureConfig(
        enabled=bool(raw.get("enabled", False)),
        route_source=route_source,
        gpx_path=gpx_path,
        cache_dir=_resolve_path(base_dir, raw.get("cache_dir", "cache/osm_features")),
        bucket_distance_m=_positive_float(
            raw.get("bucket_distance_m", 1000.0),
            "features.traffic_signals.bucket_distance_m",
        ),
        signal_match_threshold_m=_positive_float(
            raw.get("signal_match_threshold_m", 50.0),
            "features.traffic_signals.signal_match_threshold_m",
        ),
        route_match_threshold_m=_positive_float(
            raw.get("route_match_threshold_m", 150.0),
            "features.traffic_signals.route_match_threshold_m",
        ),
        bbox_margin_m=_positive_float(
            raw.get("bbox_margin_m", 1000.0),
            "features.traffic_signals.bbox_margin_m",
        ),
        overpass_url=str(
            raw.get("overpass_url", "https://overpass-api.de/api/interpreter")
        ),
        column=str(raw.get("column", "traffic_signal_count_per_km")),
    )


def _parse_place_names_feature(
    raw: Any,
    base_dir: Path,
    default_gpx_path: Path | None,
    default_pbf_path: Path | None,
) -> PlaceNamesFeatureConfig:
    if raw is None:
        return PlaceNamesFeatureConfig()
    if not isinstance(raw, dict):
        raise ValueError("features.place_namesはオブジェクトで指定してください。")
    unknown = set(raw).difference(
        {
            "enabled",
            "source",
            "route_source",
            "gpx_path",
            "pbf_path",
            "cache_dir",
            "admin_levels",
            "bbox_margin_m",
            "name_tags",
            "column",
        }
    )
    if unknown:
        raise ValueError(
            f"features.place_namesに未対応の設定があります: {sorted(unknown)}"
        )
    source = str(raw.get("source", "osm_pbf"))
    if source != "osm_pbf":
        raise ValueError("place_names.sourceは現在osm_pbfのみ対応しています。")
    route_source = str(raw.get("route_source", "gpx"))
    if route_source not in {"gpx", "fit"}:
        raise ValueError("place_names.route_sourceはgpxまたはfitを指定してください。")
    gpx_path = _resolve_optional_path(
        base_dir,
        raw.get("gpx_path"),
        default_gpx_path,
    )
    pbf_path = _resolve_optional_path(
        base_dir,
        raw.get("pbf_path"),
        default_pbf_path,
    )
    enabled = bool(raw.get("enabled", False))
    if enabled and route_source == "gpx" and gpx_path is None:
        raise ValueError(
            "place_names.route_source=gpxにはgpx_pathまたは"
            "resources.route_gpx_pathが必要です。"
        )
    if enabled and pbf_path is None:
        raise ValueError(
            "place_names.source=osm_pbfにはpbf_pathまたは"
            "resources.osm_pbf_pathが必要です。"
        )
    admin_levels = tuple(
        int(value)
        for value in raw.get("admin_levels", [7])
    )
    if not admin_levels or any(level <= 0 for level in admin_levels):
        raise ValueError("place_names.admin_levelsは正の整数配列で指定してください。")
    name_tags = tuple(str(value) for value in raw.get("name_tags", ["name:ja", "name", "name:en"]))
    if not name_tags:
        raise ValueError("place_names.name_tagsは1件以上指定してください。")
    return PlaceNamesFeatureConfig(
        enabled=enabled,
        source=source,
        route_source=route_source,
        gpx_path=gpx_path,
        pbf_path=pbf_path,
        cache_dir=_resolve_path(base_dir, raw.get("cache_dir", "cache/osm_features")),
        admin_levels=admin_levels,
        bbox_margin_m=_positive_float(
            raw.get("bbox_margin_m", 5000.0),
            "features.place_names.bbox_margin_m",
        ),
        name_tags=name_tags,
        column=str(raw.get("column", "place_name")),
    )


def _validate_feature_dependencies(
    overlays: tuple[OverlayDefinition, ...],
    route_progress: RouteProgressFeatureConfig,
    route_margin: RouteMarginFeatureConfig,
    grade: GradeFeatureConfig,
    traffic_signals: TrafficSignalsFeatureConfig,
    place_names: PlaceNamesFeatureConfig,
) -> None:
    signal_columns = {
        "traffic_signal_count_per_km",
        traffic_signals.column,
    }
    available_route_progress_columns: set[str] = set()
    if route_progress.enabled:
        available_route_progress_columns.add(route_progress.progress_column)
    if route_margin.enabled:
        available_route_progress_columns.add(route_margin.progress_column)
    if traffic_signals.enabled:
        available_route_progress_columns.add("route_progress_m")
    available_route_altitude_columns = (
        {route_progress.altitude_column}
        if route_progress.enabled and route_progress.add_route_altitude
        else set()
    )
    known_route_progress_columns = {"route_progress_m", route_progress.progress_column}
    known_route_altitude_columns = {"route_altitude_m", route_progress.altitude_column}
    route_margin_columns = {"route_margin_seconds", route_margin.column}
    ride_grade_columns = {"grade_percent", grade.ride.column}
    route_grade_columns = {"route_grade_percent", grade.route.column}
    place_name_columns = {"place_name", place_names.column}

    if grade.enabled and grade.route.enabled:
        if not route_progress.enabled:
            raise ValueError(
                "features.grade.route を有効にするには "
                "features.route_progress.enabled が必要です。"
            )
        if not route_progress.add_route_altitude:
            raise ValueError(
                "features.grade.route を有効にするには "
                "features.route_progress.add_route_altitude が必要です。"
            )

    for overlay in overlays:
        if not overlay.enabled:
            continue
        if (
            isinstance(overlay, (MetricOverlayConfig, GraphOverlayConfig))
            and overlay.column in signal_columns
            and not traffic_signals.enabled
        ):
            raise ValueError(
                f"overlay {overlay.id} は {overlay.column} を参照していますが、"
                "features.traffic_signals が有効ではありません。"
            )
        if isinstance(overlay, TextColumnOverlayConfig):
            if overlay.column in place_name_columns and not place_names.enabled:
                raise ValueError(
                    f"overlay {overlay.id} は {overlay.column} を参照していますが、"
                    "features.place_names が有効ではありません。"
                )
        if isinstance(overlay, (MetricOverlayConfig, GraphOverlayConfig)):
            references = {overlay.column}
            if isinstance(overlay, GraphOverlayConfig) and overlay.x_column is not None:
                references.add(overlay.x_column)
            if references.intersection(route_margin_columns) and not route_margin.enabled:
                raise ValueError(
                    f"overlay {overlay.id} は route_margin_seconds を参照していますが、"
                    "features.route_margin が有効ではありません。"
                )
            if references.intersection(ride_grade_columns) and not (
                grade.enabled and grade.ride.enabled
            ):
                raise ValueError(
                    f"overlay {overlay.id} は grade_percent を参照していますが、"
                    "features.grade.ride が有効ではありません。"
                )
            if references.intersection(route_grade_columns) and not (
                grade.enabled and grade.route.enabled
            ):
                raise ValueError(
                    f"overlay {overlay.id} は route_grade_percent を参照していますが、"
                    "features.grade.route が有効ではありません。"
                )
            if (
                references.intersection(known_route_progress_columns)
                and not references.intersection(available_route_progress_columns)
            ):
                raise ValueError(
                    f"overlay {overlay.id} は route_progress_m を参照していますが、"
                    "features.route_progress または features.traffic_signals が有効ではありません。"
                )
            if (
                references.intersection(known_route_altitude_columns)
                and not references.intersection(available_route_altitude_columns)
            ):
                raise ValueError(
                    f"overlay {overlay.id} は route_altitude_m を参照していますが、"
                    "features.route_progress.add_route_altitude が有効ではありません。"
                )


def _parse_graph_value_text(
    raw: dict[str, Any],
    base_dir: Path,
    default_text: TextStyleConfig,
) -> TextStyleConfig:
    legacy_style = TextStyleConfig(
        position=_pair(raw.get("value_position", [12, 34]), "graph.value_position"),
        font_scale=float(raw.get("value_font_scale", 0.9)),
        font_size=(
            None
            if raw.get("value_font_size") is None
            else _positive_int(raw.get("value_font_size"), "graph.value_font_size")
        ),
        font_path=(
            None
            if raw.get("value_font_path") is None
            else _resolve_path(base_dir, raw.get("value_font_path"))
        ),
        color=_color(raw.get("text_color", list(default_text.color))),
        thickness=_positive_int(raw.get("value_thickness", 2), "graph.value_thickness"),
    )
    value_text = raw.get("value_text")
    if value_text is None:
        return legacy_style
    if not isinstance(value_text, dict):
        raise ValueError("graph.value_textはオブジェクトで指定してください。")
    merged = {
        "position": list(legacy_style.position),
        "font_scale": legacy_style.font_scale,
        "color": list(legacy_style.color),
        "thickness": legacy_style.thickness,
    }
    if legacy_style.font_size is not None:
        merged["font_size"] = legacy_style.font_size
    if legacy_style.font_path is not None:
        merged["font_path"] = str(legacy_style.font_path)
    merged.update(value_text)
    return _parse_text_style(merged, base_dir)


def _parse_directional_icons(
    raw: Any,
    base_dir: Path,
) -> DirectionalIconsConfig | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("directional_iconsはオブジェクトで指定してください。")
    required_directions = {"north", "east", "south", "west"}
    missing = required_directions.difference(raw)
    unknown = set(raw).difference(required_directions)
    if missing:
        raise ValueError(
            f"directional_iconsに不足があります: {sorted(missing)}"
        )
    if unknown:
        raise ValueError(
            f"directional_iconsに未対応の方向があります: {sorted(unknown)}"
        )
    return DirectionalIconsConfig(
        north=_resolve_path(base_dir, raw["north"]),
        east=_resolve_path(base_dir, raw["east"]),
        south=_resolve_path(base_dir, raw["south"]),
        west=_resolve_path(base_dir, raw["west"]),
    )


def _mapping(
    raw: dict[str, Any],
    key: str,
    *,
    required: bool = True,
) -> dict[str, Any]:
    value = raw.get(key)
    if value is None and not required:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{key}はオブジェクトで指定してください。")
    return value


def _required(raw: dict[str, Any], key: str) -> Any:
    if key not in raw:
        raise ValueError(f"必須設定がありません: {key}")
    return raw[key]


def _resolve_path(base_dir: Path, value: Any) -> Path:
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else (base_dir / path).resolve()


def _resolve_optional_path(
    base_dir: Path,
    value: Any,
    default: Path | None = None,
) -> Path | None:
    return default if value is None else _resolve_path(base_dir, value)


def _optional_absolute_path(value: Any, name: str) -> Path | None:
    if value is None:
        return None
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{name}は絶対パスで指定してください。")
    return path


def _positive_float(value: Any, name: str) -> float:
    number = float(value)
    if number <= 0:
        raise ValueError(f"{name}は正の値で指定してください。")
    return number


def _non_negative_float(value: Any, name: str) -> float:
    number = float(value)
    if number < 0:
        raise ValueError(f"{name}は0以上の値で指定してください。")
    return number


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _alpha(value: Any, name: str) -> float:
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{name}は0.0から1.0で指定してください。")
    return number


def _positive_int(value: Any, name: str) -> int:
    number = int(value)
    if number <= 0:
        raise ValueError(f"{name}は正の整数で指定してください。")
    return number


def _interpolation(value: Any) -> str:
    method = str(value)
    if method not in {"linear", "previous"}:
        raise ValueError("interpolationはlinearまたはpreviousを指定してください。")
    return method


def _validate_clock_time(value: str) -> None:
    """deadline_timeをHH:MMまたはYYYY-MM-DD HH:MM形式で検証する。"""
    if " " in value:
        # YYYY-MM-DD HH:MM 形式
        try:
            datetime.datetime.strptime(value, "%Y-%m-%d %H:%M")
        except (ValueError, TypeError) as error:
            raise ValueError(
                "deadline_timeはYYYY-MM-DD HH:MM形式で指定してください。"
            ) from error
    else:
        # 後方互換: HH:MM 形式
        try:
            hour_text, minute_text = value.split(":", maxsplit=1)
            hour = int(hour_text)
            minute = int(minute_text)
        except (ValueError, TypeError) as error:
            raise ValueError(
                "deadline_timeはHH:MMまたはYYYY-MM-DD HH:MM形式で指定してください。"
            ) from error
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("deadline_timeは有効な時刻を指定してください。")


def _even_positive_int(value: Any, name: str) -> int:
    number = _positive_int(value, name)
    if number % 2:
        raise ValueError(f"{name}は動画出力のため偶数で指定してください。")
    return number


def _pair(value: Any, name: str) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{name}は2要素の配列で指定してください。")
    return int(value[0]), int(value[1])


def _quad(value: Any, name: str) -> tuple[int, int, int, int]:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError(f"{name}は4要素の配列で指定してください。")
    result = tuple(int(item) for item in value)
    if any(item < 0 for item in result):
        raise ValueError(f"{name}は0以上の整数で指定してください。")
    return result


def _optional_size(value: Any, name: str) -> tuple[int, int] | None:
    if value is None:
        return None
    width, height = _pair(value, name)
    if width <= 0 or height <= 0:
        raise ValueError(f"{name}は正の整数で指定してください。")
    return width, height


def _color(value: Any) -> Color:
    color = _pair_or_triplet(value, "text.color", 3)
    if any(component < 0 or component > 255 for component in color):
        raise ValueError("text.colorは0から255の範囲で指定してください。")
    return color


def _pair_or_triplet(value: Any, name: str, length: int) -> tuple[int, ...]:
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"{name}は{length}要素の配列で指定してください。")
    return tuple(int(item) for item in value)


def _check_keys(
    raw: dict[str, Any],
    *,
    common: set[str],
    specific: set[str],
) -> None:
    unknown = set(raw).difference(common | specific)
    if unknown:
        raise ValueError(f"overlayに未対応の設定があります: {sorted(unknown)}")
