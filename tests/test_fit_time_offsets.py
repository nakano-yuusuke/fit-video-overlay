from __future__ import annotations

import datetime
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from fit_overlay.config import FitTimeOffsetConfig, load_processor_config
from fit_overlay.data import load_fit_data


class FitTimeOffsetConfigTest(unittest.TestCase):
    def _load(self, processing: object):
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
                        "processing": processing,
                        "overlays": [],
                    }
                ),
                encoding="utf-8",
            )
            return load_processor_config(config_path)

    def test_parses_and_sorts_timezone_aware_rules(self) -> None:
        config = self._load(
            {
                "fit_time_offset_seconds": 5,
                "fit_time_offsets": [
                    {
                        "from": "2024-09-29T01:00:00+09:00",
                        "offset_seconds": 120,
                    },
                    {
                        "from": "2024-09-28T12:00:00Z",
                        "offset_seconds": 60,
                    },
                ],
            }
        )

        self.assertEqual(config.fit_time_offset_seconds, 5)
        self.assertEqual(
            [item.from_timestamp for item in config.fit_time_offsets],
            [
                datetime.datetime(2024, 9, 28, 12, tzinfo=datetime.timezone.utc),
                datetime.datetime(2024, 9, 28, 16, tzinfo=datetime.timezone.utc),
            ],
        )
        self.assertEqual(
            [item.offset_seconds for item in config.fit_time_offsets],
            [60, 120],
        )

    def test_rejects_rule_without_timezone(self) -> None:
        with self.assertRaisesRegex(ValueError, "タイムゾーン"):
            self._load(
                {
                    "fit_time_offsets": [
                        {
                            "from": "2024-09-28T13:24:23",
                            "offset_seconds": 10493,
                        }
                    ]
                }
            )

    def test_rejects_duplicate_instants(self) -> None:
        with self.assertRaisesRegex(ValueError, "重複"):
            self._load(
                {
                    "fit_time_offsets": [
                        {"from": "2024-09-28T13:00:00Z", "offset_seconds": 1},
                        {
                            "from": "2024-09-28T22:00:00+09:00",
                            "offset_seconds": 2,
                        },
                    ]
                }
            )


class LoadFitDataTimeOffsetTest(unittest.TestCase):
    def test_rules_override_global_offset_from_raw_fit_timestamps(self) -> None:
        source = pd.DataFrame(
            {
                "timestamp": pd.date_range(
                    "2024-09-28T12:00:00Z", periods=4, freq="min"
                ),
                "marker": [0, 1, 2, 3],
            }
        )
        rules = (
            FitTimeOffsetConfig(
                from_timestamp=datetime.datetime(
                    2024, 9, 28, 12, 2, tzinfo=datetime.timezone.utc
                ),
                offset_seconds=120,
            ),
            FitTimeOffsetConfig(
                from_timestamp=datetime.datetime(
                    2024, 9, 28, 12, 3, tzinfo=datetime.timezone.utc
                ),
                offset_seconds=180,
            ),
        )

        with patch("fit_overlay.data.fit2df", return_value=source):
            result = load_fit_data(
                Path("activity.fit"),
                time_offset=pd.Timedelta(seconds=5),
                time_offsets=rules,
                max_duration=None,
            )

        self.assertEqual(
            list(result.index),
            list(
                pd.to_datetime(
                    [
                        "2024-09-28T12:00:05Z",
                        "2024-09-28T12:01:05Z",
                        "2024-09-28T12:04:00Z",
                        "2024-09-28T12:06:00Z",
                    ],
                    utc=True,
                )
            ),
        )
        self.assertEqual(result["marker"].tolist(), [0, 1, 2, 3])

    def test_backward_step_prefers_post_rule_record_at_duplicate_time(self) -> None:
        source = pd.DataFrame(
            {
                "timestamp": pd.date_range(
                    "2024-09-28T12:00:00Z", periods=4, freq="s"
                ),
                "marker": [0, 1, 2, 3],
            }
        )
        rules = (
            FitTimeOffsetConfig(
                from_timestamp=datetime.datetime(
                    2024, 9, 28, 12, 0, 2, tzinfo=datetime.timezone.utc
                ),
                offset_seconds=-1,
            ),
        )

        with patch("fit_overlay.data.fit2df", return_value=source):
            result = load_fit_data(
                Path("activity.fit"),
                time_offsets=rules,
                max_duration=None,
            )

        self.assertTrue(result.index.is_unique)
        self.assertEqual(
            list(result.index),
            list(
                pd.to_datetime(
                    [
                        "2024-09-28T12:00:00Z",
                        "2024-09-28T12:00:01Z",
                        "2024-09-28T12:00:02Z",
                    ],
                    utc=True,
                )
            ),
        )
        self.assertEqual(result["marker"].tolist(), [0, 2, 3])

    def test_global_offset_remains_backward_compatible(self) -> None:
        source = pd.DataFrame(
            {
                "timestamp": [pd.Timestamp("2024-09-28T12:00:00Z")],
                "marker": [1],
            }
        )

        with patch("fit_overlay.data.fit2df", return_value=source):
            result = load_fit_data(
                Path("activity.fit"),
                time_offset=pd.Timedelta(seconds=30),
                max_duration=None,
            )

        self.assertEqual(result.index[0], pd.Timestamp("2024-09-28T12:00:30Z"))


if __name__ == "__main__":
    unittest.main()
