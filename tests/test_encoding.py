from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fit_overlay.config import ProcessorConfig, load_processor_config


class EncodingConfigTest(unittest.TestCase):
    def test_loads_nvenc_gop_options(self) -> None:
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
                        "encoding": {
                            "codec": "hevc_nvenc",
                            "bframes": 0,
                            "gop_size": 60,
                            "no_scenecut": True,
                            "strict_gop": True,
                        },
                        "overlays": [],
                    }
                ),
                encoding="utf-8",
            )

            config = load_processor_config(config_path)

            self.assertEqual(config.video_bframes, 0)
            self.assertEqual(config.video_gop_size, 60)
            self.assertTrue(config.video_no_scenecut)
            self.assertTrue(config.video_strict_gop)

    def test_builds_nvenc_gop_options(self) -> None:
        from fit_overlay.pipeline import OverlayVideoProcessor

        config = ProcessorConfig(
            mp4_dir=Path("media"),
            fit_path=Path("activity.fit"),
            output_dir=Path("output"),
            overlays=(),
            video_codec="hevc_nvenc",
            video_bframes=0,
            video_gop_size=60,
            video_no_scenecut=True,
            video_strict_gop=True,
        )

        options = OverlayVideoProcessor(config)._composited_output_options()

        self.assertEqual(options["bf"], 0)
        self.assertEqual(options["g"], 60)
        self.assertEqual(options["no-scenecut"], 1)
        self.assertEqual(options["strict_gop"], 1)


if __name__ == "__main__":
    unittest.main()
