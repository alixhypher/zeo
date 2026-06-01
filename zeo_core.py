"""Core logic for decoding Zeo .DAT files and correcting their timestamps.

This module is intentionally GUI-free so it can be unit tested and reused.

The ZeoDataDecoder.jar produces a CSV whose ``Start of Night``, ``End of Night``
and ``Rise Time`` columns have two known problems (see README.txt):

1. Every one of those three timestamps is offset by 5 hours and needs +5h.
2. Timestamps that fall before midnight (usually just the start of night) are
   emitted without 24-hour/PM notation and need an additional +12h.

A timestamp is treated as "before midnight" when its calendar date is earlier
than the End of Night date for that record (i.e. you went to bed in the evening
and woke up the next morning). This reproduces the manually-corrected example in
zeosleep_corrected.csv, e.g. ``05/31/2026 06:50`` -> ``05/31/2026 23:50``.
"""

from __future__ import annotations

import csv
import io
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

# Column headers (exactly as emitted by ZeoDataDecoder.jar).
SLEEP_DATE_COL = "Sleep Date"
START_COL = "Start of Night"
END_COL = "End of Night"
RISE_COL = "Rise Time"
TIME_COLUMNS = (START_COL, END_COL, RISE_COL)

# Timestamp format used throughout the Zeo CSV, e.g. "05/31/2026 23:50".
TIME_FORMAT = "%m/%d/%Y %H:%M"

HOUR_OFFSET = timedelta(hours=5)
PRE_MIDNIGHT_OFFSET = timedelta(hours=12)


def decode_dat(
    dat_path: str,
    jar_path: str = "ZeoDataDecoder.jar",
    tz: Optional[str] = None,
) -> str:
    """Run ZeoDataDecoder.jar on ``dat_path`` and return the raw CSV text.

    The decoder renders timestamps in the JVM's local timezone, so its raw
    output depends on the host timezone. ``tz`` optionally forces a specific
    timezone (e.g. "Etc/GMT+5") for reproducible decoding; when None the host's
    environment is used, which on the user's own machine is the intended case.

    Raises FileNotFoundError if the inputs are missing and
    subprocess.CalledProcessError if the decoder exits non-zero.
    """
    if not os.path.isfile(dat_path):
        raise FileNotFoundError(f"Zeo data file not found: {dat_path}")
    if not os.path.isfile(jar_path):
        raise FileNotFoundError(f"Decoder jar not found: {jar_path}")

    env = None
    if tz is not None:
        env = dict(os.environ, TZ=tz)

    result = subprocess.run(
        ["java", "-jar", jar_path, dat_path],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.stdout


def parse_datetime(value: str) -> Optional[datetime]:
    """Parse a Zeo timestamp, returning None for blank/unparseable values."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, TIME_FORMAT)
    except ValueError:
        return None


def format_datetime(dt: datetime) -> str:
    """Format a datetime back into the Zeo CSV timestamp format."""
    return dt.strftime(TIME_FORMAT)


def correct_timestamp(value: str, reference: Optional[datetime]) -> str:
    """Return the corrected timestamp string for a single raw value.

    ``reference`` is the (raw) End of Night datetime for the record, used to
    decide whether ``value`` falls before midnight. Blank/unparseable values
    are returned unchanged.
    """
    dt = parse_datetime(value)
    if dt is None:
        return (value or "").strip()

    corrected = dt + HOUR_OFFSET
    if reference is not None and dt.date() < reference.date():
        corrected += PRE_MIDNIGHT_OFFSET
    return format_datetime(corrected)


@dataclass
class SleepRecord:
    """One night of sleep: the full original CSV row plus corrected times.

    ``corrected`` holds the auto-corrected (and possibly user-overridden) values
    for the three time columns. ``selected`` controls whether the record is
    written to the Oscar output file.
    """

    row: dict  # full original CSV row, header -> value
    corrected: dict = field(default_factory=dict)  # time column -> corrected str
    selected: bool = True

    @property
    def sleep_date(self) -> str:
        return self.row.get(SLEEP_DATE_COL, "")

    def original(self, column: str) -> str:
        return (self.row.get(column, "") or "").strip()

    def output_row(self) -> dict:
        """Return a copy of the original row with corrected times substituted."""
        out = dict(self.row)
        for col in TIME_COLUMNS:
            if col in out:
                out[col] = self.corrected.get(col, out[col])
        return out


def build_records(csv_text: str) -> tuple[list[str], list[SleepRecord]]:
    """Parse decoder CSV text into a header list and SleepRecord list."""
    reader = csv.DictReader(io.StringIO(csv_text))
    header = list(reader.fieldnames or [])
    records: list[SleepRecord] = []

    for row in reader:
        # Skip fully blank trailing rows.
        if not any((v or "").strip() for v in row.values()):
            continue
        reference = parse_datetime(row.get(END_COL, ""))
        corrected = {
            col: correct_timestamp(row.get(col, ""), reference) for col in TIME_COLUMNS
        }
        records.append(SleepRecord(row=row, corrected=corrected))

    return header, records


def load_csv_file(path: str) -> tuple[list[str], list[SleepRecord]]:
    """Build records from an existing CSV file on disk."""
    with open(path, newline="") as fh:
        return build_records(fh.read())


def decode_and_build(
    dat_path: str,
    jar_path: str = "ZeoDataDecoder.jar",
    tz: Optional[str] = None,
) -> tuple[list[str], list[SleepRecord]]:
    """Decode a .DAT file and build corrected records in one step."""
    return build_records(decode_dat(dat_path, jar_path, tz=tz))


def write_output(
    header: list[str], records: list[SleepRecord], path: str, selected_only: bool = True
) -> int:
    """Write (selected) records to ``path`` as a CSV. Returns rows written."""
    chosen = [r for r in records if r.selected] if selected_only else list(records)
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        for record in chosen:
            writer.writerow(record.output_row())
    return len(chosen)
