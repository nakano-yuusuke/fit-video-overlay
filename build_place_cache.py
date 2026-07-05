#!/usr/bin/env python3
"""OSM PBFから地名境界キャッシュを事前生成する。"""

from __future__ import annotations

import argparse
from pathlib import Path

from fit_overlay.config import load_processor_config
from fit_overlay.place_names import build_boundary_index_cache


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="features.place_names用の行政境界キャッシュを生成します。",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("overlay_config.json"),
        help="place_names設定を含むJSON設定",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="既存の全国境界キャッシュがあっても作り直す",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_processor_config(args.config).place_names
    cache_path, boundary_count = build_boundary_index_cache(
        config,
        force=args.force,
    )
    print(f"境界キャッシュ: {cache_path}")
    print(f"境界数: {boundary_count}")


if __name__ == "__main__":
    main()
