from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from fit_overlay.route_feature_profile import RouteFeatureProfile


class RouteFeatureProfileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fit_data = pd.DataFrame(
            {"route_progress_m": [100.0, 1_500.0]},
            index=pd.DatetimeIndex(
                ["2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z"]
            ),
        )
        self.profile = RouteFeatureProfile(
            pd.DataFrame(
                {"traffic_signal_count_per_km": [2.0, 4.0, 4.0]},
                index=pd.Index(
                    [0.0, 1_000.0, 3_000.0],
                    name="route_distance_m",
                ),
            )
        )

    def test_maps_fit_progress_without_mutating_fit_data(self) -> None:
        resolved = self.profile.attach_columns(
            self.fit_data,
            ["traffic_signal_count_per_km"],
        )

        self.assertNotIn("traffic_signal_count_per_km", self.fit_data.columns)
        self.assertEqual(
            resolved["traffic_signal_count_per_km"].tolist(),
            [2.0, 4.0],
        )

    def test_merges_profiles_with_different_distance_boundaries(self) -> None:
        toilets = RouteFeatureProfile(
            pd.DataFrame(
                {"toilet_count_per_km": [0.0, 1.0, 1.0]},
                index=pd.Index(
                    [0.0, 2_000.0, 3_000.0],
                    name="route_distance_m",
                ),
            )
        )

        merged = self.profile.merge(toilets)

        self.assertEqual(
            merged.data.index.tolist(),
            [0.0, 1_000.0, 2_000.0, 3_000.0],
        )
        self.assertEqual(
            merged.data["traffic_signal_count_per_km"].tolist(),
            [2.0, 4.0, 4.0, 4.0],
        )
        self.assertEqual(
            merged.data["toilet_count_per_km"].tolist(),
            [0.0, 0.0, 1.0, 1.0],
        )

    def test_metric_uses_temporarily_mapped_route_feature(self) -> None:
        from fit_overlay.config import MetricOverlayConfig
        from fit_overlay.frames import MetricFrameMaker
        from fit_overlay.overlay_factory import OverlayFactory

        factory = OverlayFactory(route_features=self.profile)
        config = MetricOverlayConfig(
            id="signals",
            type="metric",
            x=0,
            y=0,
            width=200,
            height=60,
            refresh_rate_hz=1.0,
            column="traffic_signal_count_per_km",
        )

        frame_maker = factory.create(config, self.fit_data)

        self.assertIsInstance(frame_maker, MetricFrameMaker)
        self.assertIn("traffic_signal_count_per_km", frame_maker.data.columns)
        self.assertNotIn("traffic_signal_count_per_km", self.fit_data.columns)

    def test_graph_uses_full_route_profile_and_fit_for_current_position(self) -> None:
        from fit_overlay.config import GraphOverlayConfig
        from fit_overlay.frames import MatplotlibStripGraphFrameMaker
        from fit_overlay.overlay_factory import OverlayFactory

        factory = OverlayFactory(route_features=self.profile)
        config = GraphOverlayConfig(
            id="signals",
            type="graph",
            x=0,
            y=0,
            width=320,
            height=120,
            refresh_rate_hz=1.0,
            engine="matplotlib_strip",
            viewport_mode="overview",
            x_column="route_progress_m",
            x_multiplier=0.001,
            column="traffic_signal_count_per_km",
            line_draw_style="steps-post",
            poi_position="bottom",
        )

        frame_maker = factory.create(config, self.fit_data)

        self.assertIsInstance(frame_maker, MatplotlibStripGraphFrameMaker)
        self.assertEqual(frame_maker.poi_position, "bottom")
        self.assertEqual(frame_maker._explicit_x_domain, (0.0, 3.0))
        self.assertEqual(len(frame_maker.graph_series), 1)
        series = frame_maker.graph_series[0]
        self.assertEqual(series.source, "route_feature")
        np.testing.assert_array_equal(series.x_values, [0.0, 1_000.0, 3_000.0])
        np.testing.assert_array_equal(series.y_values, [2.0, 4.0, 4.0])
        self.assertEqual(series.reveal, "all")


if __name__ == "__main__":
    unittest.main()
