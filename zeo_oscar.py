#!/usr/bin/env python3
"""Zeo -> Oscar: decode Zeo .DAT files, correct timestamps, export to CSV.

A small Tkinter desktop app that:

1. Decodes a Zeo ``.DAT`` file with ZeoDataDecoder.jar (requires Java).
2. Shows each night with its original and auto-corrected Start of Night,
   End of Night and Rise Time (see zeo_core for the correction rules).
3. Lets you tick which nights to export and override any corrected time.
4. Generates an Oscar-ready CSV containing the selected nights.

Run it with no arguments to launch the GUI:

    python3 zeo_oscar.py

The default .DAT file and decoder jar are looked up next to this script, but
both can be changed from within the app.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import zeo_core as zc

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DAT = os.path.join(HERE, "ZEOSLEEP.DAT")
DEFAULT_JAR = os.path.join(HERE, "ZeoDataDecoder.jar")

# Columns shown in the table, in order. Each entry is (heading, width).
DISPLAY_COLUMNS = [
    ("sel", "Export", 60),
    (zc.SLEEP_DATE_COL, "Sleep Date", 100),
    ("ZQ", "ZQ", 50),
    (f"orig_{zc.START_COL}", "Start (orig)", 130),
    (f"corr_{zc.START_COL}", "Start (corrected)", 140),
    (f"orig_{zc.END_COL}", "End (orig)", 130),
    (f"corr_{zc.END_COL}", "End (corrected)", 140),
    (f"orig_{zc.RISE_COL}", "Rise (orig)", 130),
    (f"corr_{zc.RISE_COL}", "Rise (corrected)", 140),
]

# Map a corrected-column id back to its underlying time column.
CORRECTED_COLUMN_TO_TIME = {f"corr_{col}": col for col in zc.TIME_COLUMNS}


class ZeoOscarApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Zeo → Oscar")
        self.root.geometry("1100x560")

        self.header: list[str] = []
        self.records: list[zc.SleepRecord] = []
        # Map Treeview item id -> SleepRecord.
        self.item_to_record: dict[str, zc.SleepRecord] = {}

        self.dat_path = tk.StringVar(value=DEFAULT_DAT if os.path.isfile(DEFAULT_DAT) else "")
        self.jar_path = tk.StringVar(value=DEFAULT_JAR if os.path.isfile(DEFAULT_JAR) else "")

        self._build_toolbar()
        self._build_table()
        self._build_statusbar()

        # Load automatically on startup if both inputs are present.
        if self.dat_path.get() and self.jar_path.get():
            self.root.after(100, self.decode)

    # ----- UI construction -------------------------------------------------
    def _build_toolbar(self):
        bar = ttk.Frame(self.root, padding=(8, 6))
        bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(bar, text="Zeo .DAT:").grid(row=0, column=0, sticky="w")
        ttk.Entry(bar, textvariable=self.dat_path, width=48).grid(row=0, column=1, padx=4)
        ttk.Button(bar, text="Browse…", command=self.browse_dat).grid(row=0, column=2)

        ttk.Label(bar, text="Decoder jar:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(bar, textvariable=self.jar_path, width=48).grid(row=1, column=1, padx=4, pady=(4, 0))
        ttk.Button(bar, text="Browse…", command=self.browse_jar).grid(row=1, column=2, pady=(4, 0))

        actions = ttk.Frame(bar)
        actions.grid(row=0, column=3, rowspan=2, padx=(16, 0))
        ttk.Button(actions, text="Decode .DAT", command=self.decode).pack(side=tk.LEFT, padx=3)
        ttk.Button(actions, text="Load CSV…", command=self.load_csv).pack(side=tk.LEFT, padx=3)
        ttk.Separator(actions, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Button(actions, text="Select all", command=lambda: self.set_all(True)).pack(side=tk.LEFT, padx=3)
        ttk.Button(actions, text="Select none", command=lambda: self.set_all(False)).pack(side=tk.LEFT, padx=3)
        ttk.Button(actions, text="Generate Oscar CSV…", command=self.generate).pack(side=tk.LEFT, padx=(8, 3))

    def _build_table(self):
        frame = ttk.Frame(self.root, padding=(8, 0))
        frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        col_ids = [cid for cid, _, _ in DISPLAY_COLUMNS]
        self.tree = ttk.Treeview(frame, columns=col_ids, show="headings", selectmode="browse")
        for cid, heading, width in DISPLAY_COLUMNS:
            anchor = "center" if cid in ("sel", "ZQ") else "w"
            self.tree.heading(cid, text=heading)
            self.tree.column(cid, width=width, anchor=anchor, stretch=False)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Single click toggles the export checkbox; double click edits a
        # corrected time cell.
        self.tree.bind("<Button-1>", self.on_single_click)
        self.tree.bind("<Double-1>", self.on_double_click)

    def _build_statusbar(self):
        self.status = tk.StringVar(value="Ready.")
        ttk.Label(self.root, textvariable=self.status, relief=tk.SUNKEN, anchor="w",
                  padding=(6, 3)).pack(side=tk.BOTTOM, fill=tk.X)

    # ----- Data loading ----------------------------------------------------
    def browse_dat(self):
        path = filedialog.askopenfilename(
            title="Select Zeo .DAT file",
            filetypes=[("Zeo data", "*.DAT *.dat"), ("All files", "*.*")],
        )
        if path:
            self.dat_path.set(path)

    def browse_jar(self):
        path = filedialog.askopenfilename(
            title="Select ZeoDataDecoder.jar",
            filetypes=[("Jar files", "*.jar"), ("All files", "*.*")],
        )
        if path:
            self.jar_path.set(path)

    def decode(self):
        dat = self.dat_path.get().strip()
        jar = self.jar_path.get().strip()
        if not dat or not jar:
            messagebox.showwarning("Missing input", "Please choose both a .DAT file and the decoder jar.")
            return
        try:
            header, records = zc.decode_and_build(dat, jar)
        except FileNotFoundError as exc:
            messagebox.showerror("File not found", str(exc))
            return
        except subprocess.CalledProcessError as exc:
            messagebox.showerror(
                "Decode failed",
                f"ZeoDataDecoder.jar exited with an error.\n\n{exc.stderr or exc}",
            )
            return
        except OSError as exc:
            messagebox.showerror(
                "Java not found",
                f"Could not run Java. Make sure Java is installed and on your PATH.\n\n{exc}",
            )
            return
        self._populate(header, records, source=f"decoded {os.path.basename(dat)}")

    def load_csv(self):
        path = filedialog.askopenfilename(
            title="Load decoder CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            header, records = zc.load_csv_file(path)
        except OSError as exc:
            messagebox.showerror("Load failed", str(exc))
            return
        self._populate(header, records, source=f"loaded {os.path.basename(path)}")

    def _populate(self, header, records, source):
        self.header = header
        self.records = records
        self.tree.delete(*self.tree.get_children())
        self.item_to_record.clear()
        for record in records:
            item = self.tree.insert("", tk.END, values=self._row_values(record))
            self.item_to_record[item] = record
        self.status.set(f"{source}: {len(records)} night(s).")

    def _row_values(self, record: zc.SleepRecord) -> list:
        values = []
        for cid, _, _ in DISPLAY_COLUMNS:
            if cid == "sel":
                values.append("☑" if record.selected else "☐")
            elif cid == zc.SLEEP_DATE_COL:
                values.append(record.sleep_date)
            elif cid == "ZQ":
                values.append(record.row.get("ZQ", ""))
            elif cid.startswith("orig_"):
                values.append(record.original(cid[len("orig_"):]))
            elif cid in CORRECTED_COLUMN_TO_TIME:
                values.append(record.corrected.get(CORRECTED_COLUMN_TO_TIME[cid], ""))
            else:
                values.append("")
        return values

    def _refresh_row(self, item):
        self.tree.item(item, values=self._row_values(self.item_to_record[item]))

    # ----- Interaction -----------------------------------------------------
    def on_single_click(self, event):
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        column = self.tree.identify_column(event.x)  # like "#1"
        item = self.tree.identify_row(event.y)
        if not item:
            return
        col_index = int(column[1:]) - 1
        cid = DISPLAY_COLUMNS[col_index][0]
        if cid == "sel":
            record = self.item_to_record[item]
            record.selected = not record.selected
            self._refresh_row(item)
            self._update_selection_count()

    def on_double_click(self, event):
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        column = self.tree.identify_column(event.x)
        item = self.tree.identify_row(event.y)
        if not item:
            return
        col_index = int(column[1:]) - 1
        cid = DISPLAY_COLUMNS[col_index][0]
        if cid in CORRECTED_COLUMN_TO_TIME:
            self._edit_cell(item, column, cid)

    def _edit_cell(self, item, column, cid):
        """Pop up an inline Entry to override a corrected time value."""
        x, y, width, height = self.tree.bbox(item, column)
        time_col = CORRECTED_COLUMN_TO_TIME[cid]
        current = self.item_to_record[item].corrected.get(time_col, "")

        entry = ttk.Entry(self.tree)
        entry.place(x=x, y=y, width=width, height=height)
        entry.insert(0, current)
        entry.focus_set()
        entry.select_range(0, tk.END)

        def commit(_event=None):
            new_value = entry.get().strip()
            record = self.item_to_record[item]
            if new_value and zc.parse_datetime(new_value) is None:
                messagebox.showwarning(
                    "Invalid time",
                    f"'{new_value}' is not a valid timestamp.\n"
                    f"Use the format MM/DD/YYYY HH:MM, e.g. 05/31/2026 23:50.",
                )
                entry.focus_set()
                return
            record.corrected[time_col] = new_value
            entry.destroy()
            self._refresh_row(item)
            self.status.set(f"Overrode {time_col} for {record.sleep_date}.")

        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", commit)
        entry.bind("<Escape>", lambda e: entry.destroy())

    def set_all(self, value: bool):
        for item, record in self.item_to_record.items():
            record.selected = value
            self._refresh_row(item)
        self._update_selection_count()

    def _update_selection_count(self):
        n = sum(1 for r in self.records if r.selected)
        self.status.set(f"{n} of {len(self.records)} night(s) selected for export.")

    # ----- Output ----------------------------------------------------------
    def generate(self):
        if not self.records:
            messagebox.showinfo("Nothing to export", "Decode or load a file first.")
            return
        selected = [r for r in self.records if r.selected]
        if not selected:
            messagebox.showinfo("Nothing selected", "Tick at least one night to export.")
            return
        path = filedialog.asksaveasfilename(
            title="Save Oscar CSV",
            defaultextension=".csv",
            initialfile="zeosleep_oscar.csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            written = zc.write_output(self.header, self.records, path, selected_only=True)
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc))
            return
        self.status.set(f"Wrote {written} night(s) to {os.path.basename(path)}.")
        messagebox.showinfo("Done", f"Wrote {written} night(s) to:\n{path}")


def main():
    root = tk.Tk()
    ZeoOscarApp(root)
    root.mainloop()


if __name__ == "__main__":
    sys.exit(main())
