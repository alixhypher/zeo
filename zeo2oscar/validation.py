"""Sanity checks for a night's corrected times.

The corrections (especially the +12h "before midnight" fixup on Start of Night)
can occasionally produce a surprising result, so before exporting it is worth
flagging nights whose corrected times are not chronologically consistent. These
checks are advisory only -- they never block an export.
"""

from __future__ import annotations

from typing import List

from .corrections import parse_zeo_datetime
from .records import COL_END, COL_START, Night


def validate_night(night: Night) -> List[str]:
    """Return a list of human-readable warnings for a night (empty if fine)."""
    warnings: List[str] = []

    start = parse_zeo_datetime(night.corrected(COL_START))
    end = parse_zeo_datetime(night.corrected(COL_END))

    if start is None:
        warnings.append("missing Start of Night")
    if end is None:
        warnings.append("missing End of Night")

    # The only reliable chronology check: a night must have positive duration.
    # Rise Time is intentionally not compared against End of Night -- the source
    # data legitimately records them within a minute of each other in either
    # order, so such a check would flag normal records.
    if start is not None and end is not None and start >= end:
        warnings.append("Start of Night is not before End of Night")

    return warnings


def has_warnings(night: Night) -> bool:
    return bool(validate_night(night))
