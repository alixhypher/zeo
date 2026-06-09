"""Tests for the chronology validation checks."""

import unittest

from zeo2oscar.records import COL_START, Night
from zeo2oscar.validation import has_warnings, validate_night

from tests.test_records import make_row


class ValidationTests(unittest.TestCase):
    def test_clean_night_has_no_warnings(self):
        night = Night(raw=make_row())
        self.assertEqual(validate_night(night), [])
        self.assertFalse(has_warnings(night))

    def test_missing_start_flagged(self):
        night = Night(raw=make_row(start=""))
        self.assertIn("missing Start of Night", validate_night(night))

    def test_start_after_end_flagged(self):
        # Override the corrected start to after the corrected end.
        night = Night(raw=make_row())
        night.set_override(COL_START, "06/02/2026 10:00")  # after end 06/01 08:48
        self.assertIn(
            "Start of Night is not before End of Night", validate_night(night)
        )

    def test_missing_rise_is_allowed(self):
        # Rise is optional; absence alone is not a warning.
        night = Night(raw=make_row(rise=""))
        self.assertEqual(validate_night(night), [])

    def test_rise_near_end_is_not_flagged(self):
        # Source data legitimately records Rise a few minutes before End.
        night = Night(raw=make_row(end="06/01/2026 04:03", rise="06/01/2026 04:00"))
        self.assertEqual(validate_night(night), [])


if __name__ == "__main__":
    unittest.main()
