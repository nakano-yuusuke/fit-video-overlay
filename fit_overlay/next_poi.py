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
    if config.never_revisit_passed:
        names, remaining = _next_poi_monotonic(
            progress,
            distances,
            labels,
            include_current_distance_m=config.include_current_distance_m,
        )
    else:
        names, remaining = _next_poi_independent(
            progress,
            distances,
            labels,
            include_current_distance_m=config.include_current_distance_m,
        )

    result[config.name_column] = names
    result[config.distance_column] = remaining
    return result


def _next_poi_independent(
    progress: np.ndarray,
    distances: np.ndarray,
    labels: np.ndarray,
    *,
    include_current_distance_m: float,
) -> tuple[np.ndarray, np.ndarray]:
    lookup_progress = progress - include_current_distance_m
    target_indices = np.searchsorted(distances, lookup_progress, side="left")
    return _labels_and_remaining(progress, distances, labels, target_indices)


def _next_poi_monotonic(
    progress: np.ndarray,
    distances: np.ndarray,
    labels: np.ndarray,
    *,
    include_current_distance_m: float,
) -> tuple[np.ndarray, np.ndarray]:
    target_indices = np.full(len(progress), len(distances), dtype=int)
    target_index = 0
    for row_index, current_progress in enumerate(progress):
        if not np.isfinite(current_progress):
            continue
        while (
            target_index < len(distances)
            and current_progress - include_current_distance_m > distances[target_index]
        ):
            target_index += 1
        target_indices[row_index] = target_index
    return _labels_and_remaining(progress, distances, labels, target_indices)


def _labels_and_remaining(
    progress: np.ndarray,
    distances: np.ndarray,
    labels: np.ndarray,
    target_indices: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    has_next = (
        np.isfinite(progress)
        & (target_indices >= 0)
        & (target_indices < len(distances))
    )

    names = np.full(len(progress), "", dtype=object)
    remaining = np.full(len(progress), np.nan, dtype=float)
    if has_next.any():
        valid_indices = target_indices[has_next]
        names[has_next] = labels[valid_indices]
        remaining[has_next] = np.maximum(
            0.0,
            distances[valid_indices] - progress[has_next],
        )
    return names, remaining


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
