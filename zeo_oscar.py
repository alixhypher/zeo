#!/usr/bin/env python3
"""Decode Zeo sleep records, fix ZeoDataDecoder timestamps, and export Oscar CSVs.

The module can be used as a small Tkinter application (default) or as a
headless command-line converter for tests/automation.
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Sequence

TIME_FORMAT = "%m/%d/%Y %H:%M"
DATE_FORMAT = "%m/%d/%Y"
TIME_COLUMNS = ("Start of Night", "End of Night", "Rise Time")
DEFAULT_DECODER = "ZeoDataDecoder.jar"
DEFAULT_DAT = "ZEOSLEEP.DAT"
DEFAULT_OUTPUT = "oscar_zeosleep.csv"
DEFAULT_DECODER_TIMEZONE = "Etc/GMT+5"


@dataclass
class SleepRecord:
    """A decoded Zeo record plus editable corrected timestamps."""

    row: dict[str, str]
    original_times: dict[str, str]
    corrected_times: dict[str, str]
    selected: bool = True
    notes: list[str] = field(default_factory=list)

    @property
    def sleep_date(self) -> str:
        return self.row.get("Sleep Date", "")

    def output_row(self) -> dict[str, str]:
        row = dict(self.row)
        for column in TIME_COLUMNS:
            row[column] = self.corrected_times.get(column, row.get(column, ""))
        return row


def parse_zeo_time(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, TIME_FORMAT)
    except ValueError:
        return None


def format_zeo_time(value: datetime | None) -> str:
    return "" if value is None else value.strftime(TIME_FORMAT)


def correct_time(value: str, *, column: str, offset_hours: int = 5, fix_start_pm: bool = True) -> tuple[str, list[str]]:
    """Return the corrected timestamp for a ZeoDataDecoder time field.

    ZeoDataDecoder records are corrected by adding ``offset_hours``. The start
    of night may additionally be emitted as a 12-hour clock value without a PM
    marker, so morning-looking start times are first advanced by 12 hours.
    """
    parsed = parse_zeo_time(value)
    if parsed is None:
        return value or "", []

    notes: list[str] = []
    corrected = parsed
    if fix_start_pm and column == "Start of Night" and corrected.hour < 12:
        corrected += timedelta(hours=12)
        notes.append("start +12h")
    if offset_hours:
        corrected += timedelta(hours=offset_hours)
        notes.append(f"+{offset_hours}h" if offset_hours > 0 else f"{offset_hours}h")
    return format_zeo_time(corrected), notes


def correct_row(row: dict[str, str], *, offset_hours: int = 5, fix_start_pm: bool = True) -> SleepRecord:
    originals = {column: row.get(column, "") for column in TIME_COLUMNS}
    corrected: dict[str, str] = {}
    notes: list[str] = []
    for column, original in originals.items():
        corrected_value, column_notes = correct_time(
            original, column=column, offset_hours=offset_hours, fix_start_pm=fix_start_pm
        )
        corrected[column] = corrected_value
        if column_notes:
            notes.append(f"{column}: {', '.join(column_notes)}")
    return SleepRecord(row=dict(row), original_times=originals, corrected_times=corrected, notes=notes)


def read_csv(path: Path | str) -> tuple[list[str], list[dict[str, str]]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"{path} does not contain a CSV header")
        return list(reader.fieldnames), [dict(row) for row in reader]


def decode_dat(
    dat_path: Path | str,
    decoder_jar: Path | str = DEFAULT_DECODER,
    decoder_timezone: str | None = DEFAULT_DECODER_TIMEZONE,
) -> tuple[list[str], list[dict[str, str]]]:
    dat_path = Path(dat_path)
    decoder_jar = Path(decoder_jar)
    if not dat_path.exists():
        raise FileNotFoundError(f"Zeo .DAT file not found: {dat_path}")
    if not decoder_jar.exists():
        raise FileNotFoundError(f"ZeoDataDecoder jar not found: {decoder_jar}")

    env = os.environ.copy()
    if decoder_timezone:
        # ZeoDataDecoder formats timestamps in the JVM default timezone.
        # Pinning a fixed UTC-5 zone reproduces the known decoder output that
        # needs the README's +5 hour correction, independent of host locale/DST.
        env["TZ"] = decoder_timezone
    result = subprocess.run(
        ["java", "-jar", str(decoder_jar), str(dat_path)],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ZeoDataDecoder failed with exit code {result.returncode}: {result.stderr.strip()}"
        )
    reader = csv.DictReader(io.StringIO(result.stdout))
    if not reader.fieldnames:
        raise ValueError("ZeoDataDecoder did not emit a CSV header")
    return list(reader.fieldnames), [dict(row) for row in reader]


def load_records(
    *,
    csv_path: Path | str | None = None,
    dat_path: Path | str = DEFAULT_DAT,
    decoder_jar: Path | str = DEFAULT_DECODER,
    decoder_timezone: str | None = DEFAULT_DECODER_TIMEZONE,
    offset_hours: int = 5,
    fix_start_pm: bool = True,
) -> tuple[list[str], list[SleepRecord]]:
    fieldnames, rows = read_csv(csv_path) if csv_path else decode_dat(dat_path, decoder_jar, decoder_timezone)
    for column in TIME_COLUMNS:
        if column not in fieldnames:
            raise ValueError(f"Input is missing required column: {column}")
    records = [correct_row(row, offset_hours=offset_hours, fix_start_pm=fix_start_pm) for row in rows]
    return fieldnames, records


def filter_records(records: Iterable[SleepRecord], dates: Sequence[str] | None) -> list[SleepRecord]:
    if not dates:
        return list(records)
    wanted = {normalize_date(date) for date in dates}
    return [record for record in records if normalize_date(record.sleep_date) in wanted]


def normalize_date(value: str) -> str:
    value = value.strip()
    for fmt in (DATE_FORMAT, "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime(DATE_FORMAT)
        except ValueError:
            pass
    return value


def write_output(path: Path | str, fieldnames: Sequence[str], records: Iterable[SleepRecord]) -> int:
    selected = [record.output_row() for record in records if record.selected]
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(selected)
    return len(selected)


class ZeoOscarApp:
    """Tkinter GUI for selecting records and overriding corrected times."""

    def __init__(self, fieldnames: Sequence[str], records: list[SleepRecord], output_path: Path | str):
        import tkinter as tk
        from tkinter import messagebox, simpledialog, ttk

        self.tk = tk
        self.messagebox = messagebox
        self.simpledialog = simpledialog
        self.ttk = ttk
        self.fieldnames = list(fieldnames)
        self.records = records
        self.output_path = Path(output_path)

        self.root = tk.Tk()
        self.root.title("Zeo to Oscar CSV Exporter")
        self.root.geometry("1180x560")

        instructions = (
            "Select the nights to export. Original decoder times and corrected times are shown side by side. "
            "Double-click a corrected time (or press Enter) to override it."
        )
        tk.Label(self.root, text=instructions, anchor="w", justify="left").pack(fill="x", padx=10, pady=(10, 4))

        columns = (
            "selected",
            "sleep_date",
            "zq",
            "start_original",
            "start_corrected",
            "end_original",
            "end_corrected",
            "rise_original",
            "rise_corrected",
            "notes",
        )
        self.tree = ttk.Treeview(self.root, columns=columns, show="headings", selectmode="browse")
        headings = {
            "selected": "Export",
            "sleep_date": "Sleep Date",
            "zq": "ZQ",
            "start_original": "Start Original",
            "start_corrected": "Start Corrected",
            "end_original": "End Original",
            "end_corrected": "End Corrected",
            "rise_original": "Rise Original",
            "rise_corrected": "Rise Corrected",
            "notes": "Automatic Fixes",
        }
        widths = {
            "selected": 70,
            "sleep_date": 100,
            "zq": 55,
            "start_original": 145,
            "start_corrected": 145,
            "end_original": 145,
            "end_corrected": 145,
            "rise_original": 145,
            "rise_corrected": 145,
            "notes": 190,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], minwidth=40, stretch=column == "notes")
        self.tree.pack(fill="both", expand=True, padx=10, pady=6)
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<space>", self.on_toggle_key)
        self.tree.bind("<Return>", self.on_edit_key)

        button_frame = tk.Frame(self.root)
        button_frame.pack(fill="x", padx=10, pady=(4, 10))
        tk.Button(button_frame, text="Select All", command=self.select_all).pack(side="left")
        tk.Button(button_frame, text="Select None", command=self.select_none).pack(side="left", padx=6)
        tk.Button(button_frame, text="Export CSV", command=self.export).pack(side="right")

        self.refresh()

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for index, record in enumerate(self.records):
            self.tree.insert("", "end", iid=str(index), values=self.values_for(record))

    def values_for(self, record: SleepRecord) -> tuple[str, ...]:
        return (
            "☑" if record.selected else "☐",
            record.sleep_date,
            record.row.get("ZQ", ""),
            record.original_times.get("Start of Night", ""),
            record.corrected_times.get("Start of Night", ""),
            record.original_times.get("End of Night", ""),
            record.corrected_times.get("End of Night", ""),
            record.original_times.get("Rise Time", ""),
            record.corrected_times.get("Rise Time", ""),
            "; ".join(record.notes),
        )

    def selected_record_index(self) -> int | None:
        selected = self.tree.selection()
        return int(selected[0]) if selected else None

    def toggle_record(self, index: int) -> None:
        self.records[index].selected = not self.records[index].selected
        self.tree.item(str(index), values=self.values_for(self.records[index]))

    def on_toggle_key(self, _event=None) -> str:
        index = self.selected_record_index()
        if index is not None:
            self.toggle_record(index)
        return "break"

    def on_edit_key(self, _event=None) -> str:
        index = self.selected_record_index()
        if index is not None:
            self.edit_time(index, "Start of Night")
        return "break"

    def on_double_click(self, event) -> None:
        row_id = self.tree.identify_row(event.y)
        column_id = self.tree.identify_column(event.x)
        if not row_id:
            return
        index = int(row_id)
        if column_id == "#1":
            self.toggle_record(index)
            return
        editable = {"#5": "Start of Night", "#7": "End of Night", "#9": "Rise Time"}
        if column_id in editable:
            self.edit_time(index, editable[column_id])

    def edit_time(self, index: int, column: str) -> None:
        record = self.records[index]
        current = record.corrected_times.get(column, "")
        value = self.simpledialog.askstring(
            "Override corrected time",
            f"Enter {column} for {record.sleep_date} as MM/DD/YYYY HH:MM:",
            initialvalue=current,
            parent=self.root,
        )
        if value is None:
            return
        value = value.strip()
        if value and parse_zeo_time(value) is None:
            self.messagebox.showerror("Invalid time", "Use MM/DD/YYYY HH:MM, for example 06/01/2026 08:50.")
            return
        record.corrected_times[column] = value
        if f"{column}: manual override" not in record.notes:
            record.notes.append(f"{column}: manual override")
        self.tree.item(str(index), values=self.values_for(record))

    def select_all(self) -> None:
        for record in self.records:
            record.selected = True
        self.refresh()

    def select_none(self) -> None:
        for record in self.records:
            record.selected = False
        self.refresh()

    def export(self) -> None:
        from tkinter import filedialog

        destination = filedialog.asksaveasfilename(
            title="Save Oscar CSV",
            defaultextension=".csv",
            initialfile=self.output_path.name,
            filetypes=(("CSV files", "*.csv"), ("All files", "*.*")),
        )
        if not destination:
            return
        count = write_output(destination, self.fieldnames, self.records)
        self.messagebox.showinfo("Export complete", f"Wrote {count} record(s) to {destination}")

    def run(self) -> None:
        self.root.mainloop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Decode Zeo .DAT files and export Oscar-ready CSV records.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--dat", default=None, help=f"Path to Zeo .DAT file (default: {DEFAULT_DAT}).")
    source.add_argument("--csv", default=None, help="Use an existing ZeoDataDecoder CSV instead of decoding a .DAT file.")
    parser.add_argument("--decoder", default=DEFAULT_DECODER, help=f"Path to ZeoDataDecoder.jar (default: {DEFAULT_DECODER}).")
    parser.add_argument("--decoder-timezone", default=DEFAULT_DECODER_TIMEZONE, help=f"Timezone used while running the Java decoder (default: {DEFAULT_DECODER_TIMEZONE}; use an empty string for the host default).")
    parser.add_argument("--output", "-o", default=DEFAULT_OUTPUT, help=f"Output CSV path (default: {DEFAULT_OUTPUT}).")
    parser.add_argument("--offset-hours", type=int, default=5, help="Hours to add to ZeoDataDecoder timestamps (default: 5).")
    parser.add_argument("--no-start-pm-fix", action="store_true", help="Do not add 12 hours to morning-looking Start of Night values before applying the offset.")
    parser.add_argument("--dates", nargs="*", help="Only export these sleep dates (MM/DD/YYYY or YYYY-MM-DD).")
    parser.add_argument("--no-gui", action="store_true", help="Write the output CSV without launching the Tkinter selector.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dat_path = args.dat or DEFAULT_DAT
    try:
        fieldnames, records = load_records(
            csv_path=args.csv,
            dat_path=dat_path,
            decoder_jar=args.decoder,
            decoder_timezone=args.decoder_timezone or None,
            offset_hours=args.offset_hours,
            fix_start_pm=not args.no_start_pm_fix,
        )
        records = filter_records(records, args.dates)
        if args.no_gui:
            count = write_output(args.output, fieldnames, records)
            print(f"Wrote {count} record(s) to {args.output}")
            return 0
        ZeoOscarApp(fieldnames, records, args.output).run()
        return 0
    except Exception as exc:  # pragma: no cover - command-line safety net
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
