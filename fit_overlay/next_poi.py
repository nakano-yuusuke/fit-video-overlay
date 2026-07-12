"""次に到達するPOI名と距離をDataFrameへ追加する。"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .config import NextPoiFeatureConfig
from .poi import PointOfInterest


def add_next_poi(
    data: pd.DataFrame,
    config: NextPoiFeatureConfig,
    points_of_interest: tuple[PointOfInterest, ...],
) -> pd.DataFrame:
    """現在のルート進捗から次の対象POIを求める。"""
    if not config.enabled:
        return data
    if config.progress_column not in data.columns:
        raise ValueError(
            "features.next_poi.progress_column がDataFrameにありません: "
            f"{config.progress_column}"
        )

    result = data.copy()
    targets = _target_points(points_of_interest, config)
    if not targets:
        result[config.name_column] = ""
        result[config.distance_column] = np.nan
        return result

    distances = np.asarray([poi.distance_m for poi in targets], dtype=float)
    labels = np.asarray([poi.display_text for poi in targets], dtype=object)
    progress = result[config.progress_column].to_numpy(dtype=float, copy=False)
    lookup_progress = progress - config.include_current_distance_m
    target_indices = np.searchsorted(distances, lookup_progress, side="left")
    has_next = (
        np.isfinite(progress)
        & (target_indices >= 0)
        & (target_indices < len(distances))
    )

    names = np.full(len(result), "", dtype=object)
    remaining = np.full(len(result), np.nan, dtype=float)
    if has_next.any():
        valid_indices = target_indices[has_next]
        names[has_next] = labels[valid_indices]
        remaining[has_next] = np.maximum(
            0.0,
            distances[valid_indices] - progress[has_next],
        )

    result[config.name_column] = names
    result[config.distance_column] = remaining
    return result


def _target_points(
    points_of_interest: tuple[PointOfInterest, ...],
    config: NextPoiFeatureConfig,
) -> list[PointOfInterest]:
    patterns = tuple(re.compile(pattern) for pattern in config.name_patterns)
    points = [
        poi
        for poi in points_of_interest
        if poi.distance_m is not None
        and _matches_sources(poi, config.sources)
        and _matches_waypoint_types(poi, config.waypoint_types)
        and _matches_name_patterns(poi, patterns)
    ]
    return sorted(points, key=lambda poi: float(poi.distance_m))


def _matches_sources(
    poi: PointOfInterest,
    sources: tuple[str, ...],
) -> bool:
    return not sources or poi.source in sources


def _matches_waypoint_types(
    poi: PointOfInterest,
    waypoint_types: tuple[str, ...],
) -> bool:
    return not waypoint_types or poi.waypoint_type in waypoint_types


def _matches_name_patterns(
    poi: PointOfInterest,
    patterns: tuple[re.Pattern[str], ...],
) -> bool:
    if not patterns:
        return True
    names = (poi.label, poi.name or "")
    return any(pattern.search(name) for pattern in patterns for name in names)
