from __future__ import annotations

import unittest

from fit_overlay.media_canvas import contain_geometry


class ContainGeometryTest(unittest.TestCase):
    def test_matching_4k_source_is_unchanged(self) -> None:
        geometry = contain_geometry(3840, 2160, 3840, 2160)

        self.assertEqual(
            (geometry.content_width, geometry.content_height),
            (3840, 2160),
        )
        self.assertEqual((geometry.offset_x, geometry.offset_y), (0, 0))
        self.assertFalse(geometry.needs_resize)
        self.assertFalse(geometry.needs_padding)

    def test_1080p_source_fills_4k_canvas(self) -> None:
        geometry = contain_geometry(1920, 1080, 3840, 2160)

        self.assertEqual(
            (geometry.content_width, geometry.content_height),
            (3840, 2160),
        )
        self.assertEqual((geometry.offset_x, geometry.offset_y), (0, 0))
        self.assertTrue(geometry.needs_resize)
        self.assertFalse(geometry.needs_padding)

    def test_four_by_three_source_gets_horizontal_padding(self) -> None:
        geometry = contain_geometry(2688, 2016, 3840, 2160)

        self.assertEqual(
            (geometry.content_width, geometry.content_height),
            (2880, 2160),
        )
        self.assertEqual((geometry.offset_x, geometry.offset_y), (480, 0))
        self.assertTrue(geometry.needs_resize)
        self.assertTrue(geometry.needs_padding)

    def test_wide_source_gets_vertical_padding(self) -> None:
        geometry = contain_geometry(3840, 1080, 3840, 2160)

        self.assertEqual(
            (geometry.content_width, geometry.content_height),
            (3840, 1080),
        )
        self.assertEqual((geometry.offset_x, geometry.offset_y), (0, 540))
        self.assertFalse(geometry.needs_resize)
        self.assertTrue(geometry.needs_padding)

    def test_rejects_non_positive_dimensions(self) -> None:
        with self.assertRaises(ValueError):
            contain_geometry(0, 1080, 3840, 2160)


if __name__ == "__main__":
    unittest.main()
