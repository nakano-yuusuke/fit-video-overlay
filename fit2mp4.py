#!/usr/bin/env python3
"""FITデータをメディアへ重ねるコマンドラインエントリーポイント。"""

from __future__ import annotations

import argparse
import logging
from dataclasses import replace
from pathlib import Path

from fit_overlay.config import (
    ContactSheetConfig,
    MapOverlayConfig,
    ProcessorConfig,
    default_overlay_configs,
    load_processor_config,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="FITデータから情報オーバーレイ付きメディアを生成します。",
    )
    parser.add_argument("mp4_dir", nargs="?", type=Path, metavar="media_dir")
    parser.add_argument("fit_path", nargs="?", type=Path)
    parser.add_argument("output_dir", nargs="?", type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        help="入力、エンコード、overlayを定義したJSON設定",
    )
    parser.add_argument(
        "--debug-map",
        action="store_true",
        default=None,
        help="すべての地図overlayのデバッグ情報を表示する",
    )
    parser.add_argument(
        "--preview-layout",
        action="store_true",
        help="FITやOSMを読み込まず、overlay配置確認用のPNGを1枚だけ出力する",
    )
    parser.add_argument(
        "--preview-output",
        type=Path,
        default=None,
        help="--preview-layoutの出力先。未指定時はoutput_dir/overlay_layout_preview.png",
    )
    parser.add_argument(
        "--preview-frame",
        action="store_true",
        help="入力ディレクトリ内の全メディアへ実データoverlayを重ねた静止画を出力する",
    )
    parser.add_argument(
        "--contact-sheet-only",
        action="store_true",
        help="設定のenabledに関係なくコンタクトシートとJSONだけを生成する",
    )
    parser.add_argument(
        "--preview-at",
        default=None,
        metavar="TIME",
        help="--preview-frameで動画から切り出す位置。例: 00:03:20, 200.0, middle",
    )
    parser.add_argument(
        "--fit-time-offset",
        type=float,
        default=None,
        metavar="SECONDS",
        help="JSONのFIT時刻補正を一時的に上書きする",
    )
    parser.add_argument("--video-codec", default=None)
    parser.add_argument("--video-crf", type=int, default=None)
    parser.add_argument("--video-cq", type=int, default=None)
    parser.add_argument("--video-preset", default=None)
    parser.add_argument("--pixel-format", default=None)
    parser.add_argument(
        "--output-mode",
        choices=("composited", "transparent_overlay"),
        default=None,
        help=(
            "出力形式。compositedは入力メディアへ焼き込み、"
            "transparent_overlayは透明背景のオーバーレイだけを生成する"
        ),
    )
    parser.add_argument(
        "--copy-audio",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="入力動画の音声を最終出力へコピーする。静止画では無視される",
    )
    parser.add_argument("--ffmpeg-binary", type=Path, default=None)
    parser.add_argument("--ffprobe-binary", type=Path, default=None)
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
        help="ログ出力レベル",
    )
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> ProcessorConfig:
    if args.config is not None:
        config = load_processor_config(args.config)
    else:
        if args.mp4_dir is None or args.fit_path is None or args.output_dir is None:
            raise ValueError(
                "--configを指定するか、media_dir fit_path output_dirを指定してください。"
            )
        asset_dir = Path(__file__).resolve().parent
        refresh_rate_hz = 59.94 / 4
        config = ProcessorConfig(
            mp4_dir=args.mp4_dir,
            fit_path=args.fit_path,
            output_dir=args.output_dir,
            overlays=default_overlay_configs(asset_dir, refresh_rate_hz),
            default_refresh_rate_hz=refresh_rate_hz,
            contact_sheet=ContactSheetConfig(
                output_dir=args.output_dir / "contact_sheet"
            ),
        )

    updates = {
        "mp4_dir": args.mp4_dir,
        "fit_path": args.fit_path,
        "output_dir": args.output_dir,
        "fit_time_offset_seconds": args.fit_time_offset,
        "video_codec": args.video_codec,
        "video_crf": args.video_crf,
        "video_cq": args.video_cq,
        "video_preset": args.video_preset,
        "pixel_format": args.pixel_format,
        "output_mode": args.output_mode,
        "copy_audio": args.copy_audio,
        "ffmpeg_binary": args.ffmpeg_binary,
        "ffprobe_binary": args.ffprobe_binary,
    }
    config = replace(
        config,
        **{key: value for key, value in updates.items() if value is not None},
    )

    if args.debug_map:
        config = replace(
            config,
            overlays=tuple(
                replace(overlay, debug=True)
                if isinstance(overlay, MapOverlayConfig)
                else overlay
                for overlay in config.overlays
            ),
        )
    return config


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s [%(processName)s] %(name)s: %(message)s",
    )
    from fit_overlay.pipeline import OverlayVideoProcessor

    processor = OverlayVideoProcessor(build_config(args))
    selected_modes = sum(
        bool(value)
        for value in (
            args.preview_layout,
            args.preview_frame,
            args.contact_sheet_only,
        )
    )
    if selected_modes > 1:
        raise ValueError(
            "--preview-layout、--preview-frame、--contact-sheet-onlyは同時指定できません。"
        )
    if args.preview_layout:
        processor.write_layout_preview(args.preview_output)
    elif args.preview_frame:
        if args.preview_at is None:
            raise ValueError("--preview-frameには--preview-atを指定してください。")
        processor.write_frame_previews(args.preview_at)
    elif args.contact_sheet_only:
        processor.write_contact_sheet()
    else:
        processor.run()


if __name__ == "__main__":
    main()
