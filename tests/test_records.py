"""Tests for the Night / NightCollection model and CSV export."""

import csv
import os
import tempfile
import unittest

from zeo2oscar.records import (
    COL_END,
    COL_RISE,
    COL_START,
    Night,
    NightCollection,
)

FIELDNAMES = ["Sleep Date", "ZQ", "Total Z", "Start of Night", "End of Night", "Rise Time"]


def make_row(date="05/31/2026", zq="55", start="05/31/2026 06:50",
             end="06/01/2026 03:48", rise="06/01/2026 03:50"):
    return {
        "Sleep Date": date,
        "ZQ": zq,
        "Total Z": "339",
        "Start of Night": start,
        "End of Night": end,
        "Rise Time": rise,
    }


class NightTests(unittest.TestCase):
    def test_default_correction_applied(self):
        night = Night(raw=make_row())
        self.assertEqual(night.original(COL_START), "05/31/2026 06:50")
        self.assertEqual(night.corrected(COL_START), "05/31/2026 23:50")
        self.assertEqual(night.corrected(COL_END), "06/01/2026 08:48")
        self.assertEqual(night.corrected(COL_RISE), "06/01/2026 08:50")

    def test_override_takes_precedence(self):
        night = Night(raw=make_row())
        night.set_override(COL_START, "05/31/2026 22:30")
        self.assertTrue(night.is_overridden(COL_START))
        self.assertEqual(night.corrected(COL_START), "05/31/2026 22:30")

    def test_clearing_override_restores_default(self):
        night = Night(raw=make_row())
        night.set_override(COL_START, "05/31/2026 22:30")
        night.set_override(COL_START, "")
        self.assertFalse(night.is_overridden(COL_START))
        self.assertEqual(night.corrected(COL_START), "05/31/2026 23:50")

    def test_invalid_override_rejected(self):
        night = Night(raw=make_row())
        with self.assertRaises(ValueError):
            night.set_override(COL_START, "not a time")

    def test_output_row_has_corrected_times(self):
        night = Night(raw=make_row())
        out = night.to_output_row()
        self.assertEqual(out["Start of Night"], "05/31/2026 23:50")
        self.assertEqual(out["End of Night"], "06/01/2026 08:48")
        # Untouched columns are preserved.
        self.assertEqual(out["ZQ"], "55")

    def test_empty_rise_stays_empty(self):
        night = Night(raw=make_row(rise=""))
        self.assertEqual(night.corrected(COL_RISE), "")
        self.assertEqual(night.to_output_row()["Rise Time"], "")


class CollectionTests(unittest.TestCase):
    def test_select_all_and_selected(self):
        coll = NightCollection.from_rows(
            FIELDNAMES, [make_row(date="05/30/2026"), make_row(date="05/31/2026")]
        )
        self.assertEqual(coll.selected, [])
        coll.select_all(True)
        self.assertEqual(len(coll.selected), 2)

    def test_write_output_only_selected(self):
        coll = NightCollection.from_rows(
            FIELDNAMES, [make_row(date="05/30/2026"), make_row(date="05/31/2026")]
        )
        coll.nights[1].selected = True
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.csv")
            count = coll.write_output(path, only_selected=True)
            self.assertEqual(count, 1)
            with open(path, newline="") as handle:
                rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Sleep Date"], "05/31/2026")
        self.assertEqual(rows[0]["Start of Night"], "05/31/2026 23:50")


if __name__ == "__main__":
    unittest.main()
