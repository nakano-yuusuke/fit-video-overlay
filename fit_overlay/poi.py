"""グラフや地図で共用するPOIデータの読み込み。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import PointsOfInterestConfig
from .gpx_route import GpxRoute


@dataclass(frozen=True)
class PointOfInterest:
    id: str
    label: str
    emoji: str = ""
    icon_path: Path | None = None
    icon_size: tuple[int, int] | None = None
    name: str | None = None
    waypoint_type: str | None = None
    source: str = "manual"
    distance_m: float | None = None
    lat: float | None = None
    lon: float | None = None

    @property
    def display_text(self) -> str:
        return self.label


def load_points_of_interest(
    config: PointsOfInterestConfig,
    *,
    default_gpx_path: Path | None = None,
) -> tuple[PointOfInterest, ...]:
    """設定とGPX WPTから、表示用POI一覧を作る。"""
    if not config.enabled:
        return ()

    route_cache: dict[Path, GpxRoute] = {}

    def route_for(path: Path | None) -> GpxRoute | None:
        if path is None:
            return None
        if path not in route_cache:
            route_cache[path] = GpxRoute(path)
        return route_cache[path]

    points: list[PointOfInterest] = []
    fallback_route_path = config.gpx_path or default_gpx_path

    for source_index, source in enumerate(config.sources, start=1):
        route = route_for(source.gpx_path)
        assert route is not None
        waypoints = GpxRoute.load_waypoints(source.gpx_path)
        for index, waypoint in enumerate(waypoints, start=1):
            progress_m, _ = route.progress_for_position(
                waypoint.lon,
                waypoint.lat,
            )
            label = waypoint.name or f"WPT{index}"
            points.append(
                PointOfInterest(
                    id=f"gpx_wpt_{source_index}_{index}",
                    label=label,
                    emoji=source.emoji,
                    icon_path=source.icon,
                    icon_size=source.icon_size,
                    name=waypoint.name or None,
                    waypoint_type=waypoint.type,
                    source="gpx_wpt",
                    distance_m=progress_m,
                    lat=waypoint.lat,
                    lon=waypoint.lon,
                )
            )

    fallback_route = route_for(fallback_route_path)
    for item in config.items:
        distance_m = item.distance_m
        lat = item.lat
        lon = item.lon
        if (
            distance_m is None
            and lat is not None
            and lon is not None
            and fallback_route is not None
        ):
            distance_m, _ = fallback_route.progress_for_position(lon, lat)
        if (
            lat is None
            and lon is None
            and distance_m is not None
            and fallback_route is not None
        ):
            lon, lat = fallback_route.position_at(distance_m)
        label = item.label or item.name or item.id
        points.append(
            PointOfInterest(
                id=item.id,
                label=label,
                emoji=item.emoji,
                icon_path=item.icon,
                icon_size=item.icon_size,
                name=item.name,
                waypoint_type=None,
                source="manual",
                distance_m=distance_m,
                lat=lat,
                lon=lon,
            )
        )

    return tuple(points)
