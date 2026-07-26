from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fit_overlay.config import GraphOverlayConfig, load_processor_config


class GraphConfigTest(unittest.TestCase):
    def test_gpx_series_uses_route_domain_without_route_altitude_feature(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gpx_path = root / "route.gpx"
            gpx_path.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1"><trk><trkseg>
<trkpt lat="35.0" lon="139.0"><ele>10</ele></trkpt>
<trkpt lat="35.0" lon="139.01"><ele>20</ele></trkpt>
</trkseg></trk></gpx>
""",
                encoding="utf-8",
            )
            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "resources": {"route_gpx_path": str(gpx_path)},
                        "input": {
                            "mp4_dir": "media",
                            "fit_path": "activity.fit",
                            "output_dir": "output",
                        },
                        "features": {
                            "route_progress": {
                                "enabled": True,
                                "add_route_altitude": False,
                            }
                        },
                        "overlays": [
                            {
                                "id": "altitude",
                                "type": "graph",
                                "x": 0,
                                "y": 0,
                                "width": 320,
                                "height": 120,
                                "engine": "matplotlib_strip",
                                "x_column": "route_progress_m",
                                "x_multiplier": 0.001,
                                "x_domain": "route",
                                "series": [
                                    {
                                        "source": "gpx",
                                        "x_column": "route_progress_m",
                                        "x_multiplier": 0.001,
                                        "column": "route_altitude_m",
                                        "reveal": "all",
                                    },
                                    {
                                        "source": "fit",
                                        "x_column": "route_progress_m",
                                        "x_multiplier": 0.001,
                                        "column": "altitude",
                                        "reveal": "past",
                                    },
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            config = load_processor_config(config_path)

        overlay = config.overlays[0]
        self.assertIsInstance(overlay, GraphOverlayConfig)
        self.assertEqual(overlay.column, "altitude")
        self.assertEqual(overlay.x_domain, "route")
        self.assertEqual(len(overlay.series), 2)
        self.assertEqual(overlay.series[0].source, "gpx")
        self.assertEqual(overlay.series[0].column, "route_altitude_m")
        self.assertEqual(overlay.series[1].reveal, "past")


if __name__ == "__main__":
    unittest.main()
