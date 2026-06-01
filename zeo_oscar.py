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
both can be changed from within the app. A light/dark theme can be toggled from
the header.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk

import zeo_core as zc

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DAT = os.path.join(HERE, "ZEOSLEEP.DAT")
DEFAULT_JAR = os.path.join(HERE, "ZeoDataDecoder.jar")

# Columns shown in the table, in order: (id, heading, width).
DISPLAY_COLUMNS = [
    ("sel", "Export", 90),
    (zc.SLEEP_DATE_COL, "Sleep Date", 110),
    ("ZQ", "ZQ", 55),
    (f"orig_{zc.START_COL}", "Start (orig)", 135),
    (f"corr_{zc.START_COL}", "Start (corrected)", 150),
    (f"orig_{zc.END_COL}", "End (orig)", 135),
    (f"corr_{zc.END_COL}", "End (corrected)", 150),
    (f"orig_{zc.RISE_COL}", "Rise (orig)", 135),
    (f"corr_{zc.RISE_COL}", "Rise (corrected)", 150),
]

# Map a corrected-column id back to its underlying time column.
CORRECTED_COLUMN_TO_TIME = {f"corr_{col}": col for col in zc.TIME_COLUMNS}

CHECK_ON = "☑"   # ☑
CHECK_OFF = "☐"  # ☐

# Colour palettes for the two themes. Keys are shared so the rest of the app is
# theme-agnostic.
THEMES = {
    "light": {
        "name": "light",
        "window": "#eef0f4",
        "surface": "#ffffff",
        "panel": "#f7f8fa",
        "fg": "#1f2329",
        "muted": "#5c6470",
        "accent": "#3b82f6",
        "accent_active": "#2f6fe0",
        "accent_fg": "#ffffff",
        "heading_bg": "#e4e7ee",
        "heading_fg": "#3a4250",
        "stripe": "#f3f5f8",
        "sel_bg": "#cfe3ff",
        "sel_fg": "#0b1b3a",
        "border": "#d4d8df",
        "btn_bg": "#ffffff",
        "btn_active": "#e9edf3",
        "toggle_label": "\U0001f319  Dark",
    },
    "dark": {
        "name": "dark",
        "window": "#16171d",
        "surface": "#22242e",
        "panel": "#1c1e26",
        "fg": "#e6e8ee",
        "muted": "#99a0ad",
        "accent": "#5b9bff",
        "accent_active": "#7badff",
        "accent_fg": "#0b1220",
        "heading_bg": "#2b2e3a",
        "heading_fg": "#c7cdd9",
        "stripe": "#272a34",
        "sel_bg": "#37507f",
        "sel_fg": "#ffffff",
        "border": "#3a3d4a",
        "btn_bg": "#2b2e3a",
        "btn_active": "#363a48",
        "toggle_label": "☀  Light",
    },
}


class ZeoOscarApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Zeo → Oscar")
        self.root.geometry("1140x600")
        self.root.minsize(900, 420)

        self.header: list[str] = []
        self.records: list[zc.SleepRecord] = []
        # Map Treeview item id -> SleepRecord.
        self.item_to_record: dict[str, zc.SleepRecord] = {}

        self.dat_path = tk.StringVar(value=DEFAULT_DAT if os.path.isfile(DEFAULT_DAT) else "")
        self.jar_path = tk.StringVar(value=DEFAULT_JAR if os.path.isfile(DEFAULT_JAR) else "")

        self.theme_name = "light"
        self.style = ttk.Style(self.root)
        # clam honours custom colours far better than the native themes.
        self.style.theme_use("clam")
        self._init_fonts()

        self._build_header()
        self._build_toolbar()
        self._build_table()
        self._build_statusbar()

        self.apply_theme(self.theme_name)

        # Load automatically on startup if both inputs are present.
        if self.dat_path.get() and self.jar_path.get():
            self.root.after(100, self.decode)

    # ----- Fonts & theming -------------------------------------------------
    def _init_fonts(self):
        base = tkfont.nametofont("TkDefaultFont")
        family = base.actual("family")
        self.font_base = tkfont.Font(family=family, size=10)
        self.font_bold = tkfont.Font(family=family, size=10, weight="bold")
        self.font_title = tkfont.Font(family=family, size=16, weight="bold")
        self.font_subtitle = tkfont.Font(family=family, size=9)
        self.font_mono = tkfont.Font(family="TkFixedFont", size=10)

    def toggle_theme(self):
        self.apply_theme("dark" if self.theme_name == "light" else "light")

    def apply_theme(self, name: str):
        self.theme_name = name
        c = THEMES[name]
        s = self.style

        self.root.configure(bg=c["window"])

        s.configure(".", background=c["window"], foreground=c["fg"],
                    fieldbackground=c["surface"], font=self.font_base)
        s.configure("TFrame", background=c["window"])
        s.configure("Header.TFrame", background=c["panel"])
        s.configure("Toolbar.TFrame", background=c["window"])
        s.configure("TLabel", background=c["window"], foreground=c["fg"])
        s.configure("Header.TLabel", background=c["panel"], foreground=c["fg"])
        s.configure("Title.TLabel", background=c["panel"], foreground=c["fg"],
                    font=self.font_title)
        s.configure("Subtitle.TLabel", background=c["panel"], foreground=c["muted"],
                    font=self.font_subtitle)
        s.configure("Status.TLabel", background=c["panel"], foreground=c["muted"],
                    font=self.font_subtitle)
        s.configure("Field.TLabel", background=c["window"], foreground=c["muted"])

        # Buttons.
        s.configure("TButton", background=c["btn_bg"], foreground=c["fg"],
                    bordercolor=c["border"], focuscolor=c["accent"],
                    padding=(10, 5), relief="flat")
        s.map("TButton",
              background=[("active", c["btn_active"]), ("pressed", c["btn_active"])],
              foreground=[("disabled", c["muted"])])
        s.configure("Accent.TButton", background=c["accent"], foreground=c["accent_fg"],
                    font=self.font_bold, padding=(12, 6))
        s.map("Accent.TButton",
              background=[("active", c["accent_active"]), ("pressed", c["accent_active"])])
        s.configure("Toggle.TButton", background=c["panel"], foreground=c["fg"],
                    padding=(10, 5))
        s.map("Toggle.TButton", background=[("active", c["btn_active"])])

        # Entries.
        s.configure("TEntry", fieldbackground=c["surface"], foreground=c["fg"],
                    bordercolor=c["border"], insertcolor=c["fg"], padding=4)
        s.map("TEntry", bordercolor=[("focus", c["accent"])])

        s.configure("TSeparator", background=c["border"])

        # Treeview (the table).
        s.configure("Treeview", background=c["surface"], fieldbackground=c["surface"],
                    foreground=c["fg"], bordercolor=c["border"], rowheight=28,
                    font=self.font_base)
        s.map("Treeview",
              background=[("selected", c["sel_bg"])],
              foreground=[("selected", c["sel_fg"])])
        s.configure("Treeview.Heading", background=c["heading_bg"],
                    foreground=c["heading_fg"], font=self.font_bold,
                    relief="flat", padding=(8, 8))
        s.map("Treeview.Heading", background=[("active", c["heading_bg"])])

        # Scrollbar.
        s.configure("Vertical.TScrollbar", background=c["btn_bg"],
                    troughcolor=c["panel"], bordercolor=c["panel"],
                    arrowcolor=c["muted"])

        # Row stripes and emphasis tags (re-applied on theme change).
        if hasattr(self, "tree"):
            self.tree.tag_configure("odd", background=c["surface"], foreground=c["fg"])
            self.tree.tag_configure("even", background=c["stripe"], foreground=c["fg"])
            self.tree.tag_configure("overridden", foreground=c["accent"])

        if hasattr(self, "theme_btn"):
            self.theme_btn.configure(text=c["toggle_label"])

    # ----- UI construction -------------------------------------------------
    def _build_header(self):
        header = ttk.Frame(self.root, style="Header.TFrame", padding=(16, 12))
        header.pack(side=tk.TOP, fill=tk.X)

        text = ttk.Frame(header, style="Header.TFrame")
        text.pack(side=tk.LEFT)
        ttk.Label(text, text="Zeo → Oscar", style="Title.TLabel").pack(anchor="w")
        ttk.Label(text, text="Decode, correct sleep times, and export for Oscar.",
                  style="Subtitle.TLabel").pack(anchor="w")

        self.theme_btn = ttk.Button(header, style="Toggle.TButton",
                                    command=self.toggle_theme)
        self.theme_btn.pack(side=tk.RIGHT, anchor="e")

        sep = ttk.Separator(self.root, orient=tk.HORIZONTAL)
        sep.pack(side=tk.TOP, fill=tk.X)

    def _build_toolbar(self):
        bar = ttk.Frame(self.root, style="Toolbar.TFrame", padding=(16, 12))
        bar.pack(side=tk.TOP, fill=tk.X)
        bar.columnconfigure(1, weight=1)

        ttk.Label(bar, text="Zeo .DAT", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(bar, textvariable=self.dat_path).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(bar, text="Browse…", command=self.browse_dat).grid(row=0, column=2)

        ttk.Label(bar, text="Decoder jar", style="Field.TLabel").grid(
            row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(bar, textvariable=self.jar_path).grid(
            row=1, column=1, sticky="ew", padx=8, pady=(8, 0))
        ttk.Button(bar, text="Browse…", command=self.browse_jar).grid(
            row=1, column=2, pady=(8, 0))

        actions = ttk.Frame(bar, style="Toolbar.TFrame")
        actions.grid(row=0, column=3, rowspan=2, padx=(20, 0), sticky="e")
        ttk.Button(actions, text="Decode .DAT", command=self.decode).pack(side=tk.LEFT, padx=3)
        ttk.Button(actions, text="Load CSV…", command=self.load_csv).pack(side=tk.LEFT, padx=3)
        ttk.Separator(actions, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=2)
        ttk.Button(actions, text="Select all", command=lambda: self.set_all(True)).pack(side=tk.LEFT, padx=3)
        ttk.Button(actions, text="Select none", command=lambda: self.set_all(False)).pack(side=tk.LEFT, padx=3)
        ttk.Button(actions, text="Generate Oscar CSV…", style="Accent.TButton",
                   command=self.generate).pack(side=tk.LEFT, padx=(10, 0))

    def _build_table(self):
        frame = ttk.Frame(self.root, padding=(16, 4, 16, 8))
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
        ttk.Label(self.root, textvariable=self.status, style="Status.TLabel",
                  anchor="w", padding=(16, 7)).pack(side=tk.BOTTOM, fill=tk.X)

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
        for index, record in enumerate(records):
            tag = "even" if index % 2 else "odd"
            item = self.tree.insert("", tk.END, values=self._row_values(record), tags=(tag,))
            self.item_to_record[item] = record
        self.status.set(f"{source}: {len(records)} night(s).")

    def _row_values(self, record: zc.SleepRecord) -> list:
        values = []
        for cid, _, _ in DISPLAY_COLUMNS:
            if cid == "sel":
                values.append(CHECK_ON if record.selected else CHECK_OFF)
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
