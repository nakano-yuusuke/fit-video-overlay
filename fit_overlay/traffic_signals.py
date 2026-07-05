"""OSM信号機データをルート距離へ集計する。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from .config import TrafficSignalsFeatureConfig
from .gpx_route import GpxRoute, RouteProgressMatcher


def add_traffic_signal_counts(
    data: pd.DataFrame,
    config: TrafficSignalsFeatureConfig,
) -> pd.DataFrame:
    """FITデータへ1km区間ごとの信号数列を追加する。"""
    if not config.enabled:
        return data

    route = _route_from_config(data, config)
    signals = _load_or_fetch_signals(route, config)
    signal_progress = _match_signals_to_route(route, signals, config)
    bucket_counts = _count_by_bucket(signal_progress, config.bucket_distance_m)
    progress = _fit_progress_on_route(data, route, config)

    result = data.copy()
    if "route_progress_m" not in result.columns:
        result["route_progress_m"] = progress
    bucket_indices = np.floor(progress / config.bucket_distance_m).astype("Int64")
    counts = bucket_indices.map(lambda index: bucket_counts.get(int(index), 0))
    result[config.column] = counts.astype(float).ffill().fillna(0.0)
    return result


def _route_from_config(
    data: pd.DataFrame,
    config: TrafficSignalsFeatureConfig,
) -> GpxRoute:
    if config.route_source == "gpx":
        assert config.gpx_path is not None
        return GpxRoute(config.gpx_path)
    return _fit_route(data)


def _fit_route(data: pd.DataFrame) -> GpxRoute:
    if "position_lat" not in data.columns or "position_long" not in data.columns:
        raise ValueError("route_source=fitにはposition_lat/position_long列が必要です。")
    route_data = data[["position_lat", "position_long"]].dropna()
    if len(route_data) < 2:
        raise ValueError("FIT実走ルートの位置情報が不足しています。")
    latitudes = route_data["position_lat"].to_numpy(dtype=float)
    longitudes = route_data["position_long"].to_numpy(dtype=float)
    return GpxRoute.from_points(latitudes, longitudes)


def _load_or_fetch_signals(
    route: GpxRoute,
    config: TrafficSignalsFeatureConfig,
) -> list[tuple[float, float]]:
    bbox = _route_bbox(route, config.bbox_margin_m)
    cache_path = _cache_path(bbox, config)
    if cache_path.exists():
        with cache_path.open(encoding="utf-8") as file:
            cached = json.load(file)
        return [
            (float(item["lon"]), float(item["lat"]))
            for item in cached.get("signals", [])
        ]

    signals = _fetch_signals(bbox, config.overpass_url)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "source": "overpass",
                "bbox": bbox,
                "query": "node[highway=traffic_signals]",
                "signals": [
                    {"lon": lon, "lat": lat}
                    for lon, lat in signals
                ],
            },
            file,
            ensure_ascii=False,
            indent=2,
        )
    return signals


def _route_bbox(route: GpxRoute, margin_m: float) -> list[float]:
    lon_margin = margin_m / route.lon_m_per_deg
    lat_margin = margin_m / route.lat_m_per_deg
    return [
        float(np.min(route.longitudes) - lon_margin),
        float(np.min(route.latitudes) - lat_margin),
        float(np.max(route.longitudes) + lon_margin),
        float(np.max(route.latitudes) + lat_margin),
    ]


def _cache_path(
    bbox: list[float],
    config: TrafficSignalsFeatureConfig,
) -> Path:
    key = {
        "bbox": [round(value, 6) for value in bbox],
        "bucket_distance_m": config.bucket_distance_m,
        "signal_match_threshold_m": config.signal_match_threshold_m,
        "route_source": config.route_source,
        "gpx_path": str(config.gpx_path) if config.gpx_path is not None else None,
    }
    digest = hashlib.sha1(
        json.dumps(key, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return config.cache_dir / f"traffic_signals_{digest}.json"


def _fetch_signals(
    bbox: list[float],
    overpass_url: str,
) -> list[tuple[float, float]]:
    west, south, east, north = bbox
    query = f"""
    [out:json][timeout:60];
    node["highway"="traffic_signals"]({south},{west},{north},{east});
    out body;
    """
    data = urlencode({"data": query}).encode("utf-8")
    request = Request(
        overpass_url,
        data=data,
        headers={"User-Agent": "fit2mp4"},
        method="POST",
    )
    with urlopen(request, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return [
        (float(element["lon"]), float(element["lat"]))
        for element in payload.get("elements", [])
        if "lon" in element and "lat" in element
    ]


def _match_signals_to_route(
    route: GpxRoute,
    signals: list[tuple[float, float]],
    config: TrafficSignalsFeatureConfig,
) -> list[float]:
    progress_values: list[float] = []
    for lon, lat in signals:
        x, y = route.to_xy(lon, lat)
        candidates = route.candidate_segments(
            x,
            y,
            search_radius_m=config.signal_match_threshold_m,
        )
        distance, progress, _, _ = route.project(x, y, candidates)
        best = int(np.argmin(distance))
        if float(distance[best]) <= config.signal_match_threshold_m:
            progress_values.append(float(progress[best]))
    return progress_values


def _count_by_bucket(
    progress_values: list[float],
    bucket_distance_m: float,
) -> dict[int, int]:
    counts: dict[int, int] = {}
    for progress in progress_values:
        bucket = int(progress // bucket_distance_m)
        counts[bucket] = counts.get(bucket, 0) + 1
    return counts


def _fit_progress_on_route(
    data: pd.DataFrame,
    route: GpxRoute,
    config: TrafficSignalsFeatureConfig,
) -> pd.Series:
    if "route_progress_m" in data.columns:
        return data["route_progress_m"].ffill().fillna(0.0)
    matcher = RouteProgressMatcher(
        route,
        off_route_threshold_m=config.route_match_threshold_m,
    )
    return matcher.match(data).ffill().fillna(0.0)
