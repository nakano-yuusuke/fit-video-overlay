"""GPXルート進捗から制限時刻までの貯金秒数列を追加する。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import RouteMarginFeatureConfig
from .gpx_route import GpxRoute, RouteProgressMatcher


def add_route_margin(
    data: pd.DataFrame,
    config: RouteMarginFeatureConfig,
) -> pd.DataFrame:
    """FITデータへ制限時刻に対する貯金秒数列を追加する。"""
    if not config.enabled:
        return data
    if config.gpx_path is None:
        raise ValueError("features.route_marginにはgpx_pathが必要です。")
    if data.empty:
        return data

    route = GpxRoute(config.gpx_path)
    progress = _route_progress(data, route, config)
    target_speed_mps = config.target_speed_kmh / 3.6
    remaining_seconds = (
        np.maximum(0.0, route.total_distance_m - progress.to_numpy(dtype=float))
        / target_speed_mps
    )
    estimated_arrival = data.index + pd.to_timedelta(remaining_seconds, unit="s")
    deadline = _resolve_deadline(data.index[0], config.deadline_time, config.timezone)
    margin_seconds = pd.Series(
        (deadline - estimated_arrival).total_seconds(),
        index=data.index,
    )
    margin_seconds[pd.isna(progress)] = np.nan

    result = data.copy()
    if config.progress_column not in result.columns:
        result[config.progress_column] = progress
    result[config.column] = margin_seconds
    return result


def format_margin_seconds(margin_seconds: float) -> str:
    """秒数を+HH:MM/-HH:MMの貯金表示へ変換する。"""
    total_minutes = int(round(abs(margin_seconds) / 60))
    hours, minutes = divmod(total_minutes, 60)
    sign = "+" if margin_seconds >= 0 else "-"
    return f"{sign}{hours:02d}:{minutes:02d}"


def _route_progress(
    data: pd.DataFrame,
    route: GpxRoute,
    config: RouteMarginFeatureConfig,
) -> pd.Series:
    if config.progress_column in data.columns:
        return data[config.progress_column].ffill()
    matcher = RouteProgressMatcher(
        route,
        off_route_threshold_m=config.off_route_threshold_m,
        search_ahead_m=config.search_ahead_m,
        search_behind_m=config.search_behind_m,
    )
    return matcher.match(data)


def _resolve_deadline(
    first_time: pd.Timestamp,
    deadline_time: str,
    timezone: str,
) -> pd.Timestamp:
    if " " in deadline_time:
        # YYYY-MM-DD HH:MM 形式: 日付込みで直接解釈
        return pd.Timestamp(deadline_time, tz=timezone).tz_convert("UTC")
    # 後方互換: HH:MM 形式 — 開始日を基準に翌日繰り上げ
    first_local = first_time.tz_convert(timezone)
    deadline_local = pd.Timestamp(
        f"{first_local.date()} {deadline_time}",
        tz=timezone,
    )
    if deadline_local <= first_local:
        deadline_local += pd.Timedelta(days=1)
    return deadline_local.tz_convert("UTC")
