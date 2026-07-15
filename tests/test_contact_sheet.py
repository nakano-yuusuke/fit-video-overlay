from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from fit_overlay.config import (
    ContactSheetConfig,
    ContactSheetJsonFieldConfig,
    ProcessorConfig,
    load_processor_config,
)
from fit_overlay.contact_sheet import generate_contact_sheet, video_sample_positions


class ContactSheetConfigTest(unittest.TestCase):
    def test_loads_relative_output_and_allows_no_overlays(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "input": {
                            "mp4_dir": "media",
                            "fit_path": "activity.fit",
                            "output_dir": "output",
                        },
                        "contact_sheet": {
                            "enabled": True,
                            "output_dir": "sheets",
                            "json_fields": [
                                {"source_column": "speed", "output_name": "speed_kmh"}
                            ],
                        },
                        "overlays": [],
                    }
                ),
                encoding="utf-8",
            )
            config = load_processor_config(config_path)
            self.assertEqual(config.contact_sheet.output_dir, root / "output" / "sheets")
            self.assertEqual(config.overlays, ())

    def test_rejects_invalid_interval_and_duplicate_output_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = {
                "input": {
                    "mp4_dir": "media",
                    "fit_path": "activity.fit",
                    "output_dir": "output",
                },
                "overlays": [],
            }
            for contact_sheet in (
                {"interval_seconds": 0},
                {
                    "json_fields": [
                        {"source_column": "a", "output_name": "same"},
                        {"source_column": "b", "output_name": "same"},
                    ]
                },
            ):
                config_path = root / "config.json"
                config_path.write_text(
                    json.dumps({**base, "contact_sheet": contact_sheet}),
                    encoding="utf-8",
                )
                with self.assertRaises(ValueError):
                    load_processor_config(config_path)


class ContactSheetGenerationTest(unittest.TestCase):
    def test_video_sample_positions_include_margins_and_short_fallback(self) -> None:
        config = ContactSheetConfig(
            interval_seconds=5.0,
            start_margin_seconds=1.0,
            end_margin_seconds=0.5,
        )
        self.assertEqual(video_sample_positions(10.0, config), (1.0, 6.0))
        self.assertEqual(video_sample_positions(1.0, config), (0.5,))

    def test_images_are_sorted_and_json_uses_preceding_fit_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media_dir = root / "media"
            output_dir = root / "output" / "contact_sheet"
            media_dir.mkdir()
            first_path = media_dir / "later.jpg"
            second_path = media_dir / "earlier.png"
            Image.new("RGB", (40, 20), (255, 0, 0)).save(first_path)
            Image.new("RGB", (20, 40), (0, 255, 0)).save(second_path)

            times = {
                first_path: pd.Timestamp("2026-01-01T00:00:06Z"),
                second_path: pd.Timestamp("2025-12-31T23:59:59Z"),
            }
            data = pd.DataFrame(
                {
                    "speed": [1.0, 2.0, 3.0],
                    "place_name": ["A", "B", "C"],
                },
                index=pd.DatetimeIndex(
                    [
                        "2026-01-01T00:00:00Z",
                        "2026-01-01T00:00:05Z",
                        "2026-01-01T00:00:10Z",
                    ]
                ),
            )
            contact_config = ContactSheetConfig(
                enabled=True,
                output_dir=output_dir,
                columns=1,
                rows=2,
                thumbnail_width=80,
                thumbnail_height=50,
                label_height=20,
                image_format="png",
                json_fields=(
                    ContactSheetJsonFieldConfig("speed", "speed_kmh", 3.6, 1),
                    ContactSheetJsonFieldConfig("place_name", "place_name"),
                    ContactSheetJsonFieldConfig("missing", "missing"),
                ),
            )
            processor_config = ProcessorConfig(
                mp4_dir=media_dir,
                fit_path=root / "unused.fit",
                output_dir=root / "output",
                overlays=(),
                contact_sheet=contact_config,
            )

            result = generate_contact_sheet(
                processor_config,
                data,
                read_video_raw_time=lambda path, info: pd.Timestamp(0, tz="UTC"),
                read_video_time=lambda path, info: pd.Timestamp(0, tz="UTC"),
                media_offset_for=lambda timestamp: 0.0,
                read_video_frame=lambda path, seconds, width, height: np.zeros(
                    (height, width, 3), dtype=np.uint8
                ),
                read_image_time=lambda path: times[path],
                read_image=lambda path: np.asarray(Image.open(path).convert("RGB")),
            )

            self.assertEqual(result.frame_count, 2)
            self.assertEqual(len(result.sheet_paths), 1)
            payload = json.loads(result.json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["frames"][0]["source"]["media_id"], "M0001")
            self.assertEqual(payload["frames"][0]["fit_match"]["status"], "out_of_range")
            self.assertEqual(payload["frames"][0]["data"], {})
            self.assertEqual(payload["frames"][1]["data"]["speed_kmh"], 7.2)
            self.assertEqual(payload["frames"][1]["data"]["place_name"], "B")
            self.assertNotIn("missing", payload["frames"][1]["data"])
            self.assertEqual(payload["frames"][1]["capture_gap_seconds"], 7)

            sheet = np.asarray(Image.open(result.sheet_paths[0]).convert("RGB"))
            self.assertEqual(sheet.shape, (140, 80, 3))

            no_overwrite = replace(
                processor_config,
                contact_sheet=replace(contact_config, overwrite=False),
            )
            with self.assertRaises(FileExistsError):
                generate_contact_sheet(
                    no_overwrite,
                    data,
                    read_video_raw_time=lambda path, info: pd.Timestamp(0, tz="UTC"),
                    read_video_time=lambda path, info: pd.Timestamp(0, tz="UTC"),
                    media_offset_for=lambda timestamp: 0.0,
                    read_video_frame=lambda path, seconds, width, height: np.zeros(
                        (height, width, 3), dtype=np.uint8
                    ),
                    read_image_time=lambda path: times[path],
                    read_image=lambda path: np.asarray(Image.open(path).convert("RGB")),
                )


if __name__ == "__main__":
    unittest.main()
