from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from fit_overlay.config import (
    LayoutConfig,
    ProcessorConfig,
    StillImageConfig,
    load_processor_config,
)


class StillImageConfigTest(unittest.TestCase):
    def test_contain_defaults_to_layout_reference_resolution(self) -> None:
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
                        "layout": {"reference_resolution": [1920, 1080]},
                        "still_images": {
                            "resize_mode": "contain",
                            "background_color": [12, 34, 56],
                        },
                        "overlays": [],
                    }
                ),
                encoding="utf-8",
            )

            config = load_processor_config(config_path)

            self.assertEqual(config.still_images.canvas_resolution, (1920, 1080))
            self.assertEqual(config.still_images.resize_mode, "contain")
            self.assertEqual(config.still_images.background_color, (12, 34, 56))

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
            for still_images in (
                {"resize_mode": "cover"},
                {"background_color": [0, 0, 256]},
            ):
                config_path = root / "config.json"
                config_path.write_text(
                    json.dumps({**base, "still_images": still_images}),
                    encoding="utf-8",
                )
                with self.assertRaises(ValueError):
                    load_processor_config(config_path)


class StillImageContainTest(unittest.TestCase):
    def _processor(self):
        from fit_overlay.pipeline import OverlayVideoProcessor

        config = ProcessorConfig(
            mp4_dir=Path("media"),
            fit_path=Path("activity.fit"),
            output_dir=Path("output"),
            overlays=(),
            layout=LayoutConfig(reference_resolution=(16, 9)),
            still_images=StillImageConfig(
                canvas_resolution=(16, 9),
                resize_mode="contain",
                background_color=(10, 20, 30),
            ),
        )
        return OverlayVideoProcessor(config)

    def test_landscape_image_is_centered_without_cropping(self) -> None:
        source = np.full((3, 4, 3), (200, 100, 50), dtype=np.uint8)

        result = self._processor()._prepare_still_image(source)

        self.assertEqual(result.shape, (9, 16, 4))
        self.assertTrue(np.all(result[:, :2, :3] == (10, 20, 30)))
        self.assertTrue(np.all(result[:, 14:, :3] == (10, 20, 30)))
        self.assertTrue(np.all(result[:, 2:14, :3] == (200, 100, 50)))

    def test_portrait_image_is_centered_without_cropping(self) -> None:
        source = np.full((4, 3, 3), (50, 100, 200), dtype=np.uint8)

        result = self._processor()._prepare_still_image(source)

        self.assertEqual(result.shape, (9, 16, 4))
        self.assertTrue(np.all(result[:, :4, :3] == (10, 20, 30)))
        self.assertTrue(np.all(result[:, 11:, :3] == (10, 20, 30)))
        self.assertTrue(np.all(result[:, 4:11, :3] == (50, 100, 200)))


if __name__ == "__main__":
    unittest.main()
