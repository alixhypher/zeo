import csv
import tempfile
import unittest
from pathlib import Path

from zeo_oscar import correct_row, correct_time, load_records, write_output


class ZeoOscarTests(unittest.TestCase):
    def test_corrects_start_pm_before_offset(self):
        corrected, notes = correct_time("05/31/2026 06:50", column="Start of Night")
        self.assertEqual(corrected, "05/31/2026 23:50")
        self.assertEqual(notes, ["start +12h", "+5h"])

    def test_corrects_end_and_rise_by_offset_only(self):
        self.assertEqual(correct_time("06/01/2026 03:48", column="End of Night")[0], "06/01/2026 08:48")
        self.assertEqual(correct_time("06/01/2026 03:50", column="Rise Time")[0], "06/01/2026 08:50")

    def test_blank_times_stay_blank(self):
        corrected, notes = correct_time("", column="Rise Time")
        self.assertEqual(corrected, "")
        self.assertEqual(notes, [])

    def test_write_output_uses_overrides_and_selection(self):
        row = {
            "Sleep Date": "05/31/2026",
            "ZQ": "55",
            "Start of Night": "05/31/2026 06:50",
            "End of Night": "06/01/2026 03:48",
            "Rise Time": "06/01/2026 03:50",
        }
        record = correct_row(row)
        record.corrected_times["Rise Time"] = "06/01/2026 09:00"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.csv"
            count = write_output(output, list(row), [record])
            with output.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
        self.assertEqual(count, 1)
        self.assertEqual(rows[0]["Start of Night"], "05/31/2026 23:50")
        self.assertEqual(rows[0]["Rise Time"], "06/01/2026 09:00")

    def test_load_records_from_existing_csv(self):
        fieldnames, records = load_records(csv_path="zeosleep.csv")
        self.assertIn("Sleep Date", fieldnames)
        self.assertGreaterEqual(len(records), 1)


if __name__ == "__main__":
    unittest.main()
