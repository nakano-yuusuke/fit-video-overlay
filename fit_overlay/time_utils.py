"""アプリケーション内で使う時刻表現をUTCへ統一する。"""

from __future__ import annotations

from typing import Any

import pandas as pd


UTC = "UTC"
DISPLAY_TIMEZONE = "Asia/Tokyo"


def to_utc_timestamp(value: Any) -> pd.Timestamp:
    """日時として解釈できる値を、タイムゾーン付きUTCへ変換する。"""
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise ValueError("時刻が空です。")
    if timestamp.tzinfo is None:
        return timestamp.tz_localize(UTC)
    return timestamp.tz_convert(UTC)


def to_utc_datetime_index(values: Any) -> pd.DatetimeIndex:
    """日時の配列を、タイムゾーン付きUTCのDatetimeIndexへ変換する。"""
    index = pd.DatetimeIndex(pd.to_datetime(values, utc=True))
    if index.hasnans:
        raise ValueError("時刻に変換できない値が含まれています。")
    return index
