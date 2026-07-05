"""GPXルートの累積距離計算とFIT位置の進捗マッチング。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class GpxWaypoint:
    name: str
    lat: float
    lon: float
    elevation_m: float | None = None
    type: str | None = None


class GpxRoute:
    """順序付きGPX点群を、距離計算しやすい平面座標へ変換する。"""

    def __init__(self, path: Path, *, grid_size_m: float = 250.0) -> None:
        latitudes, longitudes, elevations = self._load_track_points(path)
        self._initialize(
            latitudes,
            longitudes,
            elevations,
            grid_size_m=grid_size_m,
        )

    @classmethod
    def from_points(
        cls,
        latitudes: np.ndarray,
        longitudes: np.ndarray,
        elevations: np.ndarray | None = None,
        *,
        grid_size_m: float = 250.0,
    ) -> GpxRoute:
        route = cls.__new__(cls)
        route._initialize(
            latitudes,
            longitudes,
            elevations,
            grid_size_m=grid_size_m,
        )
        return route

    def _initialize(
        self,
        latitudes: np.ndarray,
        longitudes: np.ndarray,
        elevations: np.ndarray | None,
        *,
        grid_size_m: float,
    ) -> None:
        if len(latitudes) < 2:
            raise ValueError("ルートの点が不足しています。")

        self.origin_lat = float(np.mean(latitudes))
        self.origin_lon = float(np.mean(longitudes))
        self.latitudes = latitudes
        self.longitudes = longitudes
        self.elevations = elevations
        self.lon_m_per_deg = max(
            1e-9,
            111320.0 * np.cos(np.radians(self.origin_lat)),
        )
        self.lat_m_per_deg = 110540.0
        self.x = (longitudes - self.origin_lon) * self.lon_m_per_deg
        self.y = (latitudes - self.origin_lat) * self.lat_m_per_deg
        self.segment_dx = np.diff(self.x)
        self.segment_dy = np.diff(self.y)
        self.segment_length = np.hypot(self.segment_dx, self.segment_dy)
        self.segment_length_squared = np.maximum(
            self.segment_length**2,
            1e-12,
        )
        self.cumulative_distance = np.concatenate(
            ([0.0], np.cumsum(self.segment_length))
        )
        self.total_distance_m = float(self.cumulative_distance[-1])
        self.grid_size_m = grid_size_m
        self.grid = self._build_grid()

    @staticmethod
    def _load_track_points(
        path: Path,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
        latitudes: list[float] = []
        longitudes: list[float] = []
        elevations: list[float] = []
        for _, element in ET.iterparse(path, events=("end",)):
            if element.tag.endswith("trkpt"):
                latitudes.append(float(element.attrib["lat"]))
                longitudes.append(float(element.attrib["lon"]))
                elevation = np.nan
                for child in element:
                    if child.tag.endswith("ele") and child.text is not None:
                        elevation = float(child.text)
                        break
                elevations.append(elevation)
                element.clear()
        elevation_array = np.asarray(elevations, dtype=float)
        return (
            np.asarray(latitudes),
            np.asarray(longitudes),
            elevation_array if np.isfinite(elevation_array).any() else None,
        )

    @staticmethod
    def load_waypoints(path: Path) -> list[GpxWaypoint]:
        waypoints: list[GpxWaypoint] = []
        for _, element in ET.iterparse(path, events=("end",)):
            if element.tag.endswith("trkpt"):
                element.clear()
                continue
            if not element.tag.endswith("wpt"):
                continue
            name = ""
            waypoint_type: str | None = None
            elevation_m: float | None = None
            for child in element:
                if child.text is None:
                    continue
                if child.tag.endswith("name"):
                    name = child.text.strip()
                elif child.tag.endswith("type"):
                    waypoint_type = child.text.strip()
                elif child.tag.endswith("ele"):
                    elevation_m = float(child.text)
            waypoints.append(
                GpxWaypoint(
                    name=name,
                    lat=float(element.attrib["lat"]),
                    lon=float(element.attrib["lon"]),
                    elevation_m=elevation_m,
                    type=waypoint_type,
                )
            )
            element.clear()
        return waypoints

    def _build_grid(self) -> dict[tuple[int, int], np.ndarray]:
        cells: dict[tuple[int, int], list[int]] = defaultdict(list)
        for segment_index in range(len(self.segment_length)):
            min_x = min(self.x[segment_index], self.x[segment_index + 1])
            max_x = max(self.x[segment_index], self.x[segment_index + 1])
            min_y = min(self.y[segment_index], self.y[segment_index + 1])
            max_y = max(self.y[segment_index], self.y[segment_index + 1])
            cell_x_min = int(np.floor(min_x / self.grid_size_m))
            cell_x_max = int(np.floor(max_x / self.grid_size_m))
            cell_y_min = int(np.floor(min_y / self.grid_size_m))
            cell_y_max = int(np.floor(max_y / self.grid_size_m))
            for cell_x in range(cell_x_min, cell_x_max + 1):
                for cell_y in range(cell_y_min, cell_y_max + 1):
                    cells[(cell_x, cell_y)].append(segment_index)
        return {
            cell: np.asarray(sorted(set(indices)), dtype=np.int32)
            for cell, indices in cells.items()
        }

    def to_xy(self, lon: float, lat: float) -> tuple[float, float]:
        return (
            (lon - self.origin_lon) * self.lon_m_per_deg,
            (lat - self.origin_lat) * self.lat_m_per_deg,
        )

    def position_at(self, progress_m: float) -> tuple[float, float]:
        progress = float(np.clip(progress_m, 0.0, self.total_distance_m))
        lon = np.interp(progress, self.cumulative_distance, self.longitudes)
        lat = np.interp(progress, self.cumulative_distance, self.latitudes)
        return float(lon), float(lat)

    def altitude_at(self, progress_m: float) -> float:
        if self.elevations is None:
            return float("nan")
        valid = np.isfinite(self.elevations)
        if not valid.any():
            return float("nan")
        progress = float(np.clip(progress_m, 0.0, self.total_distance_m))
        return float(
            np.interp(
                progress,
                self.cumulative_distance[valid],
                self.elevations[valid],
            )
        )

    def altitudes_at(self, progress_m: np.ndarray) -> np.ndarray:
        if self.elevations is None:
            return np.full(len(progress_m), np.nan)
        valid = np.isfinite(self.elevations)
        if not valid.any():
            return np.full(len(progress_m), np.nan)
        clipped = np.clip(progress_m.astype(float), 0.0, self.total_distance_m)
        result = np.interp(
            clipped,
            self.cumulative_distance[valid],
            self.elevations[valid],
        )
        result[~np.isfinite(progress_m)] = np.nan
        return result

    def progress_for_position(
        self,
        lon: float,
        lat: float,
        *,
        search_radius_m: float = 1000.0,
    ) -> tuple[float, float]:
        x, y = self.to_xy(lon, lat)
        candidates = self.candidate_segments(
            x,
            y,
            search_radius_m=search_radius_m,
        )
        distance, progress, _, _ = self.project(x, y, candidates)
        best = int(np.argmin(distance))
        return float(progress[best]), float(distance[best])

    def candidate_segments(
        self,
        x: float,
        y: float,
        *,
        search_radius_m: float,
    ) -> np.ndarray:
        cell_x = int(np.floor(x / self.grid_size_m))
        cell_y = int(np.floor(y / self.grid_size_m))
        cell_radius = max(
            1,
            int(np.ceil(search_radius_m / self.grid_size_m)),
        )
        candidates: list[np.ndarray] = []
        for offset_x in range(-cell_radius, cell_radius + 1):
            for offset_y in range(-cell_radius, cell_radius + 1):
                indices = self.grid.get((cell_x + offset_x, cell_y + offset_y))
                if indices is not None:
                    candidates.append(indices)
        if not candidates:
            return np.arange(len(self.segment_length), dtype=np.int32)
        return np.unique(np.concatenate(candidates))

    def project(
        self,
        x: float,
        y: float,
        segment_indices: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        start_x = self.x[segment_indices]
        start_y = self.y[segment_indices]
        dx = self.segment_dx[segment_indices]
        dy = self.segment_dy[segment_indices]
        ratio = (
            (x - start_x) * dx + (y - start_y) * dy
        ) / self.segment_length_squared[segment_indices]
        ratio = np.clip(ratio, 0.0, 1.0)
        projected_x = start_x + ratio * dx
        projected_y = start_y + ratio * dy
        distance = np.hypot(x - projected_x, y - projected_y)
        progress = (
            self.cumulative_distance[segment_indices]
            + ratio * self.segment_length[segment_indices]
        )
        return distance, progress, dx, dy


class RouteProgressMatcher:
    """FIT位置を時系列順にGPXへ対応付け、ルート進捗を計算する。"""

    def __init__(
        self,
        route: GpxRoute,
        *,
        off_route_threshold_m: float = 150.0,
        search_ahead_m: float = 5000.0,
        search_behind_m: float = 300.0,
    ) -> None:
        self.route = route
        self.off_route_threshold_m = off_route_threshold_m
        self.search_ahead_m = search_ahead_m
        self.search_behind_m = search_behind_m

    def match(self, data: pd.DataFrame) -> pd.Series:
        positions = data[["position_long", "position_lat"]]
        progress_values = np.full(len(positions), np.nan)
        previous_progress: float | None = None
        previous_xy: tuple[float, float] | None = None

        for row_index, row in enumerate(positions.itertuples(index=False)):
            lon = float(row.position_long)
            lat = float(row.position_lat)
            if not np.isfinite(lon) or not np.isfinite(lat):
                progress_values[row_index] = (
                    np.nan if previous_progress is None else previous_progress
                )
                continue

            x, y = self.route.to_xy(lon, lat)
            candidates = self.route.candidate_segments(
                x,
                y,
                search_radius_m=max(
                    self.off_route_threshold_m,
                    self.search_behind_m,
                ),
            )
            distance, progress, segment_dx, segment_dy = self.route.project(
                x,
                y,
                candidates,
            )
            score = distance.copy()

            if previous_progress is not None:
                delta = progress - previous_progress
                score += np.abs(delta) * 0.02
                score += np.where(
                    delta < -self.search_behind_m,
                    1_000_000.0 + np.abs(delta) * 10.0,
                    0.0,
                )
                score += np.where(
                    delta > self.search_ahead_m,
                    1_000_000.0 + delta * 10.0,
                    0.0,
                )
                score += np.where(delta < 0, np.abs(delta) * 0.5, 0.0)

            if previous_xy is not None:
                movement_x = x - previous_xy[0]
                movement_y = y - previous_xy[1]
                movement_length = np.hypot(movement_x, movement_y)
                segment_length = np.hypot(segment_dx, segment_dy)
                if movement_length >= 1.0:
                    cosine = (
                        movement_x * segment_dx + movement_y * segment_dy
                    ) / np.maximum(movement_length * segment_length, 1e-9)
                    score += (1.0 - np.clip(cosine, -1.0, 1.0)) * 100.0

            best = int(np.argmin(score))
            if distance[best] <= self.off_route_threshold_m:
                previous_progress = float(progress[best])
            progress_values[row_index] = (
                np.nan if previous_progress is None else previous_progress
            )
            previous_xy = (x, y)

        return pd.Series(
            progress_values,
            index=data.index,
            name="route_progress_m",
        ).ffill()
