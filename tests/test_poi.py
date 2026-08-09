from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fit_overlay.config import (
    NextPoiFeatureConfig,
    PointOfInterestSourceConfig,
    PointsOfInterestConfig,
)
from fit_overlay.gpx_route import GpxRoute
from fit_overlay.next_poi import filter_points_of_interest
from fit_overlay.poi import PointOfInterest, load_points_of_interest


GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1">
  <wpt lat="35.0" lon="139.001">
    <name>Control</name>
    <cmt>control</cmt>
    <desc>PC1 First control</desc>
    <type>Dot</type>
  </wpt>
  <wpt lat="35.0" lon="139.002">
    <name>Right</name>
    <desc>Turn right</desc>
    <type>Dot</type>
  </wpt>
  <trk><trkseg>
    <trkpt lat="35.0" lon="139.0" />
    <trkpt lat="35.0" lon="139.01" />
  </trkseg></trk>
</gpx>
"""


class GpxPoiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.gpx_path = Path(self.temp_directory.name) / "route.gpx"
        self.gpx_path.write_text(GPX, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def test_load_waypoints_reads_desc_and_cmt(self) -> None:
        waypoints = GpxRoute.load_waypoints(self.gpx_path)

        self.assertEqual(waypoints[0].name, "Control")
        self.assertEqual(waypoints[0].description, "PC1 First control")
        self.assertEqual(waypoints[0].comment, "control")

    def test_gpx_source_can_use_desc_as_label(self) -> None:
        config = PointsOfInterestConfig(
            enabled=True,
            gpx_path=self.gpx_path,
            sources=(
                PointOfInterestSourceConfig(
                    type="gpx_wpt",
                    gpx_path=self.gpx_path,
                    label_field="desc",
                ),
            ),
        )

        points = load_points_of_interest(config)

        self.assertEqual(points[0].label, "PC1 First control")
        self.assertEqual(points[0].name, "Control")
        self.assertEqual(points[1].label, "Turn right")

    def test_next_poi_filter_is_reusable_for_overlay_points(self) -> None:
        points = (
            PointOfInterest(
                id="pc1",
                label="PC1 First control",
                source="gpx_wpt",
                distance_m=1000.0,
            ),
            PointOfInterest(
                id="turn",
                label="Turn right",
                source="gpx_wpt",
                distance_m=2000.0,
            ),
            PointOfInterest(
                id="goal",
                label="Goal",
                source="manual",
                distance_m=3000.0,
            ),
        )
        config = NextPoiFeatureConfig(
            enabled=True,
            sources=("gpx_wpt", "manual"),
            name_patterns=(r"(?i)^(PC|Goal)",),
        )

        filtered = filter_points_of_interest(points, config)

        self.assertEqual([point.id for point in filtered], ["pc1", "goal"])


if __name__ == "__main__":
    unittest.main()
