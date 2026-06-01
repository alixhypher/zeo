"""Tests for zeo_core, validated against the hand-corrected example file."""

import csv
import os
import tempfile

import zeo_core as zc

HERE = os.path.dirname(os.path.abspath(__file__))


def test_correct_timestamp_start_of_night_before_midnight():
    # Start of night falls on an earlier date than end of night -> +5h +12h.
    ref = zc.parse_datetime("06/01/2026 03:48")
    assert zc.correct_timestamp("05/31/2026 06:50", ref) == "05/31/2026 23:50"


def test_correct_timestamp_morning_times_plus_five():
    ref = zc.parse_datetime("06/01/2026 03:48")
    assert zc.correct_timestamp("06/01/2026 03:48", ref) == "06/01/2026 08:48"
    assert zc.correct_timestamp("06/01/2026 03:50", ref) == "06/01/2026 08:50"


def test_correct_timestamp_blank_passthrough():
    assert zc.correct_timestamp("", None) == ""
    assert zc.correct_timestamp("   ", None) == ""


def test_post_midnight_bedtime_only_plus_five():
    # If you went to bed after midnight, start date == end date -> no +12h.
    ref = zc.parse_datetime("06/01/2026 03:48")
    assert zc.correct_timestamp("06/01/2026 01:00", ref) == "06/01/2026 06:00"


def test_matches_hand_corrected_example():
    # Decode the real .DAT, correct it, and compare the 05/31/2026 record to
    # the manually corrected reference file.
    dat = os.path.join(HERE, "ZEOSLEEP.DAT")
    jar = os.path.join(HERE, "ZeoDataDecoder.jar")
    header, records = zc.decode_and_build(dat, jar, tz="Etc/GMT+5")

    target = next(r for r in records if r.sleep_date == "05/31/2026")

    with open(os.path.join(HERE, "zeosleep_corrected.csv"), newline="") as fh:
        expected = next(
            row
            for row in csv.DictReader(fh)
            if row[zc.SLEEP_DATE_COL] == "05/31/2026"
        )

    out = target.output_row()
    for col in zc.TIME_COLUMNS:
        assert out[col] == expected[col], f"{col}: {out[col]!r} != {expected[col]!r}"


def test_write_output_selected_only(tmp_path=None):
    dat = os.path.join(HERE, "ZEOSLEEP.DAT")
    jar = os.path.join(HERE, "ZeoDataDecoder.jar")
    header, records = zc.decode_and_build(dat, jar, tz="Etc/GMT+5")

    for r in records:
        r.selected = r.sleep_date == "05/31/2026"

    with tempfile.NamedTemporaryFile("r", suffix=".csv", delete=False) as tmp:
        path = tmp.name
    try:
        written = zc.write_output(header, records, path)
        assert written == 1
        with open(path, newline="") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 1
        assert rows[0][zc.SLEEP_DATE_COL] == "05/31/2026"
        assert rows[0][zc.START_COL] == "05/31/2026 23:50"
    finally:
        os.remove(path)


if __name__ == "__main__":
    import sys

    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc}")
    sys.exit(1 if failures else 0)
