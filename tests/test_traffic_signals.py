from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from fit_overlay.config import TrafficSignalsFeatureConfig
from fit_overlay.traffic_signals import build_traffic_signal_profile


class TrafficSignalProfileTest(unittest.TestCase):
    def test_builds_complete_route_profile_without_adding_fit_column(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            gpx_path = Path(directory) / "route.gpx"
            gpx_path.write_text(
                """<gpx><trk><trkseg>
<trkpt lat="35.0" lon="139.0"/>
<trkpt lat="35.0" lon="139.03"/>
</trkseg></trk></gpx>""",
                encoding="utf-8",
            )
            fit_data = pd.DataFrame(
                {
                    "position_lat": [35.0, 35.0],
                    "position_long": [139.0, 139.01],
                },
                index=pd.DatetimeIndex(
                    ["2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z"]
                ),
            )
            config = TrafficSignalsFeatureConfig(
                enabled=True,
                route_source="gpx",
                gpx_path=gpx_path,
                bucket_distance_m=1_000.0,
            )

            with patch(
                "fit_overlay.traffic_signals._load_or_fetch_signals",
                return_value=[(139.005, 35.0), (139.025, 35.0)],
            ):
                result = build_traffic_signal_profile(fit_data, config)

        self.assertNotIn(config.column, fit_data.columns)
        self.assertIsNotNone(result.route_progress)
        self.assertGreater(result.profile.total_distance_m, 2_000.0)
        values = result.profile.series(config.column)
        self.assertEqual(values.iloc[0], 1.0)
        self.assertEqual(values.iloc[1], 0.0)
        self.assertEqual(values.iloc[2], 1.0)


if __name__ == "__main__":
    unittest.main()
