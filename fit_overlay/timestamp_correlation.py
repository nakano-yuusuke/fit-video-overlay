"""FITのUTC時刻をtimestamp_correlationの内部時計へ写像する。"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd


logger = logging.getLogger(__name__)


def correct_fit_timestamps(
    timestamps: pd.DatetimeIndex,
    correlations: pd.DataFrame,
) -> pd.DatetimeIndex:
    """UTC−内部時計の差をUTC時刻上で補間し、元record時刻から引く。"""
    required = {"timestamp", "system_timestamp"}
    if correlations.empty or not required.issubset(correlations.columns):
        raise ValueError(
            "FIT時刻相関補正が有効ですが、有効なtimestamp_correlation"
            "（timestampとsystem_timestamp）がありません。"
        )

    utc = _correlation_clock(correlations, "timestamp", "fractional_timestamp")
    system = _correlation_clock(
        correlations, "system_timestamp", "fractional_system_timestamp"
    )
    valid = utc.notna() & system.notna()
    invalid_count = int((~valid).sum())
    if invalid_count:
        logger.warning(
            "fit_timestamp_correlation ignored_invalid_messages=%d", invalid_count
        )
    samples = pd.DataFrame({"utc": utc[valid], "system": system[valid]})
    if samples.empty:
        raise ValueError(
            "FIT時刻相関補正が有効ですが、有効なtimestamp_correlationがありません。"
        )

    # 同一UTCに異なる内部時計がある場合は、写像を一意に決められない。
    if (samples.groupby("utc")["system"].nunique() > 1).any():
        raise ValueError(
            "timestamp_correlationの同じUTC時刻に異なるsystem_timestampがあります。"
        )
    samples = samples.drop_duplicates("utc").sort_values("utc", kind="stable")
    origin = samples["utc"].iloc[0]
    sample_seconds = (samples["utc"] - origin).dt.total_seconds().to_numpy()
    deltas = (samples["utc"] - samples["system"]).dt.total_seconds().to_numpy()
    # Unix epochの巨大な浮動小数値を避け、サブ秒の精度を維持する。
    record_seconds = (timestamps - origin).total_seconds().to_numpy()
    offsets = np.interp(record_seconds, sample_seconds, deltas)
    corrected = timestamps - pd.to_timedelta(offsets, unit="s")
    outside_range = (record_seconds < sample_seconds[0]) | (
        record_seconds > sample_seconds[-1]
    )
    logger.info(
        "fit_timestamp_correlation samples=%d first=%s last=%s "
        "utc_minus_system_seconds_min=%.6f max=%.6f "
        "applied_offset_seconds_min=%.6f max=%.6f "
        "outside_sample_range=%d backward_steps=%d",
        len(samples),
        samples["utc"].iloc[0],
        samples["utc"].iloc[-1],
        float(deltas.min()),
        float(deltas.max()),
        float(-offsets.max()),
        float(-offsets.min()),
        int(outside_range.sum()),
        int((np.diff(corrected.asi8) < 0).sum()),
    )
    return corrected


def _correlation_clock(
    correlations: pd.DataFrame,
    column: str,
    fractional_column: str,
) -> pd.Series:
    clock = pd.to_datetime(correlations[column], utc=True, errors="coerce")
    # SDKにはfractional_*（秒）と*_ms（ミリ秒）の2表現がある。
    # 両方あるときはミリ秒を優先し、同じ小数部を二重に加算しない。
    fractions = pd.to_numeric(
        correlations.get(
            fractional_column, pd.Series(np.nan, index=correlations.index)
        ),
        errors="coerce",
    )
    milliseconds = pd.to_numeric(
        correlations.get(f"{column}_ms", pd.Series(np.nan, index=correlations.index)),
        errors="coerce",
    )
    subsecond = (milliseconds / 1000).combine_first(fractions).fillna(0)
    finite = np.isfinite(subsecond) & (subsecond >= 0) & (subsecond < 1)
    clock = clock + pd.to_timedelta(subsecond.where(finite, 0), unit="s")
    return clock.where(finite)
