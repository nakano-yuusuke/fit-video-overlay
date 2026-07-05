"""OSM行政境界から現在地名列を追加する。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import PlaceNamesFeatureConfig
from .gpx_route import GpxRoute


def add_place_names(
    data: pd.DataFrame,
    config: PlaceNamesFeatureConfig,
) -> pd.DataFrame:
    """FIT位置をOSM行政境界へ対応付け、地名列を追加する。"""
    if not config.enabled:
        return data
    _require_geometry_dependencies()
    if config.pbf_path is None:
        raise ValueError("place_names.source=osm_pbfにはpbf_pathが必要です。")

    bbox = _route_bbox(data, config)
    cached = _load_or_extract_boundaries(bbox, config)
    boundaries = _build_boundary_index(cached)

    result = data.copy()
    result[config.column] = _names_for_positions(
        result,
        boundaries,
        config.admin_levels,
    )
    return result


def _require_geometry_dependencies() -> None:
    try:
        import osmium  # noqa: F401
        import shapely  # noqa: F401
    except ImportError as error:
        raise ImportError(
            "features.place_names には osmium と shapely が必要です。"
            " 例: python3 -m pip install osmium shapely"
        ) from error


def _route_bbox(
    data: pd.DataFrame,
    config: PlaceNamesFeatureConfig,
) -> list[float]:
    route = _route_from_config(data, config)
    lon_margin = config.bbox_margin_m / route.lon_m_per_deg
    lat_margin = config.bbox_margin_m / route.lat_m_per_deg
    return [
        float(np.min(route.longitudes) - lon_margin),
        float(np.min(route.latitudes) - lat_margin),
        float(np.max(route.longitudes) + lon_margin),
        float(np.max(route.latitudes) + lat_margin),
    ]


def _route_from_config(
    data: pd.DataFrame,
    config: PlaceNamesFeatureConfig,
) -> GpxRoute:
    if config.route_source == "gpx":
        assert config.gpx_path is not None
        return GpxRoute(config.gpx_path)
    if "position_lat" not in data.columns or "position_long" not in data.columns:
        raise ValueError("place_names.route_source=fitにはposition_lat/position_long列が必要です。")
    route_data = data[["position_lat", "position_long"]].dropna()
    if len(route_data) < 2:
        raise ValueError("FIT実走ルートの位置情報が不足しています。")
    return GpxRoute.from_points(
        route_data["position_lat"].to_numpy(dtype=float),
        route_data["position_long"].to_numpy(dtype=float),
    )


def _load_or_extract_boundaries(
    bbox: list[float],
    config: PlaceNamesFeatureConfig,
) -> list[dict[str, Any]]:
    cache_path = _route_cache_path(bbox, config)
    if cache_path.exists():
        return _load_boundaries_cache(cache_path)

    index_cache_path = _index_cache_path(config)
    if index_cache_path.exists():
        boundaries = _filter_boundaries_by_bbox(
            _load_boundaries_cache(index_cache_path),
            bbox,
        )
        _write_boundaries_cache(
            cache_path,
            config,
            boundaries,
            cache_type="route",
            bbox=bbox,
        )
        return boundaries

    boundaries = _extract_boundaries_from_pbf(bbox, config)
    _write_boundaries_cache(
        cache_path,
        config,
        boundaries,
        cache_type="route",
        bbox=bbox,
    )
    return boundaries


def build_boundary_index_cache(
    config: PlaceNamesFeatureConfig,
    *,
    force: bool = False,
) -> tuple[Path, int]:
    """PBFから行政境界を抽出し、広域キャッシュとして保存する。"""
    _require_geometry_dependencies()
    if config.pbf_path is None:
        raise ValueError("place_names.source=osm_pbfにはpbf_pathが必要です。")

    cache_path = _index_cache_path(config)
    if cache_path.exists() and not force:
        return cache_path, len(_load_boundaries_cache(cache_path))

    boundaries = _extract_boundaries_from_pbf(None, config)
    _write_boundaries_cache(
        cache_path,
        config,
        boundaries,
        cache_type="index",
        bbox=None,
    )
    return cache_path, len(boundaries)


def _load_boundaries_cache(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as file:
        cached = json.load(file)
    return list(cached.get("boundaries", []))


def _write_boundaries_cache(
    path: Path,
    config: PlaceNamesFeatureConfig,
    boundaries: list[dict[str, Any]],
    *,
    cache_type: str,
    bbox: list[float] | None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "source": "osm_pbf",
                "cache_type": cache_type,
                "pbf_path": str(config.pbf_path),
                "bbox": bbox,
                "admin_levels": list(config.admin_levels),
                "name_tags": list(config.name_tags),
                "boundaries": boundaries,
            },
            file,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    tmp_path.replace(path)


def _route_cache_path(
    bbox: list[float],
    config: PlaceNamesFeatureConfig,
) -> Path:
    assert config.pbf_path is not None
    stat = config.pbf_path.stat()
    key = {
        "bbox": [round(value, 5) for value in bbox],
        "pbf_path": str(config.pbf_path),
        "pbf_size": stat.st_size,
        "pbf_mtime_ns": stat.st_mtime_ns,
        "admin_levels": list(config.admin_levels),
        "name_tags": list(config.name_tags),
    }
    digest = hashlib.sha1(
        json.dumps(key, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return config.cache_dir / f"place_names_{digest}.json"


def _index_cache_path(config: PlaceNamesFeatureConfig) -> Path:
    assert config.pbf_path is not None
    stat = config.pbf_path.stat()
    key = {
        "pbf_path": str(config.pbf_path),
        "pbf_size": stat.st_size,
        "pbf_mtime_ns": stat.st_mtime_ns,
        "admin_levels": list(config.admin_levels),
        "name_tags": list(config.name_tags),
    }
    digest = hashlib.sha1(
        json.dumps(key, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return config.cache_dir / f"place_names_index_{digest}.json"


def _filter_boundaries_by_bbox(
    boundaries: list[dict[str, Any]],
    bbox: list[float],
) -> list[dict[str, Any]]:
    return [
        boundary
        for boundary in boundaries
        if _bbox_intersects(list(boundary["bbox"]), bbox)
    ]


def _extract_boundaries_from_pbf(
    bbox: list[float] | None,
    config: PlaceNamesFeatureConfig,
) -> list[dict[str, Any]]:
    import osmium
    from shapely import wkb

    class BoundaryHandler(osmium.SimpleHandler):
        def __init__(self) -> None:
            super().__init__()
            self.wkb_factory = osmium.geom.WKBFactory()
            self.boundaries: list[dict[str, Any]] = []

        def area(self, area) -> None:
            tags = dict(area.tags)
            if tags.get("boundary") != "administrative":
                return
            admin_level = tags.get("admin_level")
            try:
                admin_level_int = int(admin_level) if admin_level is not None else -1
            except ValueError:
                return
            if admin_level_int not in config.admin_levels:
                return
            name = _name_from_tags(tags, config.name_tags)
            if name is None:
                return

            try:
                geometry = wkb.loads(
                    self.wkb_factory.create_multipolygon(area),
                    hex=True,
                )
            except RuntimeError:
                return
            if not geometry.is_valid:
                geometry = geometry.buffer(0)
            if geometry.is_empty:
                return
            if bbox is not None and not _bbox_intersects(list(geometry.bounds), bbox):
                return

            self.boundaries.append(
                {
                    "name": name,
                    "admin_level": admin_level_int,
                    "bbox": [float(value) for value in geometry.bounds],
                    "multipolygon": _geometry_to_coordinates(geometry),
                }
            )

    handler = BoundaryHandler()
    assert config.pbf_path is not None
    handler.apply_file(str(config.pbf_path), locations=True)
    return handler.boundaries


def _name_from_tags(
    tags: dict[str, str],
    name_tags: tuple[str, ...],
) -> str | None:
    for tag in name_tags:
        value = tags.get(tag)
        if value:
            return value
    return None


def _bbox_intersects(
    left: list[float],
    right: list[float],
) -> bool:
    left_west, left_south, left_east, left_north = left
    right_west, right_south, right_east, right_north = right
    return not (
        left_east < right_west
        or right_east < left_west
        or left_north < right_south
        or right_north < left_south
    )


def _geometry_to_coordinates(geometry) -> list[list[dict[str, list[list[float]]]]]:
    polygons = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
    result: list[list[dict[str, list[list[float]]]]] = []
    for polygon in polygons:
        rings = [{"exterior": _coords_to_lists(polygon.exterior.coords)}]
        for interior in polygon.interiors:
            rings.append({"interior": _coords_to_lists(interior.coords)})
        result.append(rings)
    return result


def _coords_to_lists(coordinates) -> list[list[float]]:
    return [[float(lon), float(lat)] for lon, lat in coordinates]


def _build_boundary_index(
    cached_boundaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    from shapely.geometry import MultiPolygon, Polygon
    from shapely.prepared import prep

    boundaries: list[dict[str, Any]] = []
    for boundary in cached_boundaries:
        polygons = []
        for polygon_data in boundary["multipolygon"]:
            exterior = None
            interiors = []
            for ring in polygon_data:
                if "exterior" in ring:
                    exterior = ring["exterior"]
                elif "interior" in ring:
                    interiors.append(ring["interior"])
            if exterior is None:
                continue
            polygons.append(Polygon(exterior, interiors))
        if not polygons:
            continue
        geometry = polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
        boundaries.append(
            {
                "name": boundary["name"],
                "admin_level": int(boundary["admin_level"]),
                "bbox": boundary["bbox"],
                "area": float(geometry.area),
                "geometry": prep(geometry),
            }
        )
    return boundaries


def _names_for_positions(
    data: pd.DataFrame,
    boundaries: list[dict[str, Any]],
    admin_levels: tuple[int, ...],
) -> list[str]:
    from shapely.geometry import Point

    names: list[str] = []
    if "position_lat" not in data.columns or "position_long" not in data.columns:
        raise ValueError("place_namesにはposition_lat/position_long列が必要です。")

    for _, row in data[["position_long", "position_lat"]].iterrows():
        if row.isna().any():
            names.append("")
            continue
        lon = float(row["position_long"])
        lat = float(row["position_lat"])
        point = Point(lon, lat)
        matches_by_level: dict[int, dict[str, Any]] = {}
        for boundary in boundaries:
            if not _point_in_bbox(lon, lat, boundary["bbox"]):
                continue
            if boundary["geometry"].covers(point):
                level = int(boundary["admin_level"])
                current = matches_by_level.get(level)
                if current is None or float(boundary["area"]) < float(current["area"]):
                    matches_by_level[level] = boundary
        names.append(_format_place_name(matches_by_level, admin_levels))
    return names


def _format_place_name(
    matches_by_level: dict[int, dict[str, Any]],
    admin_levels: tuple[int, ...],
) -> str:
    parts: list[str] = []
    for level in admin_levels:
        boundary = matches_by_level.get(level)
        if boundary is None:
            continue
        name = str(boundary["name"])
        if name and name not in parts:
            parts.append(name)
    return "".join(parts)


def _point_in_bbox(
    lon: float,
    lat: float,
    bbox: list[float],
) -> bool:
    west, south, east, north = bbox
    return west <= lon <= east and south <= lat <= north
