from __future__ import annotations

import datetime
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

from fit2csv import fit2df_with_correlations
from fit_overlay.config import FitTimeOffsetConfig, load_processor_config
from fit_overlay.data import load_fit_data
from fit_overlay.timestamp_correlation import correct_fit_timestamps


class TimestampCorrelationConfigTest(unittest.TestCase):
    def _load(self, processing):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps({
                    "input": {
                        "mp4_dir": "media", "fit_path": "activity.fit",
                        "output_dir": "output",
                    },
                    "processing": processing,
                    "overlays": [],
                }),
                encoding="utf-8",
            )
            return load_processor_config(path)

    def test_defaults_to_disabled_and_accepts_boolean_switch(self):
        self.assertFalse(self._load({}).fit_timestamp_correlation.enabled)
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                config = self._load({"fit_timestamp_correlation": {"enabled": enabled}})
                self.assertEqual(config.fit_timestamp_correlation.enabled, enabled)

    def test_rejects_ambiguous_or_unknown_settings(self):
        for raw in (True, [], {"enabled": "false"}, {"enabled": 1},
                    {"reference": "first"}, {"scale": 0.5}):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self._load({"fit_timestamp_correlation": raw})


class TimestampCorrelationTest(unittest.TestCase):
    origin = pd.Timestamp("2024-11-15T20:00:00Z")

    def _times(self, seconds):
        return pd.DatetimeIndex(self.origin + pd.to_timedelta(seconds, unit="s"))

    def _samples(self, utc_seconds, system_seconds):
        return pd.DataFrame({
            "timestamp": self._times(utc_seconds),
            "system_timestamp": self._times(system_seconds),
        })

    def test_subtracts_full_initial_difference_and_interpolates(self):
        # UTC 00:00 / 00:10 maps to system 59:50 / 59:56 (delta 10 / 14).
        # Even the first record must move back ten seconds.
        samples = self._samples([0, 10], [-10, -4])
        result = correct_fit_timestamps(self._times([-5, 0, 5, 10, 15]), samples)
        pd.testing.assert_index_equal(result, self._times([-15, -10, -7, -4, 1]))

    def test_negative_delta_and_single_sample_hold_constant_difference(self):
        samples = self._samples([0], [3])
        result = correct_fit_timestamps(self._times([-10, 0, 10]), samples)
        pd.testing.assert_index_equal(result, self._times([-7, 3, 13]))

    def test_sorts_samples_without_reordering_records_and_accepts_identical_duplicates(self):
        samples = self._samples([10, 0, 10], [6, -2, 6])
        result = correct_fit_timestamps(self._times([10, 0, 5]), samples)
        pd.testing.assert_index_equal(result, self._times([6, -2, 2]))

    def test_millisecond_and_fractional_fields_have_correct_units(self):
        samples = self._samples([0, 10], [-10, 0])
        samples["timestamp_ms"] = [250, np.nan]
        samples["fractional_timestamp"] = [0.75, 0.5]
        samples["system_timestamp_ms"] = [750, np.nan]
        samples["fractional_system_timestamp"] = [0.25, 0.25]
        # Milliseconds take precedence over the fractional-seconds alternative.
        result = correct_fit_timestamps(self._times([0.25, 5.375, 10.5]), samples)
        pd.testing.assert_index_equal(result, self._times([-9.25, -4.5, 0.25]))

    def test_missing_or_all_invalid_correlations_fail_explicitly(self):
        for samples in (
            pd.DataFrame(),
            pd.DataFrame({"timestamp": self._times([0])}),
            pd.DataFrame({"timestamp": [None], "system_timestamp": [None]}),
            pd.DataFrame({"timestamp": ["invalid"], "system_timestamp": ["invalid"]}),
        ):
            with self.subTest(samples=samples), self.assertRaisesRegex(
                ValueError, "有効なtimestamp_correlation"
            ):
                correct_fit_timestamps(self._times([0]), samples)

    def test_ignores_incomplete_messages_with_a_warning(self):
        samples = self._samples([0, 10], [-3, 7])
        samples.loc[0, "system_timestamp"] = pd.NaT
        with self.assertLogs("fit_overlay.timestamp_correlation", level="WARNING"):
            result = correct_fit_timestamps(self._times([0, 5, 10]), samples)
        pd.testing.assert_index_equal(result, self._times([-3, 2, 7]))

    def test_conflicting_system_times_for_same_utc_fail(self):
        with self.assertRaisesRegex(ValueError, "同じUTC時刻"):
            correct_fit_timestamps(self._times([0]), self._samples([0, 0], [-1, -2]))

    def test_load_fit_applies_manual_rules_using_raw_timestamp(self):
        source = pd.DataFrame({
            "timestamp": self._times([0, 5, 10]), "marker": [0, 1, 2],
        })
        samples = self._samples([0, 10], [-10, -4])
        rules = (FitTimeOffsetConfig(
            from_timestamp=(self.origin + pd.Timedelta(seconds=5)).to_pydatetime(),
            offset_seconds=20,
        ),)
        with patch("fit_overlay.data.fit2df_with_correlations", return_value=(source, samples)):
            result = load_fit_data(
                Path("activity.fit"), timestamp_correlation_enabled=True,
                time_offset=pd.Timedelta(seconds=2), time_offsets=rules,
                max_duration=None,
            )
        pd.testing.assert_index_equal(result.index, self._times([-8, 13, 16]).rename("timestamp"))
        self.assertEqual(result.marker.tolist(), [0, 1, 2])

    def test_disabled_mode_does_not_load_correlations(self):
        source = pd.DataFrame({"timestamp": self._times([0, 10]), "marker": [1, 2]})
        with patch("fit_overlay.data.fit2df", return_value=source), patch(
            "fit_overlay.data.fit2df_with_correlations"
        ) as correlation_reader:
            result = load_fit_data(Path("activity.fit"), max_duration=None)
        correlation_reader.assert_not_called()
        pd.testing.assert_index_equal(result.index, self._times([0, 10]).rename("timestamp"))

    def test_collapsed_timestamps_keep_later_record_and_log_count(self):
        source = pd.DataFrame({"timestamp": self._times([0, 1, 2]), "marker": [0, 1, 2]})
        samples = self._samples([0, 1, 2], [0, 0, 1])
        with patch("fit_overlay.data.fit2df_with_correlations", return_value=(source, samples)):
            with self.assertLogs("fit_overlay.data", level="WARNING") as logs:
                result = load_fit_data(
                    Path("activity.fit"), timestamp_correlation_enabled=True, max_duration=None
                )
        pd.testing.assert_index_equal(result.index, self._times([0, 1]).rename("timestamp"))
        self.assertEqual(result.marker.tolist(), [1, 2])
        self.assertIn("duplicate_corrected_timestamps=1", " ".join(logs.output))

    def test_duration_limit_uses_corrected_times(self):
        source = pd.DataFrame({"timestamp": self._times([0, 10, 20]), "marker": [0, 1, 2]})
        samples = self._samples([0, 20], [-10, 5])
        with patch("fit_overlay.data.fit2df_with_correlations", return_value=(source, samples)):
            result = load_fit_data(
                Path("activity.fit"), timestamp_correlation_enabled=True,
                max_duration=pd.Timedelta(seconds=10),
            )
        self.assertEqual(result.marker.tolist(), [0, 1])


