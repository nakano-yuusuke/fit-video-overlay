"""元メディアのコンタクトシートと対応するFITデータJSONを生成する。"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import cv2
import ffmpeg
import numpy as np
import pandas as pd
from PIL import Image

from .config import ContactSheetConfig, ContactSheetJsonFieldConfig, ProcessorConfig


logger = logging.getLogger(__name__)
VIDEO_SUFFIXES = {".mp4"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


@dataclass(frozen=True)
class ContactSheetMedia:
    path: Path
    media_type: str
    captured_at: pd.Timestamp
    width: int
    height: int
    duration_seconds: float | None = None
    raw_start_time: pd.Timestamp | None = None
    offset_seconds: float = 0.0
    media_id: str = ""
    sample_count: int = 0


@dataclass(frozen=True)
class ContactSheetSample:
    media_path: Path
    media_type: str
    captured_at: pd.Timestamp
    source_time_seconds: float | None = None
    frame_id: str = ""


@dataclass(frozen=True)
class ContactSheetResult:
    output_dir: Path
    json_path: Path
    sheet_paths: tuple[Path, ...]
    frame_count: int


def video_sample_positions(duration: float, config: ContactSheetConfig) -> tuple[float, ...]:
    """動画長と余白設定から抽出位置を作る。"""
    last_allowed = duration - config.end_margin_seconds
    positions: list[float] = []
    position = config.start_margin_seconds
    while position <= last_allowed + 1e-9:
        positions.append(round(float(position), 9))
        position += config.interval_seconds
    if not positions and config.ensure_at_least_one_frame:
        upper = max(0.0, last_allowed)
        positions.append(min(max(0.0, duration / 2.0), upper))
    return tuple(positions)


def generate_contact_sheet(
    processor_config: ProcessorConfig,
    data: pd.DataFrame,
    *,
    read_video_raw_time: Callable[[Path, dict], pd.Timestamp],
    read_video_time: Callable[[Path, dict], pd.Timestamp],
    media_offset_for: Callable[[pd.Timestamp], float],
    read_video_frame: Callable[[Path, float, int, int], np.ndarray],
    read_image_time: Callable[[Path], pd.Timestamp],
    read_image: Callable[[Path], np.ndarray],
) -> ContactSheetResult:
    """入力ディレクトリ全体からシートとJSONを一度だけ生成する。"""
    config = processor_config.contact_sheet
    media_paths = sorted(
        path
        for path in processor_config.mp4_dir.iterdir()
        if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES | IMAGE_SUFFIXES
    )
    if not media_paths:
        raise ValueError(f"対象の動画・静止画がありません: {processor_config.mp4_dir}")

    _prepare_output(config)
    media, samples = _collect_metadata(
        media_paths,
        processor_config,
        read_video_raw_time=read_video_raw_time,
        read_video_time=read_video_time,
        media_offset_for=media_offset_for,
        read_image_time=read_image_time,
    )
    media = _assign_media_ids(media)
    media_by_path = {item.path: item for item in media}
    samples = tuple(
        replace(sample, frame_id=f"F{index:06d}")
        for index, sample in enumerate(
            sorted(
                samples,
                key=lambda item: (
                    item.captured_at,
                    item.media_path.name,
                    -1.0 if item.source_time_seconds is None else item.source_time_seconds,
                ),
            ),
            start=1,
        )
    )

    config.output_dir.mkdir(parents=True, exist_ok=True)
    sheet_paths = _render_sheets(
        samples,
        media_by_path,
        config,
        read_video_frame=read_video_frame,
        read_image=read_image,
    )
    payload, debug_payload = _build_json(config, data, media, samples)
    json_path = config.output_dir / config.json_filename
    _write_json(json_path, payload)
    if config.write_debug_json:
        _write_json(config.output_dir / "contact_sheet_debug.json", debug_payload)
    logger.info(
        "contact_sheet_generated output_dir=%s sheets=%d frames=%d",
        config.output_dir,
        len(sheet_paths),
        len(samples),
    )
    return ContactSheetResult(config.output_dir, json_path, sheet_paths, len(samples))


def _collect_metadata(
    paths: list[Path],
    processor_config: ProcessorConfig,
    *,
    read_video_raw_time: Callable[[Path, dict], pd.Timestamp],
    read_video_time: Callable[[Path, dict], pd.Timestamp],
    media_offset_for: Callable[[pd.Timestamp], float],
    read_image_time: Callable[[Path], pd.Timestamp],
) -> tuple[tuple[ContactSheetMedia, ...], tuple[ContactSheetSample, ...]]:
    media: list[ContactSheetMedia] = []
    samples: list[ContactSheetSample] = []
    errors: list[str] = []
    for path in paths:
        try:
            if path.suffix.lower() in VIDEO_SUFFIXES:
                info = ffmpeg.probe(
                    str(path), cmd=str(processor_config.ffprobe_binary)
                )
                stream = next(
                    item for item in info.get("streams", ())
                    if item.get("codec_type") == "video"
                )
                duration = float(
                    stream.get("duration") or info.get("format", {}).get("duration")
                )
                raw_time = read_video_raw_time(path, info)
                captured_at = read_video_time(path, info)
                positions = video_sample_positions(duration, processor_config.contact_sheet)
                media.append(
                    ContactSheetMedia(
                        path=path,
                        media_type="video",
                        captured_at=captured_at,
                        width=int(stream["width"]),
                        height=int(stream["height"]),
                        duration_seconds=duration,
                        raw_start_time=raw_time,
                        offset_seconds=media_offset_for(raw_time),
                        sample_count=len(positions),
                    )
                )
                samples.extend(
                    ContactSheetSample(
                        media_path=path,
                        media_type="video",
                        captured_at=captured_at + pd.Timedelta(seconds=position),
                        source_time_seconds=position,
                    )
                    for position in positions
                )
            else:
                with Image.open(path) as image:
                    width, height = image.size
                captured_at = read_image_time(path)
                media.append(
                    ContactSheetMedia(
                        path=path,
                        media_type="image",
                        captured_at=captured_at,
                        width=width,
                        height=height,
                        sample_count=1,
                    )
                )
                samples.append(
                    ContactSheetSample(path, "image", captured_at)
                )
        except Exception as error:
            errors.append(f"{path.name}: {error}")
            logger.exception("contact_sheet_metadata_failed path=%s", path)
    if errors:
        raise RuntimeError("メディア情報の収集に失敗しました: " + "; ".join(errors))
    return tuple(media), tuple(samples)


def _assign_media_ids(
    media: tuple[ContactSheetMedia, ...],
) -> tuple[ContactSheetMedia, ...]:
    return tuple(
        replace(item, media_id=f"M{index:04d}")
        for index, item in enumerate(
            sorted(media, key=lambda value: (value.captured_at, value.path.name)),
            start=1,
        )
    )


def _prepare_output(config: ContactSheetConfig) -> None:
    targets = [config.output_dir / config.json_filename]
    targets.extend(config.output_dir.glob("sheet_*.jpg"))
    targets.extend(config.output_dir.glob("sheet_*.png"))
    debug_path = config.output_dir / "contact_sheet_debug.json"
    if debug_path.exists():
        targets.append(debug_path)
    existing = sorted({path for path in targets if path.exists()})
    if existing and not config.overwrite:
        raise FileExistsError(
            "コンタクトシート出力が既に存在します: "
            + ", ".join(str(path) for path in existing)
        )
    if config.overwrite:
        for path in existing:
            path.unlink()


def _render_sheets(
    samples: tuple[ContactSheetSample, ...],
    media_by_path: dict[Path, ContactSheetMedia],
    config: ContactSheetConfig,
    *,
    read_video_frame: Callable[[Path, float, int, int], np.ndarray],
    read_image: Callable[[Path], np.ndarray],
) -> tuple[Path, ...]:
    frames_per_sheet = config.columns * config.rows
    cell_height = config.thumbnail_height + config.label_height
    timezone = ZoneInfo(config.timezone)
    output_paths: list[Path] = []
    errors: list[str] = []
    for sheet_index, start in enumerate(range(0, len(samples), frames_per_sheet), 1):
        canvas = np.empty(
            (config.rows * cell_height, config.columns * config.thumbnail_width, 3),
            dtype=np.uint8,
        )
        canvas[:] = config.background_color
        for offset, sample in enumerate(samples[start : start + frames_per_sheet]):
            row, column = divmod(offset, config.columns)
            x = column * config.thumbnail_width
            y = row * cell_height
            try:
                media = media_by_path[sample.media_path]
                if sample.media_type == "video":
                    assert sample.source_time_seconds is not None
                    source = read_video_frame(
                        sample.media_path,
                        sample.source_time_seconds,
                        media.width,
                        media.height,
                    )
                else:
                    source = read_image(sample.media_path)
                thumbnail = _fit_image(source, config)
                canvas[y : y + config.thumbnail_height, x : x + config.thumbnail_width] = thumbnail
                if config.label_height:
                    shown = sample.captured_at.tz_convert(timezone).strftime(config.time_format)
                    _draw_label(
                        canvas,
                        f"{sample.frame_id}   {shown}",
                        x,
                        y + config.thumbnail_height,
                        config.thumbnail_width,
                        config.label_height,
                    )
            except Exception as error:
                errors.append(f"{sample.media_path.name}: {error}")
                logger.exception("contact_sheet_sample_failed path=%s", sample.media_path)
        output_path = config.output_dir / f"sheet_{sheet_index:04d}.{config.image_format}"
        _write_sheet(output_path, canvas, config)
        output_paths.append(output_path)
    if errors:
        raise RuntimeError("サンプル画像の生成に失敗しました: " + "; ".join(errors))
    return tuple(output_paths)


def _fit_image(source: np.ndarray, config: ContactSheetConfig) -> np.ndarray:
    if source.ndim != 3 or source.shape[2] not in {3, 4}:
        raise ValueError("元画像はRGBまたはRGBAである必要があります。")
    scale = min(
        config.thumbnail_width / source.shape[1],
        config.thumbnail_height / source.shape[0],
    )
    width = max(1, int(round(source.shape[1] * scale)))
    height = max(1, int(round(source.shape[0] * scale)))
    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    resized = cv2.resize(source, (width, height), interpolation=interpolation)
    target = np.empty((config.thumbnail_height, config.thumbnail_width, 3), dtype=np.uint8)
    target[:] = config.background_color
    x = (config.thumbnail_width - width) // 2
    y = (config.thumbnail_height - height) // 2
    if resized.shape[2] == 4:
        alpha = resized[:, :, 3:4].astype(np.float32) / 255.0
        background = target[y : y + height, x : x + width].astype(np.float32)
        rgb = resized[:, :, :3].astype(np.float32)
        target[y : y + height, x : x + width] = np.clip(
            rgb * alpha + background * (1.0 - alpha), 0, 255
        ).astype(np.uint8)
    else:
        target[y : y + height, x : x + width] = resized
    return target


def _draw_label(
    image: np.ndarray,
    text: str,
    x: int,
    y: int,
    width: int,
    height: int,
) -> None:
    font_scale = max(0.3, min(0.8, height / 45.0))
    thickness = max(1, int(round(font_scale * 1.5)))
    text_size, baseline = cv2.getTextSize(
        text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
    )
    text_x = x + 8
    text_y = y + max(text_size[1] + 2, (height + text_size[1] - baseline) // 2)
    cv2.putText(
        image,
        text,
        (text_x, min(y + height - baseline, text_y)),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA,
    )


def _write_sheet(path: Path, image: np.ndarray, config: ContactSheetConfig) -> None:
    bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    parameters = (
        [cv2.IMWRITE_JPEG_QUALITY, config.jpeg_quality]
        if config.image_format == "jpg"
        else []
    )
    success, encoded = cv2.imencode(f".{config.image_format}", bgr, parameters)
    if not success:
        raise RuntimeError(f"コンタクトシートをエンコードできません: {path}")
    temporary = path.parent / f".{path.name}.{os.getpid()}.part"
    temporary.write_bytes(encoded.tobytes())
    temporary.replace(path)


def _build_json(
    config: ContactSheetConfig,
    data: pd.DataFrame,
    media: tuple[ContactSheetMedia, ...],
    samples: tuple[ContactSheetSample, ...],
) -> tuple[dict[str, object], dict[str, object]]:
    timezone = ZoneInfo(config.timezone)
    frames_per_sheet = config.columns * config.rows
    available_fields = tuple(
        field for field in config.json_fields if field.source_column in data.columns
    )
    for field in config.json_fields:
        if field.source_column not in data.columns:
            logger.warning(
                "contact_sheet_json_column_missing source_column=%s",
                field.source_column,
            )
    media_by_path = {item.path: item for item in media}
    frame_records: list[dict[str, object]] = []
    debug_records: list[dict[str, object]] = []
    previous_time: pd.Timestamp | None = None
    for index, sample in enumerate(samples):
        sheet_index, cell_index = divmod(index, frames_per_sheet)
        row, column = divmod(cell_index, config.columns)
        matched, row_data, matched_at = _match_fit_row(data, sample.captured_at)
        values: dict[str, object] = {}
        conversions: dict[str, object] = {}
        if matched and row_data is not None:
            for field in available_fields:
                original = row_data[field.source_column]
                converted = _convert_field(original, field)
                conversions[field.output_name] = {
                    "source": _json_scalar(original),
                    "converted": converted,
                }
                if converted is not None:
                    values[field.output_name] = converted
        gap = (
            None
            if previous_time is None
            else _finite_number((sample.captured_at - previous_time).total_seconds())
        )
        previous_time = sample.captured_at
        source: dict[str, object] = {
            "type": sample.media_type,
            "media_id": media_by_path[sample.media_path].media_id,
        }
        if sample.source_time_seconds is not None:
            source.update(
                source_time_seconds=sample.source_time_seconds,
                source_timecode=_timecode(sample.source_time_seconds),
            )
        frame_records.append(
            {
                "frame_id": sample.frame_id,
                "sheet": {
                    "number": sheet_index + 1,
                    "filename": f"sheet_{sheet_index + 1:04d}.{config.image_format}",
                    "row": row + 1,
                    "column": column + 1,
                },
                "source": source,
                "captured_at": _iso_time(sample.captured_at, timezone),
                "capture_gap_seconds": gap,
                "fit_match": {"status": "matched" if matched else "out_of_range"},
                "data": values,
            }
        )
        media_item = media_by_path[sample.media_path]
        debug_records.append(
            {
                "frame_id": sample.frame_id,
                "captured_at_utc": sample.captured_at.isoformat(),
                "captured_at_display": _iso_time(sample.captured_at, timezone),
                "selected_row_at": matched_at.isoformat() if matched_at is not None else None,
                "selected_row_age_seconds": (
                    (sample.captured_at - matched_at).total_seconds()
                    if matched_at is not None else None
                ),
                "field_conversions": conversions,
                "video_creation_time": (
                    media_item.raw_start_time.isoformat()
                    if media_item.raw_start_time is not None else None
                ),
                "media_time_offset_seconds": media_item.offset_seconds,
                "requested_source_time_seconds": sample.source_time_seconds,
            }
        )

    sheet_records = []
    for sheet_index, start in enumerate(range(0, len(samples), frames_per_sheet), 1):
        group = samples[start : start + frames_per_sheet]
        sheet_records.append(
            {
                "sheet_number": sheet_index,
                "filename": f"sheet_{sheet_index:04d}.{config.image_format}",
                "first_frame_id": group[0].frame_id,
                "last_frame_id": group[-1].frame_id,
                "start_time": _iso_time(group[0].captured_at, timezone),
                "end_time": _iso_time(group[-1].captured_at, timezone),
            }
        )

    media_records = []
    for item in media:
        record: dict[str, object] = {
            "media_id": item.media_id,
            "type": item.media_type,
            "filename": item.path.name,
            "width": item.width,
            "height": item.height,
        }
        if item.media_type == "video":
            record.update(
                duration_seconds=round(float(item.duration_seconds or 0.0), 3),
                resolved_start_time=_iso_time(item.captured_at, timezone),
                sample_count=item.sample_count,
            )
        else:
            record.update(
                captured_at=_iso_time(item.captured_at, timezone),
                sample_count=1,
            )
        media_records.append(record)

    payload: dict[str, object] = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone).isoformat(timespec="seconds"),
        "timezone": config.timezone,
        "sampling": {
            "interval_seconds": config.interval_seconds,
            "start_margin_seconds": config.start_margin_seconds,
            "end_margin_seconds": config.end_margin_seconds,
            "sort": "captured_at",
        },
        "contact_sheet": {
            "columns": config.columns,
            "rows": config.rows,
            "thumbnail_width": config.thumbnail_width,
            "thumbnail_height": config.thumbnail_height,
            "label_height": config.label_height,
            "frames_per_sheet": frames_per_sheet,
            "sheet_count": math.ceil(len(samples) / frames_per_sheet),
            "frame_count": len(samples),
        },
        "media": media_records,
        "sheets": sheet_records,
        "frames": frame_records,
    }
    return payload, {"schema_version": "1.0", "frames": debug_records}


def _match_fit_row(
    data: pd.DataFrame, captured_at: pd.Timestamp
) -> tuple[bool, pd.Series | None, pd.Timestamp | None]:
    if data.empty or captured_at < data.index[0] or captured_at > data.index[-1]:
        return False, None, None
    position = int(data.index.searchsorted(captured_at, side="right")) - 1
    return True, data.iloc[position], data.index[position]


def _convert_field(value: object, field: ContactSheetJsonFieldConfig) -> object | None:
    if _is_missing(value):
        return None
    converted = _json_scalar(value)
    if isinstance(converted, (int, float)) and not isinstance(converted, bool):
        converted = converted * field.multiplier
        if field.decimals is not None:
            converted = round(converted, field.decimals)
            if field.decimals == 0:
                converted = int(converted)
    return converted


def _is_missing(value: object) -> bool:
    if isinstance(value, str):
        return value == ""
    try:
        missing = pd.isna(value)
        if isinstance(missing, (bool, np.bool_)) and bool(missing):
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(value, (int, float, np.number)):
        return not math.isfinite(float(value))
    return False


def _json_scalar(value: object) -> object | None:
    if _is_missing(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _finite_number(value: float) -> float | int:
    return int(value) if value.is_integer() else value


def _iso_time(value: pd.Timestamp, timezone: ZoneInfo) -> str:
    return value.tz_convert(timezone).to_pydatetime().isoformat(timespec="milliseconds")


def _timecode(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    total_seconds, milliseconds = divmod(milliseconds, 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.parent / f".{path.name}.{os.getpid()}.part"
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write("\n")
    temporary.replace(path)
