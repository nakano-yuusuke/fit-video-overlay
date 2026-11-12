#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fitファイルをcsvファイルに変換する
"""
import sys
import pandas as pd
from fitparse import FitFile

# fitファイルを読み込み、dataframeに変換する関数
def fit2df(fit_path):
    return _read_fit_data(fit_path, include_correlations=False)[0]


def fit2df_with_correlations(fit_path):
    """走行レコードと時刻相関メッセージを同じFIT読込で取得する。"""
    return _read_fit_data(fit_path, include_correlations=True)


def _read_fit_data(fit_path, *, include_correlations):
    fitfile = FitFile(fit_path)
    records = []
    correlations = []
    messages = (
        fitfile.get_messages()
        if include_correlations
        else fitfile.get_messages('record')
    )
    for message in messages:
        if message.name == 'record':
            records.append(message.get_values())
        elif include_correlations and message.name == 'timestamp_correlation':
            correlations.append(message.get_values())
    df = pd.DataFrame(records)

    # dfの緯度経度を変換する
    for column in ('position_lat', 'position_long'):
        if column in df.columns:
            df[column] = df[column] * (180 / 2**31)
    
    return df, pd.DataFrame(correlations)

if __name__ == '__main__':
    fit_path = sys.argv[1]
    output_path = sys.argv[2] + fit_path.split('/')[-1].split('.')[0] + '.csv'

    # fitファイルを読み込み、dataframeに変換する
    df = fit2df(fit_path)

    # dataframeをcsvファイルに変換する
    df.to_csv(output_path, index=False)
