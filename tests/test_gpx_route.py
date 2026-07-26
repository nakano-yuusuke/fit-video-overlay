from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from fit_overlay.gpx_route import GpxRoute, RouteProgressMatcher


class RouteProgressMatcherTest(unittest.TestCase):
    def test_closed_route_starts_near_zero_when_end_is_slightly_closer(self) -> None:
        route = GpxRoute.from_points(
            latitudes=np.asarray([0.0, 0.0, 0.001, 0.001, 0.00001]),
            longitudes=np.asarray([0.0, 0.001, 0.001, 0.0, 0.0]),
        )
        data = pd.DataFrame(
            {
                "position_lat": [0.000009, 0.0, 0.0],
                "position_long": [0.0, 0.00025, 0.0005],
            },
            index=pd.date_range("2024-01-01", periods=3, freq="s", tz="UTC"),
        )

        progress = RouteProgressMatcher(
            route,
            off_route_threshold_m=20.0,
            search_ahead_m=5000.0,
            search_behind_m=300.0,
        ).match(data)

        self.assertLess(progress.iloc[0], 2.0)
        self.assertGreater(progress.iloc[1], progress.iloc[0])
        self.assertGreater(progress.iloc[2], progress.iloc[1])

    def test_activity_starting_mid_route_uses_nearest_progress(self) -> None:
        route = GpxRoute.from_points(
            latitudes=np.asarray([0.0, 0.0]),
            longitudes=np.asarray([0.0, 0.01]),
        )
        data = pd.DataFrame(
            {
                "position_lat": [0.0],
                "position_long": [0.005],
            },
            index=pd.date_range("2024-01-01", periods=1, freq="s", tz="UTC"),
        )

        progress = RouteProgressMatcher(
            route,
            off_route_threshold_m=20.0,
            search_ahead_m=5000.0,
            search_behind_m=300.0,
        ).match(data)

        self.assertAlmostEqual(progress.iloc[0], route.total_distance_m / 2)
