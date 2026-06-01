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

    LIGHT_THEME = {
        "bg": "#f4f7fb",
        "panel": "#ffffff",
        "panel_alt": "#eef4ff",
        "text": "#172033",
        "muted": "#5d6b82",
        "accent": "#2563eb",
        "accent_text": "#ffffff",
        "border": "#d8e0ef",
        "tree_bg": "#ffffff",
        "tree_alt": "#f7faff",
        "tree_selected": "#e6f0ff",
        "tree_unselected": "#fff7ed",
        "heading": "#e8eef8",
    }
    DARK_THEME = {
        "bg": "#111827",
        "panel": "#1f2937",
        "panel_alt": "#263244",
        "text": "#f9fafb",
        "muted": "#cbd5e1",
        "accent": "#60a5fa",
        "accent_text": "#0f172a",
        "border": "#374151",
        "tree_bg": "#182231",
        "tree_alt": "#202c3d",
        "tree_selected": "#1e3a5f",
        "tree_unselected": "#3a2a1c",
        "heading": "#273449",
    }
    EDITABLE_COLUMNS = {"#5": "Start of Night", "#7": "End of Night", "#9": "Rise Time"}

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
        self.dark_mode = tk.BooleanVar(value=True)

        self.root = tk.Tk()
        self.root.title("Zeo to Oscar CSV Exporter")
        self.root.geometry("1240x640")
        self.root.minsize(1060, 520)

        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self.app_frame = ttk.Frame(self.root, style="App.TFrame", padding=18)
        self.app_frame.pack(fill="both", expand=True)

        header = ttk.Frame(self.app_frame, style="Panel.TFrame", padding=(18, 16))
        header.pack(fill="x", pady=(0, 14))
        title_row = ttk.Frame(header, style="Panel.TFrame")
        title_row.pack(fill="x")
        ttk.Label(title_row, text="Zeo → Oscar Exporter", style="Title.TLabel").pack(side="left")
        self.theme_button = ttk.Button(title_row, text="☀ Light mode", command=self.toggle_theme, style="Secondary.TButton")
        self.theme_button.pack(side="right")
        subtitle = (
            "Review decoded nights, compare original vs corrected times, single-click a row to include/exclude it, "
            "and double-click corrected times to override them."
        )
        ttk.Label(header, text=subtitle, style="Muted.TLabel", wraplength=980, justify="left").pack(anchor="w", pady=(8, 0))

        summary_frame = ttk.Frame(self.app_frame, style="App.TFrame")
        summary_frame.pack(fill="x", pady=(0, 12))
        self.total_card = ttk.Label(summary_frame, style="Card.TLabel", anchor="center", padding=(14, 10))
        self.total_card.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.selected_card = ttk.Label(summary_frame, style="Card.TLabel", anchor="center", padding=(14, 10))
        self.selected_card.pack(side="left", fill="x", expand=True, padx=8)
        self.output_card = ttk.Label(summary_frame, style="Card.TLabel", anchor="center", padding=(14, 10))
        self.output_card.pack(side="left", fill="x", expand=True, padx=(8, 0))

        table_frame = ttk.Frame(self.app_frame, style="Panel.TFrame", padding=10)
        table_frame.pack(fill="both", expand=True)
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
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
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
            "notes": "Automatic Fixes / Notes",
        }
        widths = {
            "selected": 78,
            "sleep_date": 110,
            "zq": 58,
            "start_original": 148,
            "start_corrected": 152,
            "end_original": 148,
            "end_corrected": 152,
            "rise_original": 148,
            "rise_corrected": 152,
            "notes": 220,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], minwidth=46, stretch=column == "notes")
        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        self.tree.bind("<ButtonRelease-1>", self.on_single_click)
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<space>", self.on_toggle_key)
        self.tree.bind("<Return>", self.on_edit_key)

        button_frame = ttk.Frame(self.app_frame, style="App.TFrame")
        button_frame.pack(fill="x", pady=(12, 0))
        ttk.Button(button_frame, text="Select all", command=self.select_all, style="Secondary.TButton").pack(side="left")
        ttk.Button(button_frame, text="Select none", command=self.select_none, style="Secondary.TButton").pack(side="left", padx=8)
        self.status_label = ttk.Label(button_frame, style="Muted.TLabel")
        self.status_label.pack(side="left", padx=10)
        ttk.Button(button_frame, text="Export CSV", command=self.export, style="Primary.TButton").pack(side="right")

        self.apply_theme()
        self.refresh()

    def current_theme(self) -> dict[str, str]:
        return self.DARK_THEME if self.dark_mode.get() else self.LIGHT_THEME

    def toggle_theme(self) -> None:
        self.dark_mode.set(not self.dark_mode.get())
        self.apply_theme()
        self.refresh()

    def apply_theme(self) -> None:
        theme = self.current_theme()
        self.root.configure(bg=theme["bg"])
        self.style.configure("App.TFrame", background=theme["bg"])
        self.style.configure("Panel.TFrame", background=theme["panel"], relief="flat")
        self.style.configure("Title.TLabel", background=theme["panel"], foreground=theme["text"], font=("TkDefaultFont", 20, "bold"))
        self.style.configure("Muted.TLabel", background=theme["panel"], foreground=theme["muted"], font=("TkDefaultFont", 10))
        self.style.configure("Card.TLabel", background=theme["panel_alt"], foreground=theme["text"], font=("TkDefaultFont", 11, "bold"), relief="flat")
        self.style.configure("Treeview", background=theme["tree_bg"], fieldbackground=theme["tree_bg"], foreground=theme["text"], rowheight=30, bordercolor=theme["border"], lightcolor=theme["border"], darkcolor=theme["border"])
        self.style.configure("Treeview.Heading", background=theme["heading"], foreground=theme["text"], font=("TkDefaultFont", 10, "bold"), relief="flat", padding=(8, 8))
        self.style.map("Treeview", background=[("selected", theme["accent"])], foreground=[("selected", theme["accent_text"])])
        self.style.configure("Primary.TButton", background=theme["accent"], foreground=theme["accent_text"], font=("TkDefaultFont", 10, "bold"), padding=(16, 9), borderwidth=0)
        self.style.configure("Secondary.TButton", background=theme["panel_alt"], foreground=theme["text"], padding=(14, 8), borderwidth=0)
        self.style.map("Primary.TButton", background=[("active", theme["accent"])], foreground=[("active", theme["accent_text"])])
        self.style.map("Secondary.TButton", background=[("active", theme["heading"])], foreground=[("active", theme["text"])])
        self.theme_button.configure(text="☀ Light mode" if self.dark_mode.get() else "🌙 Dark mode")
        self.update_tree_tags()

    def update_tree_tags(self) -> None:
        theme = self.current_theme()
        self.tree.tag_configure("selected_even", background=theme["tree_bg"], foreground=theme["text"])
        self.tree.tag_configure("selected_odd", background=theme["tree_alt"], foreground=theme["text"])
        self.tree.tag_configure("not_exported", background=theme["tree_unselected"], foreground=theme["muted"])

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for index, record in enumerate(self.records):
            self.tree.insert("", "end", iid=str(index), values=self.values_for(record), tags=self.tags_for(index, record))
        self.update_summary()

    def tags_for(self, index: int, record: SleepRecord) -> tuple[str, ...]:
        if not record.selected:
            return ("not_exported",)
        return ("selected_even",) if index % 2 == 0 else ("selected_odd",)

    def values_for(self, record: SleepRecord) -> tuple[str, ...]:
        return (
            "✓ Export" if record.selected else "— Skip",
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
        self.tree.item(str(index), values=self.values_for(self.records[index]), tags=self.tags_for(index, self.records[index]))
        self.tree.selection_set(str(index))
        self.update_summary()

    def update_summary(self) -> None:
        total = len(self.records)
        selected = sum(1 for record in self.records if record.selected)
        skipped = total - selected
        self.total_card.configure(text=f"{total} decoded night{'s' if total != 1 else ''}")
        self.selected_card.configure(text=f"{selected} selected • {skipped} skipped")
        self.output_card.configure(text=f"Output: {self.output_path.name}")
        self.status_label.configure(text="Single-click a row to toggle export; double-click corrected times to edit.")

    def on_single_click(self, event) -> str | None:
        row_id = self.tree.identify_row(event.y)
        column_id = self.tree.identify_column(event.x)
        if not row_id:
            return None
        self.tree.selection_set(row_id)
        # Corrected timestamp cells are reserved for double-click editing, so a
        # single click there only focuses the row instead of toggling it.
        if column_id not in self.EDITABLE_COLUMNS:
            self.toggle_record(int(row_id))
            return "break"
        return None

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

    def on_double_click(self, event) -> str | None:
        row_id = self.tree.identify_row(event.y)
        column_id = self.tree.identify_column(event.x)
        if not row_id:
            return None
        index = int(row_id)
        if column_id in self.EDITABLE_COLUMNS:
            self.edit_time(index, self.EDITABLE_COLUMNS[column_id])
            return "break"
        return None

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
        self.tree.item(str(index), values=self.values_for(record), tags=self.tags_for(index, record))
        self.update_summary()

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
