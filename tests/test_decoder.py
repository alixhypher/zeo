"""Tests for decoding and parsing, including an end-to-end check vs the
hand-corrected reference file when Java is available."""

import os
import shutil
import unittest

from zeo2oscar import decoder
from zeo2oscar.decoder import DecoderError
from zeo2oscar.records import COL_START, COL_END, COL_RISE, NightCollection

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAT = os.path.join(REPO_ROOT, "ZEOSLEEP.DAT")
JAR = os.path.join(REPO_ROOT, "ZeoDataDecoder.jar")
RAW_CSV = os.path.join(REPO_ROOT, "zeosleep.csv")
CORRECTED_CSV = os.path.join(REPO_ROOT, "zeosleep_corrected.csv")

HAVE_JAVA = shutil.which("java") is not None


class ParseTests(unittest.TestCase):
    def test_parse_csv_text(self):
        text = "A,B,C\n1,2,3\n4,5,6\n"
        fields, rows = decoder.parse_csv_text(text)
        self.assertEqual(fields, ["A", "B", "C"])
        self.assertEqual(rows, [
            {"A": "1", "B": "2", "C": "3"},
            {"A": "4", "B": "5", "C": "6"},
        ])

    def test_parse_pads_short_rows(self):
        fields, rows = decoder.parse_csv_text("A,B,C\n1,2\n")
        self.assertEqual(rows[0], {"A": "1", "B": "2", "C": ""})

    def test_parse_empty_raises(self):
        with self.assertRaises(DecoderError):
            decoder.parse_csv_text("\n\n")

    def test_missing_csv_file(self):
        with self.assertRaises(DecoderError):
            decoder.load_csv_file("/no/such/file.csv")


class CsvFixtureTests(unittest.TestCase):
    @unittest.skipUnless(os.path.isfile(RAW_CSV), "zeosleep.csv missing")
    def test_load_repo_csv(self):
        fields, rows = decoder.load_csv_file(RAW_CSV)
        self.assertIn("Start of Night", fields)
        self.assertTrue(rows)


@unittest.skipUnless(
    HAVE_JAVA and os.path.isfile(DAT) and os.path.isfile(JAR),
    "Java and decoder artefacts required",
)
class EndToEndTests(unittest.TestCase):
    """Decode the real .DAT and confirm corrections reproduce the reference."""

    def test_decode_matches_committed_raw(self):
        # The pinned-timezone decode must reproduce the committed zeosleep.csv.
        with open(RAW_CSV, encoding="utf-8") as handle:
            expected = handle.read().strip()
        actual = decoder.decode_dat(DAT, JAR).strip()
        self.assertEqual(actual, expected)

    def test_corrected_output_matches_reference_row(self):
        fields, rows = decoder.load_from_dat(DAT, JAR)
        coll = NightCollection.from_rows(fields, rows)
        night = next(n for n in coll.nights if n.sleep_date == "05/31/2026")
        self.assertEqual(night.corrected(COL_START), "05/31/2026 23:50")
        self.assertEqual(night.corrected(COL_END), "06/01/2026 08:48")
        self.assertEqual(night.corrected(COL_RISE), "06/01/2026 08:50")


if __name__ == "__main__":
    unittest.main()
