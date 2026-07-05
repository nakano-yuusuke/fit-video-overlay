"""GPXルート由来のDataFrame列を追加する。"""

from __future__ import annotations

import pandas as pd

from .config import RouteProgressFeatureConfig
from .gpx_route import GpxRoute, RouteProgressMatcher


def add_route_progress(
    data: pd.DataFrame,
    config: RouteProgressFeatureConfig,
) -> pd.DataFrame:
    """FIT位置をGPXへ投影し、ルート進捗とGPX高度を追加する。"""
    if not config.enabled:
        return data
    if config.gpx_path is None:
        raise ValueError("features.route_progressにはgpx_pathが必要です。")

    route = GpxRoute(config.gpx_path)
    matcher = RouteProgressMatcher(
        route,
        off_route_threshold_m=config.off_route_threshold_m,
        search_ahead_m=config.search_ahead_m,
        search_behind_m=config.search_behind_m,
    )

    result = data.copy()
    progress = matcher.match(result)
    result[config.progress_column] = progress

    if config.add_route_altitude:
        if route.elevations is None:
            raise ValueError(
                "GPXに高度<ele>がないためroute_altitude_mを作成できません。"
            )
        result[config.altitude_column] = route.altitudes_at(
            progress.to_numpy(dtype=float)
        )

    return result
