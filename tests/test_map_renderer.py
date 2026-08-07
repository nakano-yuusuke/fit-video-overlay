from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from fit_overlay.map_geometry import MapGeometry
from fit_overlay.map_renderer import CachedOsmTiles, StaticMapRenderer


class CachedOsmTilesTest(unittest.TestCase):
    def test_download_failure_retries_then_raises(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tiles = CachedOsmTiles(Path(directory))

            with patch(
                "fit_overlay.map_renderer.urlopen",
                side_effect=URLError("offline"),
            ) as urlopen_mock, patch("fit_overlay.map_renderer.sleep") as sleep_mock:
                with self.assertRaisesRegex(
                    RuntimeError,
                    "OSMタイルを4回取得できませんでした",
                ):
                    tiles.get_image((0, 0, 0))

            self.assertEqual(urlopen_mock.call_count, 4)
            self.assertEqual(
                [call.args[0] for call in sleep_mock.call_args_list],
                [1.0, 2.0, 4.0],
            )
            self.assertEqual(list(Path(directory).glob("*.png")), [])

    def test_limits_parallel_tile_requests(self) -> None:
        self.assertEqual(CachedOsmTiles._MAX_THREADS, 2)

    def test_renderer_reports_tile_error_when_all_downloads_fail(self) -> None:
        geometry = MapGeometry(
            bbox=(139.0, 139.01, 35.0, 35.01),
            center_lon=139.005,
            center_lat=35.005,
            half_width_m=500.0,
            half_height_m=500.0,
            lon_m_per_deg=91_000.0,
            lat_m_per_deg=110_540.0,
            width_px=32,
            height_px=32,
            pixels_per_meter=0.032,
        )
        with tempfile.TemporaryDirectory() as directory:
            renderer = StaticMapRenderer(
                Path(directory),
                dpi=100,
                zoom=0,
            )

            with patch(
                "fit_overlay.map_renderer.urlopen",
                side_effect=URLError("offline"),
            ), patch("fit_overlay.map_renderer.sleep"):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "OSMタイルを4回取得できませんでした",
                ):
                    renderer.render(geometry)
