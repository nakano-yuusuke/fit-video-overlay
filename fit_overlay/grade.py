"""距離と高度から斜度列を追加する。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import GradeFeatureConfig, GradeSeriesConfig


def add_grade(
    data: pd.DataFrame,
    config: GradeFeatureConfig,
) -> pd.DataFrame:
    """FIT実走斜度とGPXルート斜度の列を追加する。"""
    if not config.enabled:
        return data

    result = data.copy()
    if config.ride.enabled:
        result[config.ride.column] = calculate_grade_percent(result, config.ride)
    if config.route.enabled:
        result[config.route.column] = calculate_grade_percent(result, config.route)
    return result


def calculate_grade_percent(
    data: pd.DataFrame,
    config: GradeSeriesConfig,
) -> pd.Series:
    """指定した距離窓の高度差から斜度%を計算する。"""
    _require_column(data, config.distance_column)
    _require_column(data, config.altitude_column)

    distance = data[config.distance_column].to_numpy(dtype=float)
    altitude = data[config.altitude_column].to_numpy(dtype=float)
    clean_distance, clean_altitude = _prepare_profile(distance, altitude)

    result = np.full(len(data), np.nan, dtype=float)
    if len(clean_distance) < 2:
        return pd.Series(result, index=data.index)

    half_window = config.window_m / 2.0
    before = distance - half_window
    after = distance + half_window
    valid = (
        np.isfinite(distance)
        & (before >= clean_distance[0])
        & (after <= clean_distance[-1])
    )
    if not valid.any():
        return pd.Series(result, index=data.index)

    before_altitude = np.interp(before[valid], clean_distance, clean_altitude)
    after_altitude = np.interp(after[valid], clean_distance, clean_altitude)
    result[valid] = (after_altitude - before_altitude) / config.window_m * 100.0
    return pd.Series(result, index=data.index)


def _require_column(data: pd.DataFrame, column: str) -> None:
    if column not in data.columns:
        raise ValueError(f"斜度計算に必要な列がありません: {column}")


def _prepare_profile(
    distance: np.ndarray,
    altitude: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    valid = np.isfinite(distance) & np.isfinite(altitude)
    if not valid.any():
        return np.asarray([], dtype=float), np.asarray([], dtype=float)

    sorted_index = np.argsort(distance[valid], kind="mergesort")
    sorted_distance = distance[valid][sorted_index]
    sorted_altitude = altitude[valid][sorted_index]
    unique_distance, inverse = np.unique(sorted_distance, return_inverse=True)
    altitude_sum = np.bincount(inverse, weights=sorted_altitude)
    altitude_count = np.bincount(inverse)
    return unique_distance, altitude_sum / altitude_count