class FitCorrelationReaderTest(unittest.TestCase):
    def test_reads_both_message_types_once_and_preserves_source_times(self):
        utc = datetime.datetime(2024, 11, 15, 20, 0, 0)
        system = utc - datetime.timedelta(seconds=10)
        messages = []
        for name, values in (
            ("timestamp_correlation", {"timestamp": utc, "system_timestamp": system}),
            ("event", {"timestamp": utc}),
            ("record", {"timestamp": utc, "position_lat": 2**30, "position_long": 2**29}),
        ):
            message = Mock()
            message.name = name
            message.get_values.return_value = values
            messages.append(message)
        with patch("fit2csv.FitFile") as fit_class:
            fit_class.return_value.get_messages.return_value = iter(messages)
            records, correlations = fit2df_with_correlations("activity.fit")
        fit_class.assert_called_once_with("activity.fit")
        fit_class.return_value.get_messages.assert_called_once_with()
        self.assertEqual(len(records), 1)
        self.assertEqual(len(correlations), 1)
        self.assertEqual(records.timestamp.iloc[0], utc)
        self.assertEqual(records.position_lat.iloc[0], 90)
        self.assertEqual(records.position_long.iloc[0], 45)
        self.assertEqual(correlations.system_timestamp.iloc[0], system)


if __name__ == "__main__":
    unittest.main()
