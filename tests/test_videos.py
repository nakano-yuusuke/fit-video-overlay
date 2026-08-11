from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from fit_overlay.config import (
    LayoutConfig,
    ProcessorConfig,
    VideoConfig,
    load_processor_config,
)


class VideoConfigTest(unittest.TestCase):
    def test_contain_uses_layout_reference_resolution(self) -> None:
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
                        "layout": {"reference_resolution": [3840, 2160]},
                        "videos": {
                            "resize_mode": "contain",
                            "background_color": [12, 34, 56],
                        },
                        "overlays": [],
                    }
                ),
                encoding="utf-8",
            )

            config = load_processor_config(config_path)

            self.assertEqual(config.videos.resize_mode, "contain")
            self.assertEqual(config.videos.background_color, (12, 34, 56))

    def test_original_is_the_backward_compatible_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "input": {
                            "mp4_dir": "media",
                            "fit_path": "activity.fit",
                            "output_dir": "output",
                        },
                        "overlays": [],
                    }
                ),
                encoding="utf-8",
            )

            config = load_processor_config(config_path)

            self.assertEqual(config.videos.resize_mode, "original")

    def test_rejects_invalid_mode_and_background_color(self) -> None:
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
            for videos in (
                {"resize_mode": "cover"},
                {"background_color": [0, 0, 256]},
                {"resize_mode": "contain"},
                {"canvas_resolution": [1920, 1080]},
            ):
                config_path = root / "config.json"
                config_path.write_text(
                    json.dumps({**base, "videos": videos}),
                    encoding="utf-8",
                )
                with self.assertRaises(ValueError):
                    load_processor_config(config_path)


class VideoContainTest(unittest.TestCase):
    def _processor(self, resize_mode: str = "contain"):
        from fit_overlay.pipeline import OverlayVideoProcessor

        config = ProcessorConfig(
            mp4_dir=Path("media"),
            fit_path=Path("activity.fit"),
            output_dir=Path("output"),
            overlays=(),
            layout=LayoutConfig(reference_resolution=(16, 10)),
            videos=VideoConfig(
                resize_mode=resize_mode,
                background_color=(10, 20, 30),
            ),
        )
        return OverlayVideoProcessor(config)

    def test_four_by_three_frame_is_centered_without_cropping(self) -> None:
        source = np.full((6, 8, 3), (200, 100, 50), dtype=np.uint8)

        result = self._processor()._prepare_video_frame(source)

        self.assertEqual(result.shape, (10, 16, 3))
        self.assertTrue(np.all(result[:, :2] == (10, 20, 30)))
        self.assertTrue(np.all(result[:, 14:] == (10, 20, 30)))
        self.assertTrue(np.all(result[:, 2:14] == (200, 100, 50)))

    def test_original_mode_returns_the_source_frame(self) -> None:
        source = np.full((8, 6, 3), (200, 100, 50), dtype=np.uint8)

        result = self._processor(resize_mode="original")._prepare_video_frame(
            source
        )

        self.assertIs(result, source)


if __name__ == "__main__":
    unittest.main()
