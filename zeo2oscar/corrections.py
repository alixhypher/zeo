"""Time-correction rules for Zeo records.

The ``ZeoDataDecoder.jar`` output has two known problems with the
Start of Night / End of Night / Rise Time columns:

1. Every time is shifted 5 hours earlier than the real local time.  This is a
   timezone artefact of how the decoder renders the device's timestamps; the
   bundled decoder run (see :mod:`zeo2oscar.decoder`) pins the JVM timezone so
   the raw output is reproducible, and we add the 5 hours back here.

2. The Start of Night is an evening time written in 12-hour notation without an
   AM/PM marker, so a real 11:50 PM bedtime shows up as ``11:50``.  Such
   "before midnight" times need a further 12 hours added to reach proper
   24-hour notation.

These rules were validated against ``zeosleep_corrected.csv``: the 05/31/2026
record decodes to a Start of Night of ``06:50`` and the hand-corrected value is
``23:50`` (06:50 + 5h + 12h), while End/Rise (``03:48``/``03:50``) correct to
``08:48``/``08:50`` (+5h only).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

# Field identifiers used throughout the package.
START = "start"
END = "end"
RISE = "rise"

# Hours added to every corrected time to undo the decoder's timezone shift.
BASE_OFFSET_HOURS = 5

# Extra hours added to evening (PM) times that were written in 12-hour notation.
PM_FIXUP_HOURS = 12

# After the base offset, a Start-of-Night earlier than this hour is treated as a
# 12-hour-notation evening time and bumped by ``PM_FIXUP_HOURS``.  Real bedtimes
# fall in the evening, so anything decoding to before 6 PM is the wrapped form.
PM_FIXUP_THRESHOLD_HOUR = 18

# Format used by the decoder and expected by OSCAR, e.g. "05/31/2026 23:50".
ZEO_DATETIME_FORMAT = "%m/%d/%Y %H:%M"


def parse_zeo_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse a ``MM/DD/YYYY HH:MM`` string. Blank/missing values return None."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    return datetime.strptime(value, ZEO_DATETIME_FORMAT)


def format_zeo_datetime(value: Optional[datetime]) -> str:
    """Format a datetime back into ``MM/DD/YYYY HH:MM``. None becomes ''."""
    if value is None:
        return ""
    return value.strftime(ZEO_DATETIME_FORMAT)


def correct_datetime(
    dt: Optional[datetime],
    field: str,
    *,
    base_offset_hours: int = BASE_OFFSET_HOURS,
    pm_fixup_threshold_hour: int = PM_FIXUP_THRESHOLD_HOUR,
) -> Optional[datetime]:
    """Apply the correction rules to a single decoded datetime.

    ``field`` is one of :data:`START`, :data:`END`, :data:`RISE`.  Only the
    Start of Night is eligible for the 12-hour "before midnight" fixup, matching
    the README note that this "usually" affects just the start of night.
    Returns None when ``dt`` is None so empty columns stay empty.
    """
    if dt is None:
        return None
    if field not in (START, END, RISE):
        raise ValueError(f"unknown field: {field!r}")

    corrected = dt + timedelta(hours=base_offset_hours)
    if field == START and corrected.hour < pm_fixup_threshold_hour:
        corrected = corrected + timedelta(hours=PM_FIXUP_HOURS)
    return corrected


def correct_zeo_time(value: Optional[str], field: str, **kwargs) -> str:
    """String-in/string-out convenience wrapper around :func:`correct_datetime`."""
    return format_zeo_datetime(
        correct_datetime(parse_zeo_datetime(value), field, **kwargs)
    )
