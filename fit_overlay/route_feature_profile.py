"""GPXルート距離を軸にした静的な特徴量プロファイル。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RouteFeatureProfile:
    """ルート全区間の特徴量を距離インデックスで保持する。"""

    data: pd.DataFrame
    progress_column: str = "route_progress_m"

    @classmethod
    def empty(
        cls,
        progress_column: str = "route_progress_m",
    ) -> "RouteFeatureProfile":
        index = pd.Index([], dtype=float, name="route_distance_m")
        return cls(pd.DataFrame(index=index), progress_column)

    @property
    def total_distance_m(self) -> float:
        if self.data.empty:
            return 0.0
        return float(self.data.index[-1])

    def has_column(self, column: str) -> bool:
        return column in self.data.columns

    def merge(self, other: "RouteFeatureProfile") -> "RouteFeatureProfile":
        """異なる種類・距離刻みのルート特徴量を1つにまとめる。"""
        if self.data.empty:
            return other
        if other.data.empty:
            return self
        if self.progress_column != other.progress_column:
            raise ValueError(
                "ルート特徴量の進捗列が一致しません: "
                f"{self.progress_column}, {other.progress_column}"
            )
        duplicates = set(self.data.columns).intersection(other.data.columns)
        if duplicates:
            raise ValueError(
                f"ルート特徴量の列が重複しています: {sorted(duplicates)}"
            )
        distances = self.data.index.union(other.data.index).sort_values()
        left = self.data.reindex(distances).ffill().bfill()
        right = other.data.reindex(distances).ffill().bfill()
        combined = pd.concat([left, right], axis=1)
        combined.index = combined.index.rename("route_distance_m")
        return RouteFeatureProfile(combined, self.progress_column)

    def series(self, column: str) -> pd.Series:
        if not self.has_column(column):
            raise KeyError(column)
        return self.data[column]

    def map_progress(self, progress: pd.Series, column: str) -> pd.Series:
        """各GPX進捗距離に対応する直前バケットの値を返す。"""
        if not self.has_column(column) or self.data.empty:
            return pd.Series(np.nan, index=progress.index, dtype=float)

        distances = self.data.index.to_numpy(dtype=float)
        values = self.data[column].to_numpy()
        raw_progress = pd.to_numeric(progress, errors="coerce").to_numpy(dtype=float)
        result = np.full(len(raw_progress), np.nan, dtype=float)
        valid = np.isfinite(raw_progress)
        if np.any(valid):
            clipped = np.clip(raw_progress[valid], distances[0], distances[-1])
            positions = np.searchsorted(distances, clipped, side="right") - 1
            result[valid] = values[positions].astype(float)
        return pd.Series(result, index=progress.index, name=column)

    def attach_columns(
        self,
        fit_data: pd.DataFrame,
        columns: tuple[str, ...] | list[str],
    ) -> pd.DataFrame:
        """表示・出力時だけ、FIT行へ要求されたルート特徴量を対応付ける。"""
        requested = tuple(
            column
            for column in dict.fromkeys(columns)
            if self.has_column(column)
        )
        if not requested:
            return fit_data
        if self.progress_column not in fit_data.columns:
            return fit_data
        resolved = fit_data.copy()
        progress = resolved[self.progress_column]
        for column in requested:
            resolved[column] = self.map_progress(progress, column)
        return resolved
