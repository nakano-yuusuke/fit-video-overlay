"""FITデータの読み込みと動画表示向け前処理。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from fit2csv import fit2df
from .time_utils import to_utc_datetime_index


COLUMN_ALIASES = {
    "speed": ("enhanced_speed",),
    "altitude": ("enhanced_altitude",),
}


def load_fit_data(
    fit_path: Path,
    *,
    time_offset: pd.Timedelta = pd.Timedelta(0),
    max_duration: pd.Timedelta | None = pd.Timedelta(minutes=60),
) -> pd.DataFrame:
    """FITを時系列DataFrameとして読み込み、比較用の時刻をUTCへ統一する。"""
    data = fit2df(str(fit_path)).copy()
    if data.empty:
        raise ValueError(f"FITファイルにrecordデータがありません: {fit_path}")
    if "timestamp" not in data.columns:
        raise ValueError("FITデータにtimestamp列がありません。")

    # FIT機器によって列名が異なるため、表示側で使う標準列名へ揃える。
    for standard_name, aliases in COLUMN_ALIASES.items():
        if standard_name in data.columns:
            continue
        source_name = next(
            (alias for alias in aliases if alias in data.columns),
            None,
        )
        if source_name is not None:
            data[standard_name] = data[source_name]

    # 動画のcreation_timeもUTCで扱うため、FIT側もUTCへ統一しておく。
    data["timestamp"] = to_utc_datetime_index(data["timestamp"])
    data["timestamp"] = data["timestamp"] + time_offset
    data = data.sort_values("timestamp")

    # 現状は長時間のFITをすべて展開しないよう、先頭60分に制限している。
    if max_duration is not None:
        end_time = data["timestamp"].iloc[0] + max_duration
        data = data[data["timestamp"] < end_time]

    # 以降の時刻検索と補完を簡単にするため、timestampをindexとして使う。
    return data.set_index("timestamp")


def prepare_overlay_data(data: pd.DataFrame) -> pd.DataFrame:
    """元FITの記録時刻を維持したまま、数値列の欠損だけを補完する。"""
    # 文字列などは表示値の検索・補完に使わないため、数値列だけを対象にする。
    numeric_data = data.select_dtypes(include=[np.number]).sort_index()

    # FITの行数や記録時刻は変更しない。各カラムのNaNだけを直前値で埋める。
    # 記録自体がない時間帯は、各FrameMakerがsearchsorted()で直前行を参照する。
    return numeric_data.ffill()
