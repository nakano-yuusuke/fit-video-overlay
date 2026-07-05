"""現在位置を中心にした地図フレームの生成。"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from .frames import FrameMaker
from .gpx_route import GpxRoute
from .image_overlay import load_rgba_icon, overlay_rgba_center
from .map_geometry import MapGeometry
from .map_renderer import StaticMapRenderer
from .poi import PointOfInterest
from .poi_rendering import draw_poi_marker, load_poi_icons
from .text_draw import draw_text
from .time_utils import to_utc_timestamp


logger = logging.getLogger(__name__)


class MapStaticFrameMaker(FrameMaker):
    """時刻に対応する位置を検索し、静的地図から表示範囲を切り出す。"""

    def __init__(
        self,
        fps: float,
        data: pd.DataFrame,
        icon_path: Path,
        cache_dir: Path,
        *,
        width: int = 400,
        height: int = 400,
        background_alpha: float = 1.0,
        viewport_mode: str = "follow",
        display_size_m: float = 200.0,
        track_margin_m: float | None = None,
        gpx_path: Path | None = None,
        show_route: bool = False,
        show_track: bool = False,
        route_color: tuple[int, int, int] = (255, 180, 0),
        track_color: tuple[int, int, int] = (0, 255, 255),
        route_thickness: int = 4,
        track_thickness: int = 4,
        icon_size: tuple[int, int] | None = None,
        directional_icons: dict[str, Path] | None = None,
        use_icon: bool = True,
        circle_radius: int = 12,
        tile_zoom: int = 18,
        interpolation: str = "linear",
        max_interpolation_gap_seconds: float = 2.0,
        direction_window_radius: int = 3,
        direction_change_confirmations: int = 3,
        direction_min_distance_m: float = 2.0,
        debug: bool = False,
        show_poi: bool = False,
        poi_font_size: int | None = None,
        poi_font_path: Path | None = None,
        poi_color: tuple[int, int, int] = (255, 255, 255),
        poi_thickness: int = 3,
        poi_icon_size: tuple[int, int] | None = None,
        points_of_interest: tuple[PointOfInterest, ...] = (),
    ) -> None:
        super().__init__(fps, data)
        self.viewport_width = width
        self.viewport_height = height
        self.background_alpha = background_alpha
        self.viewport_mode = viewport_mode
        self.display_width_m = display_size_m
        self.pixels_per_meter = self.viewport_width / self.display_width_m
        self.display_height_m = self.viewport_height / self.pixels_per_meter
        self.track_margin_m = (
            display_size_m / 2
            if track_margin_m is None
            else track_margin_m
        )
        self.route = None if gpx_path is None else GpxRoute(gpx_path)
        self.show_route = show_route
        self.show_track = show_track
        self.route_color = route_color
        self.track_color = track_color
        self.route_thickness = route_thickness
        self.track_thickness = track_thickness
        self.renderer = StaticMapRenderer(cache_dir, zoom=tile_zoom)
        self.icons = self._load_icons(
            icon_path,
            icon_size=icon_size,
            directional_icons=directional_icons,
        )
        self.use_icon = use_icon
        self.debug = debug
        self.circle_radius = circle_radius
        self.interpolation = interpolation
        self.max_interpolation_gap_seconds = max_interpolation_gap_seconds
        self.direction_window_radius = direction_window_radius
        self.direction_change_confirmations = direction_change_confirmations
        self.direction_min_distance_m = direction_min_distance_m
        self.show_poi = show_poi
        self.poi_font_size = poi_font_size or 20
        self.poi_font_path = poi_font_path
        self.poi_color = poi_color
        self.poi_thickness = poi_thickness
        self.points_of_interest = points_of_interest
        self.poi_icons = (
            load_poi_icons(
                points_of_interest,
                icon_size_override=poi_icon_size,
            )
            if show_poi
            else {}
        )
        self.geometry: MapGeometry | None = None
        self.full_image: np.ndarray | None = None
        self.track_points: np.ndarray | None = None
        self.track_times: pd.DatetimeIndex | None = None
        self.window_has_position = True
        self.row_directions = self._build_row_directions()

    @property
    def has_alpha(self) -> bool:
        return self.background_alpha < 1.0

    @staticmethod
    def _load_icons(
        default_path: Path,
        *,
        icon_size: tuple[int, int] | None,
        directional_icons: dict[str, Path] | None,
    ) -> dict[str, np.ndarray]:
        if directional_icons is None:
            return {
                "default": load_rgba_icon(default_path, icon_size),
            }
        return {
            direction: load_rgba_icon(path, icon_size)
            for direction, path in directional_icons.items()
        }

    def _build_row_directions(self) -> list[str]:
        """各FIT行へ、前後の座標から平滑化した進行方向を割り当てる。"""
        if self.data is None or self.data.empty:
            return []
        n = len(self.data)
        r = self.direction_window_radius
        idx = np.arange(n)
        start_idx = np.maximum(0, idx - r)
        end_idx = np.minimum(n - 1, idx + r)

        # NaN のGPS欠損行を前後の有効値で補完する（元のdropna処理の近似）。
        lon = self.data["position_long"].ffill().bfill().to_numpy(dtype=float, na_value=np.nan)
        lat = self.data["position_lat"].ffill().bfill().to_numpy(dtype=float, na_value=np.nan)

        start_lon = lon[start_idx]
        start_lat = lat[start_idx]
        end_lon = lon[end_idx]
        end_lat = lat[end_idx]

        mean_lat = (start_lat + end_lat) / 2.0
        east_m = (end_lon - start_lon) * 111320.0 * np.cos(np.radians(mean_lat))
        north_m = (end_lat - start_lat) * 110540.0
        dist_m = np.hypot(east_m, north_m)

        is_nan = np.isnan(east_m) | np.isnan(north_m)
        is_valid = ~is_nan & (dist_m >= self.direction_min_distance_m)

        abs_east = np.abs(east_m)
        abs_north = np.abs(north_m)
        use_ew = abs_east >= abs_north

        candidates: list[str | None] = [
            None
            if not is_valid[i]
            else ("east" if east_m[i] > 0 else "west")
            if use_ew[i]
            else ("north" if north_m[i] > 0 else "south")
            for i in range(n)
        ]
        return self._stabilize_directions(candidates)

    def _stabilize_directions(
        self,
        candidates: list[str | None],
    ) -> list[str]:
        active_direction: str | None = None
        pending_direction: str | None = None
        pending_count = 0
        directions: list[str | None] = []

        for candidate in candidates:
            if candidate is None:
                pending_direction = None
                pending_count = 0
            elif active_direction is None:
                active_direction = candidate
            elif candidate == active_direction:
                pending_direction = None
                pending_count = 0
            elif candidate == pending_direction:
                pending_count += 1
            else:
                pending_direction = candidate
                pending_count = 1

            if (
                pending_direction is not None
                and pending_count >= self.direction_change_confirmations
            ):
                active_direction = pending_direction
                pending_direction = None
                pending_count = 0

            directions.append(active_direction)

        first_direction = next(
            (direction for direction in directions if direction is not None),
            "north",
        )
        return [
            first_direction if direction is None else direction
            for direction in directions
        ]

    @staticmethod
    def _direction_between(
        start: pd.Series,
        end: pd.Series,
        *,
        min_distance_m: float = 0.0,
    ) -> str | None:
        if start.isna().any() or end.isna().any():
            return None
        start_lon = float(start["position_long"])
        start_lat = float(start["position_lat"])
        end_lon = float(end["position_long"])
        end_lat = float(end["position_lat"])
        mean_lat = (start_lat + end_lat) / 2
        east_m = (
            (end_lon - start_lon)
            * 111320.0
            * np.cos(np.radians(mean_lat))
        )
        north_m = (end_lat - start_lat) * 110540.0
        if np.hypot(east_m, north_m) < min_distance_m:
            return None
        if abs(east_m) >= abs(north_m):
            return "east" if east_m > 0 else "west"
        return "north" if north_m > 0 else "south"

    def _direction_at(self, frame_time: pd.Timestamp) -> str:
        """指定時刻の直前行に割り当てた平滑化済み方向を返す。"""
        assert self.data is not None
        previous_index = self.data.index.searchsorted(
            frame_time,
            side="right",
        ) - 1
        if previous_index < 0:
            return self.row_directions[0] if self.row_directions else "north"

        if not self.row_directions:
            return "north"
        return self.row_directions[
            min(previous_index, len(self.row_directions) - 1)
        ]

    def set_window(self, shot_time: pd.Timestamp, video_length: float) -> None:
        """対象動画の撮影時間内に通る位置から地図範囲を決定する。"""
        if self.data is None or self.data.empty:
            raise ValueError("地図用データがありません。")

        shot_time = to_utc_timestamp(shot_time)
        end_time = shot_time + pd.Timedelta(seconds=video_length)
        # route_overview の geometry は全FITデータで決まり動画間で変化しない。
        # warmup() で事前生成した full_image を fork で子プロセスへ引き継ぐため保持する。
        if self.viewport_mode != "route_overview":
            self.full_image = None

        # FITの記録範囲外では全データへフォールバックせず、No dataを表示する。
        if end_time < self.data.index[0] or shot_time > self.data.index[-1]:
            self.geometry = None
            self.window_has_position = False
            if self.debug:
                logger.debug(
                    "map_no_position_data shot_time=%s end_time=%s",
                    shot_time,
                    end_time,
                )
            return

        if self.viewport_mode == "route_overview":
            positions = self.data[
                ["position_long", "position_lat"]
            ].dropna()
            if self.route is not None:
                route_positions = pd.DataFrame(
                    {
                        "position_long": self.route.longitudes,
                        "position_lat": self.route.latitudes,
                    }
                )
                positions = pd.concat(
                    [positions.reset_index(drop=True), route_positions],
                    ignore_index=True,
                )
            if self.show_poi:
                poi_positions = self._poi_positions()
                if not poi_positions.empty:
                    positions = pd.concat(
                        [positions.reset_index(drop=True), poi_positions],
                        ignore_index=True,
                    )
        else:
            window = self.data.loc[
                (self.data.index >= shot_time) & (self.data.index <= end_time)
            ]
            positions = window[["position_long", "position_lat"]].dropna()

        # 記録行がない停止区間では、動画開始時点以前の最後の位置を使う。
        if positions.empty and self.viewport_mode == "follow":
            previous_index = self.data.index.searchsorted(
                shot_time,
                side="right",
            ) - 1
            if previous_index >= 0:
                positions = self.data.iloc[[previous_index]][
                    ["position_long", "position_lat"]
                ].dropna()

        if positions.empty:
            self.geometry = None
            self.window_has_position = False
            return

        if self.viewport_mode == "route_overview":
            self.geometry = MapGeometry.fit_positions_to_viewport(
                positions,
                viewport_width_px=self.viewport_width,
                viewport_height_px=self.viewport_height,
                track_margin_m=self.track_margin_m,
            )
        else:
            self.geometry = MapGeometry.from_positions(
                positions,
                pixels_per_meter=self.pixels_per_meter,
                display_width_m=self.display_width_m,
                display_height_m=self.display_height_m,
                viewport_width_px=self.viewport_width,
                viewport_height_px=self.viewport_height,
                track_margin_m=self.track_margin_m,
            )
        self._build_track_points()
        self.window_has_position = True
        if self.debug:
            logger.debug("map_bbox bbox=%s", self.geometry.bbox)

    def prepare_video(self, shot_time: pd.Timestamp, duration: float) -> None:
        self.shot_time = shot_time
        self.set_window(shot_time, duration)

    def warmup(self) -> None:
        """route_overview の静的ベース画像を親プロセスで事前レンダリングする。"""
        if self.viewport_mode == "route_overview" and self.full_image is None:
            self._prepare_static_map()

    def _prepare_static_map(self) -> None:
        if not self.window_has_position:
            return
        if self.geometry is None:
            if self.data is None or self.data.empty:
                raise ValueError("地図用データがありません。")
            duration = (self.data.index[-1] - self.data.index[0]).total_seconds()
            self.set_window(self.data.index[0], duration)
        assert self.geometry is not None
        self.full_image = self._with_background_alpha(
            self.renderer.render(self.geometry)
        )
        if self.show_route and self.route is not None:
            self._draw_route(self.full_image)
        if self.show_poi and not self.show_track:
            self._draw_pois(self.full_image)

    def make_frame(self, seconds: float) -> np.ndarray:
        if not self.window_has_position:
            return self._no_data_frame()
        if self.full_image is None:
            self._prepare_static_map()
        assert self.full_image is not None
        assert self.geometry is not None
        assert self.data is not None

        frame_time = self.frame_time(seconds)
        position = self.values_at(
            frame_time,
            ["position_long", "position_lat"],
            interpolation=self.interpolation,
            max_interpolation_gap_seconds=self.max_interpolation_gap_seconds,
        )
        if position is None:
            return self._no_data_frame()

        if pd.isna(position["position_long"]) or pd.isna(position["position_lat"]):
            return self._no_data_frame()

        image = self.full_image
        if self.show_track:
            image = self.full_image.copy()
        if self.show_track:
            self._draw_track(image, frame_time)
            if self.show_poi:
                self._draw_pois(image)

        image_height, image_width = image.shape[:2]
        center_x, center_y = self.geometry.position_to_pixels(
            float(position["position_long"]),
            float(position["position_lat"]),
            image_width=image_width,
            image_height=image_height,
        )
        if self.viewport_mode == "route_overview":
            frame = image.copy()
            relative_x, relative_y = center_x, center_y
        else:
            frame, relative_x, relative_y = self._crop_around(
                image,
                center_x,
                center_y,
            )
        if self.use_icon:
            self._overlay_icon(
                frame,
                relative_x,
                relative_y,
                self._direction_at(frame_time),
            )
        else:
            self._overlay_circle(frame, relative_x, relative_y)
        self._overlay_attribution(frame)
        return frame

    def _crop_around(
        self,
        image: np.ndarray,
        center_x: int,
        center_y: int,
    ) -> tuple[np.ndarray, int, int]:
        half_width = self.viewport_width // 2
        half_height = self.viewport_height // 2
        x0 = center_x - half_width
        y0 = center_y - half_height

        if (
            x0 >= 0
            and y0 >= 0
            and x0 + self.viewport_width <= image.shape[1]
            and y0 + self.viewport_height <= image.shape[0]
        ):
            cropped = image[
                y0 : y0 + self.viewport_height,
                x0 : x0 + self.viewport_width,
            ].copy()
            return cropped, half_width, half_height

        padded = cv2.copyMakeBorder(
            image,
            half_height,
            half_height,
            half_width,
            half_width,
            cv2.BORDER_REPLICATE,
        )
        center_x += half_width
        center_y += half_height
        x0 = center_x - half_width
        y0 = center_y - half_height
        cropped = padded[
            y0 : y0 + self.viewport_height,
            x0 : x0 + self.viewport_width,
        ].copy()
        return cropped, half_width, half_height

    def _build_track_points(self) -> None:
        if not self.show_track or self.geometry is None or self.data is None:
            self.track_points = None
            self.track_times = None
            return
        positions = self.data[
            ["position_long", "position_lat"]
        ].dropna()
        self.track_times = positions.index
        self.track_points = self._positions_to_pixels(
            positions["position_long"].to_numpy(),
            positions["position_lat"].to_numpy(),
        )

    def _positions_to_pixels(
        self,
        longitudes: np.ndarray,
        latitudes: np.ndarray,
    ) -> np.ndarray:
        assert self.geometry is not None
        points = [
            self.geometry.position_to_pixels(
                float(lon),
                float(lat),
                image_width=self.geometry.width_px,
                image_height=self.geometry.height_px,
                clip=False,
            )
            for lon, lat in zip(longitudes, latitudes)
        ]
        return np.asarray(points, dtype=np.int32).reshape((-1, 1, 2))

    def _draw_route(self, image: np.ndarray) -> None:
        assert self.route is not None
        points = self._positions_to_pixels(
            self.route.longitudes,
            self.route.latitudes,
        )
        cv2.polylines(
            image,
            [points],
            False,
            self._draw_color(self.route_color),
            self.route_thickness,
            cv2.LINE_AA,
        )

    def _draw_track(
        self,
        image: np.ndarray,
        frame_time: pd.Timestamp,
    ) -> None:
        if self.track_points is None or self.track_times is None:
            return
        point_count = self.track_times.searchsorted(
            frame_time,
            side="right",
        )
        if point_count < 2:
            return
        cv2.polylines(
            image,
            [self.track_points[:point_count]],
            False,
            self._draw_color(self.track_color),
            self.track_thickness,
            cv2.LINE_AA,
        )

    def _poi_positions(self) -> pd.DataFrame:
        rows: list[dict[str, float]] = []
        for poi in self.points_of_interest:
            lon = poi.lon
            lat = poi.lat
            if (
                (lon is None or lat is None)
                and poi.distance_m is not None
                and self.route is not None
            ):
                lon, lat = self.route.position_at(poi.distance_m)
            if lon is None or lat is None:
                continue
            rows.append({"position_long": lon, "position_lat": lat})
        return pd.DataFrame(rows, columns=["position_long", "position_lat"])

    def _draw_pois(self, image: np.ndarray) -> None:
        if self.geometry is None:
            return
        image_height, image_width = image.shape[:2]
        for poi in self.points_of_interest:
            lon = poi.lon
            lat = poi.lat
            if (
                (lon is None or lat is None)
                and poi.distance_m is not None
                and self.route is not None
            ):
                lon, lat = self.route.position_at(poi.distance_m)
            if lon is None or lat is None:
                continue
            x, y = self.geometry.position_to_pixels(
                float(lon),
                float(lat),
                image_width=image_width,
                image_height=image_height,
                clip=False,
            )
            if (
                x < -200
                or x > image_width + 200
                or y < -80
                or y > image_height + 80
            ):
                continue
            label_offset = draw_poi_marker(
                image,
                poi,
                x,
                y,
                icons=self.poi_icons,
                color=self.poi_color,
                font_path=self.poi_font_path,
                font_size=self.poi_font_size,
                thickness=self.poi_thickness,
            )
            rendered = draw_text(
                image,
                poi.display_text,
                (x + label_offset, y - 7),
                color=self.poi_color,
                font_path=self.poi_font_path,
                font_size=self.poi_font_size,
                stroke_width=max(0, self.poi_thickness - 1),
                stroke_fill=(0, 0, 0),
            )
            image[:, :] = rendered

    def _overlay_icon(
        self,
        background: np.ndarray,
        cx: int,
        cy: int,
        direction: str,
    ) -> None:
        icon = self.icons.get(direction, self.icons.get("default"))
        if icon is None:
            raise ValueError(f"{direction}方向のアイコンがありません。")
        overlay_rgba_center(background, icon, cx, cy)

    def _overlay_circle(self, background: np.ndarray, cx: int, cy: int) -> None:
        center = (cx, cy)
        cv2.circle(
            background,
            center,
            self.circle_radius,
            self._draw_color((0, 0, 255)),
            3,
            cv2.LINE_AA,
        )
        cv2.circle(
            background,
            center,
            max(1, self.circle_radius // 3),
            self._draw_color((0, 0, 255)),
            -1,
            cv2.LINE_AA,
        )

    def _overlay_attribution(self, background: np.ndarray) -> None:
        lines = ["(c) OpenStreetMap contributors", "openstreetmap.org/copyright"]
        y = background.shape[0] - 15
        for text in reversed(lines):
            cv2.putText(
                background,
                text,
                (15, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                self._draw_color((0, 0, 0)),
                4,
                cv2.LINE_AA,
            )
            cv2.putText(
                background,
                text,
                (15, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                self._draw_color((255, 255, 255)),
                2,
                cv2.LINE_AA,
            )
            y -= 18

    def _no_data_frame(self) -> np.ndarray:
        frame = np.full(
            (self.viewport_height, self.viewport_width, 4 if self.has_alpha else 3),
            (0, 0, 0, int(round(self.background_alpha * 255)))
            if self.has_alpha
            else (0, 0, 0),
            dtype=np.uint8,
        )
        cv2.putText(
            frame,
            "No data",
            (50, self.viewport_height // 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.5,
            self._draw_color((255, 255, 255)),
            3,
            cv2.LINE_AA,
        )
        return frame

    def _with_background_alpha(self, image: np.ndarray) -> np.ndarray:
        if not self.has_alpha:
            return image
        alpha = np.full(
            (*image.shape[:2], 1),
            int(round(self.background_alpha * 255)),
            dtype=np.uint8,
        )
        return np.concatenate([image, alpha], axis=2)

    def _draw_color(self, color: tuple[int, int, int]) -> tuple[int, ...]:
        if self.has_alpha:
            return (*color, 255)
        return color
