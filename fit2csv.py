#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fitファイルをcsvファイルに変換する
"""
import sys
import pandas as pd
from fitparse import FitFile

# fitファイルを読み込み、dataframeに変換する関数
def fit2df(fit_path):
    fitfile = FitFile(fit_path)
    records = []
    for record in fitfile.get_messages('record'):
        record_dict = record.get_values()
        records.append(record_dict)
    df = pd.DataFrame(records)

    # dfの緯度経度を変換する
    df['position_lat'] = df['position_lat'] * (180 / 2**31)
    df['position_long'] = df['position_long'] * (180 / 2**31)
    
    return df

if __name__ == '__main__':
    fit_path = sys.argv[1]
    output_path = sys.argv[2] + fit_path.split('/')[-1].split('.')[0] + '.csv'

    # fitファイルを読み込み、dataframeに変換する
    df = fit2df(fit_path)

    # dataframeをcsvファイルに変換する
    df.to_csv(output_path, index=False)
