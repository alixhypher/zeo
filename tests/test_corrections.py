"""Tests for the time-correction rules."""

import unittest

from zeo2oscar import corrections
from zeo2oscar.corrections import END, RISE, START


class CorrectTimeTests(unittest.TestCase):
    def correct(self, value, field):
        return corrections.correct_zeo_time(value, field)

    def test_ground_truth_start_of_night(self):
        # From zeosleep_corrected.csv: 05/31/2026 06:50 -> 23:50 (+5h +12h).
        self.assertEqual(
            self.correct("05/31/2026 06:50", START), "05/31/2026 23:50"
        )

    def test_ground_truth_end_of_night(self):
        # End of night gets +5h only: 06/01/2026 03:48 -> 08:48.
        self.assertEqual(
            self.correct("06/01/2026 03:48", END), "06/01/2026 08:48"
        )

    def test_ground_truth_rise_time(self):
        self.assertEqual(
            self.correct("06/01/2026 03:50", RISE), "06/01/2026 08:50"
        )

    def test_start_rolls_to_next_day_when_needed(self):
        # 07:00 + 5h = 12:00, + 12h = 24:00 -> 00:00 next day.
        self.assertEqual(
            self.correct("05/23/2026 07:00", START), "05/24/2026 00:00"
        )

    def test_start_pm_fixup_crossing_midnight(self):
        # 09:30 + 5h = 14:30 (<18 -> +12h) = 02:30 next day.
        self.assertEqual(
            self.correct("05/24/2020 09:30", START), "05/25/2020 02:30"
        )

    def test_end_no_pm_fixup(self):
        self.assertEqual(
            self.correct("05/25/2020 04:38", END), "05/25/2020 09:38"
        )

    def test_late_start_not_double_shifted(self):
        # Already an evening time after +5h (>=18) must not get another +12h.
        # 14:00 + 5h = 19:00 (>=18) -> stays 19:00.
        self.assertEqual(
            self.correct("05/01/2026 14:00", START), "05/01/2026 19:00"
        )

    def test_blank_values_stay_blank(self):
        self.assertEqual(self.correct("", RISE), "")
        self.assertEqual(self.correct("   ", START), "")
        self.assertEqual(self.correct(None, END), "")

    def test_unknown_field_raises(self):
        with self.assertRaises(ValueError):
            corrections.correct_datetime(
                corrections.parse_zeo_datetime("05/31/2026 06:50"), "nope"
            )

    def test_parse_roundtrip(self):
        dt = corrections.parse_zeo_datetime("12/01/2026 23:59")
        self.assertEqual(corrections.format_zeo_datetime(dt), "12/01/2026 23:59")

    def test_bad_format_raises(self):
        with self.assertRaises(ValueError):
            corrections.parse_zeo_datetime("2026-12-01 23:59")


if __name__ == "__main__":
    unittest.main()
