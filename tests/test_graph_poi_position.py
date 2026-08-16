from __future__ import annotations

import unittest

import pandas as pd

from fit_overlay.frames import MatplotlibStripGraphFrameMaker


class GraphPoiPositionTest(unittest.TestCase):
    def _frame_maker(self, poi_position: str) -> MatplotlibStripGraphFrameMaker:
        data = pd.DataFrame(
            {"value": [0.0]},
            index=pd.DatetimeIndex(["2024-01-01T00:00:00Z"]),
        )
        return MatplotlibStripGraphFrameMaker(
            1.0,
            data,
            "value",
            str,
            width=200,
            height=100,
            padding=(10, 10, 10, 20),
            poi_position=poi_position,
            poi_font_size=20,
        )

    def test_top_positions_marker_and_label_from_plot_top(self) -> None:
        frame_maker = self._frame_maker("top")
        _, plot_top, _, plot_bottom = frame_maker._plot_bounds

        self.assertEqual(frame_maker._poi_marker_y(plot_top, plot_bottom), 16)
        self.assertEqual(frame_maker._poi_label_y(0, plot_top, plot_bottom), 33)
        self.assertEqual(frame_maker._poi_label_y(1, plot_top, plot_bottom), 57)

    def test_bottom_positions_marker_and_label_from_plot_bottom(self) -> None:
        frame_maker = self._frame_maker("bottom")
        _, plot_top, _, plot_bottom = frame_maker._plot_bounds

        self.assertEqual(frame_maker._poi_marker_y(plot_top, plot_bottom), 73)
        self.assertEqual(frame_maker._poi_label_y(0, plot_top, plot_bottom), 76)
        self.assertEqual(frame_maker._poi_label_y(1, plot_top, plot_bottom), 52)


if __name__ == "__main__":
    unittest.main()
