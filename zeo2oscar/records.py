"""Data model tying decoded rows to their corrected times and user overrides."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import corrections

# Column names as emitted by ZeoDataDecoder.jar.
COL_SLEEP_DATE = "Sleep Date"
COL_START = "Start of Night"
COL_END = "End of Night"
COL_RISE = "Rise Time"
COL_ZQ = "ZQ"
COL_TOTAL_Z = "Total Z"

# Maps the time columns to their correction-rule field identifiers.
TIME_COLUMNS = {
    COL_START: corrections.START,
    COL_END: corrections.END,
    COL_RISE: corrections.RISE,
}


@dataclass
class Night:
    """One night's sleep record.

    ``raw`` holds the decoded row verbatim.  Corrected times are computed on
    demand from the correction rules; ``overrides`` lets the user replace any
    corrected time with their own value (the GUI requirement).  ``selected``
    controls whether the night is written to the output file.
    """

    raw: Dict[str, str]
    selected: bool = False
    overrides: Dict[str, str] = field(default_factory=dict)

    @property
    def sleep_date(self) -> str:
        return self.raw.get(COL_SLEEP_DATE, "").strip()

    @property
    def zq(self) -> str:
        return self.raw.get(COL_ZQ, "").strip()

    @property
    def total_z(self) -> str:
        return self.raw.get(COL_TOTAL_Z, "").strip()

    def original(self, column: str) -> str:
        """The decoder's original value for a time column."""
        return self.raw.get(column, "").strip()

    def default_corrected(self, column: str) -> str:
        """The rule-corrected value for a time column (ignoring overrides)."""
        rule_field = TIME_COLUMNS[column]
        return corrections.correct_zeo_time(self.raw.get(column, ""), rule_field)

    def corrected(self, column: str) -> str:
        """The effective corrected value: the override if set, else the rule."""
        if column in self.overrides:
            return self.overrides[column]
        return self.default_corrected(column)

    def set_override(self, column: str, value: Optional[str]) -> None:
        """Override (or, with None/'', clear the override for) a time column."""
        if column not in TIME_COLUMNS:
            raise ValueError(f"not a correctable time column: {column!r}")
        if value is None or value.strip() == "":
            self.overrides.pop(column, None)
        else:
            # Validate the format so bad input fails here, not at export time.
            corrections.parse_zeo_datetime(value)
            self.overrides[column] = value.strip()

    def is_overridden(self, column: str) -> bool:
        return column in self.overrides

    def to_output_row(self) -> Dict[str, str]:
        """Build an output row: the raw row with corrected time columns."""
        row = dict(self.raw)
        for column in TIME_COLUMNS:
            if column in row or self.original(column):
                row[column] = self.corrected(column)
        return row


@dataclass
class NightCollection:
    """The decoded fieldnames plus the parsed nights."""

    fieldnames: List[str]
    nights: List[Night]

    @classmethod
    def from_rows(cls, fieldnames: List[str], rows: List[Dict[str, str]]) -> "NightCollection":
        return cls(fieldnames=list(fieldnames), nights=[Night(raw=row) for row in rows])

    def select_all(self, selected: bool = True) -> None:
        for night in self.nights:
            night.selected = selected

    @property
    def selected(self) -> List[Night]:
        return [night for night in self.nights if night.selected]

    def write_output(self, path: str, *, only_selected: bool = True) -> int:
        """Write corrected rows to ``path`` as CSV. Returns the row count."""
        nights = self.selected if only_selected else self.nights
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=self.fieldnames, extrasaction="ignore", restval=""
            )
            writer.writeheader()
            for night in nights:
                writer.writerow(night.to_output_row())
        return len(nights)
