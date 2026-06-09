"""Command-line interface for zeo2oscar.

Examples
--------
List every decoded night with its corrected times::

    python -m zeo2oscar --list

Export selected nights to an OSCAR-ready CSV::

    python -m zeo2oscar --days 05/30/2026,05/31/2026 --out oscar.csv

Export every night without launching the GUI::

    python -m zeo2oscar --all --out oscar.csv

Skip decoding and work from an existing CSV::

    python -m zeo2oscar --csv zeosleep.csv --all --out oscar.csv
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from . import decoder
from .decoder import DecoderError
from .records import COL_END, COL_RISE, COL_START, NightCollection
from .validation import validate_night


def load_collection(args: argparse.Namespace) -> NightCollection:
    """Load nights either from an existing CSV or by decoding the .DAT file."""
    if args.csv:
        fieldnames, rows = decoder.load_csv_file(args.csv)
    else:
        fieldnames, rows = decoder.load_from_dat(
            args.dat, args.jar, tz=args.tz
        )
    return NightCollection.from_rows(fieldnames, rows)


def _format_table(collection: NightCollection) -> str:
    """Render a human-readable original-vs-corrected table."""
    header = (
        f"{'#':>3}  {'Sleep Date':<11}  {'ZQ':>3}  "
        f"{'Start (orig -> corrected)':<34}  "
        f"{'End (orig -> corrected)':<34}  "
        f"{'Rise (orig -> corrected)':<34}"
    )
    lines = [header, "-" * len(header)]
    warning_notes = []
    for index, night in enumerate(collection.nights):
        cells = []
        for column in (COL_START, COL_END, COL_RISE):
            orig = night.original(column) or "(none)"
            corr = night.corrected(column) or "(none)"
            cells.append(f"{orig} -> {corr}")
        flag = " !" if validate_night(night) else "  "
        lines.append(
            f"{index:>3}{flag} {night.sleep_date:<11}  {night.zq:>3}  "
            f"{cells[0]:<34}  {cells[1]:<34}  {cells[2]:<34}"
        )
        for warning in validate_night(night):
            warning_notes.append(f"  ! #{index} {night.sleep_date}: {warning}")
    if warning_notes:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(warning_notes)
    return "\n".join(lines)


def _select(collection: NightCollection, args: argparse.Namespace) -> None:
    """Apply --all / --days selection to the collection."""
    if args.all:
        collection.select_all(True)
        return
    if args.days:
        wanted = {day.strip() for day in args.days.split(",") if day.strip()}
        found = set()
        for night in collection.nights:
            if night.sleep_date in wanted:
                night.selected = True
                found.add(night.sleep_date)
        missing = wanted - found
        if missing:
            print(
                "warning: no record for date(s): " + ", ".join(sorted(missing)),
                file=sys.stderr,
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zeo2oscar",
        description="Decode Zeo sleep records and export OSCAR-ready CSV.",
    )
    parser.add_argument(
        "--dat", default=decoder.DEFAULT_DAT,
        help=f"path to the Zeo .DAT file (default: {decoder.DEFAULT_DAT})",
    )
    parser.add_argument(
        "--jar", default=decoder.DEFAULT_JAR,
        help=f"path to ZeoDataDecoder.jar (default: {decoder.DEFAULT_JAR})",
    )
    parser.add_argument(
        "--csv",
        help="use an already-decoded CSV instead of decoding the .DAT file",
    )
    parser.add_argument(
        "--tz", default=decoder.DEFAULT_DECODE_TZ,
        help=f"timezone for the decoder JVM (default: {decoder.DEFAULT_DECODE_TZ})",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="print every night with original and corrected times, then exit",
    )
    parser.add_argument(
        "--days",
        help="comma-separated sleep dates (MM/DD/YYYY) to include in the output",
    )
    parser.add_argument(
        "--all", action="store_true", help="include every night in the output",
    )
    parser.add_argument(
        "--out", help="write the corrected CSV to this path",
    )
    parser.add_argument(
        "--gui", action="store_true", help="launch the graphical interface",
    )
    return parser


def run(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    # With no actionable flag, default to launching the GUI.
    if args.gui or not (args.list or args.out or args.days or args.all):
        from . import gui

        return gui.launch(
            dat=args.dat, jar=args.jar, csv=args.csv, tz=args.tz
        )

    try:
        collection = load_collection(args)
    except DecoderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.list:
        print(_format_table(collection))
        return 0

    _select(collection, args)
    selected = collection.selected
    if not selected:
        print(
            "error: no nights selected. Use --all or --days, or --list to "
            "see available dates.",
            file=sys.stderr,
        )
        return 1

    if not args.out:
        print("error: --out is required to write a file.", file=sys.stderr)
        return 1

    count = collection.write_output(args.out, only_selected=True)
    print(f"Wrote {count} night(s) to {args.out}")
    return 0


def main() -> None:  # pragma: no cover - thin wrapper
    sys.exit(run())
