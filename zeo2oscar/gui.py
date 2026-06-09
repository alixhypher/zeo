"""Tkinter GUI for reviewing and exporting corrected Zeo records.

The window shows one row per night with a checkbox to include it in the
output, the decoder's original Start/End/Rise times, and editable fields
pre-filled with the corrected times so any value can be overridden before
the OSCAR CSV is generated.
"""

from __future__ import annotations

import os
from typing import List, Optional

from . import decoder
from .corrections import parse_zeo_datetime
from .decoder import DecoderError
from .records import COL_END, COL_RISE, COL_START, Night, NightCollection

# Tkinter is imported lazily inside launch() so that importing this module
# (and the rest of the package) never fails on headless systems.


def launch(
    dat: str = decoder.DEFAULT_DAT,
    jar: str = decoder.DEFAULT_JAR,
    csv: Optional[str] = None,
    tz: str = decoder.DEFAULT_DECODE_TZ,
) -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except Exception as exc:  # pragma: no cover - depends on host
        print(f"error: GUI unavailable ({exc}). Use the command line instead.")
        return 1

    TIME_COLUMNS = (COL_START, COL_END, COL_RISE)

    class App:
        def __init__(self, root: "tk.Tk") -> None:
            self.root = root
            self.collection: Optional[NightCollection] = None
            self.dat = dat
            self.jar = jar
            self.csv = csv
            self.tz = tz
            self.include_vars: List[tk.BooleanVar] = []
            self.override_entries: List[dict] = []

            root.title("zeo2oscar - Zeo to OSCAR")
            root.geometry("1100x620")
            root.minsize(820, 420)

            self._build_toolbar()
            self._build_table_area()
            self._build_statusbar()

            self.root.after(100, self._initial_load)

        # ---- layout ----------------------------------------------------
        def _build_toolbar(self) -> None:
            bar = ttk.Frame(self.root, padding=(8, 6))
            bar.pack(side="top", fill="x")

            ttk.Button(bar, text="Decode .DAT...", command=self.choose_dat).pack(side="left")
            ttk.Button(bar, text="Open CSV...", command=self.choose_csv).pack(side="left", padx=(6, 0))
            ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
            ttk.Button(bar, text="Select all", command=lambda: self._set_all(True)).pack(side="left")
            ttk.Button(bar, text="Clear all", command=lambda: self._set_all(False)).pack(side="left", padx=(6, 0))
            ttk.Button(bar, text="Reset corrections", command=self._reset_overrides).pack(side="left", padx=(6, 0))
            ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
            ttk.Button(bar, text="Generate output CSV...", command=self.generate).pack(side="left")

        def _build_table_area(self) -> None:
            container = ttk.Frame(self.root)
            container.pack(side="top", fill="both", expand=True, padx=8)

            heads = ttk.Frame(container)
            heads.pack(side="top", fill="x")
            self._header_row(heads)

            canvas = tk.Canvas(container, highlightthickness=0)
            vbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=vbar.set)
            vbar.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)

            self.rows_frame = ttk.Frame(canvas)
            self._window = canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
            self.canvas = canvas

            self.rows_frame.bind(
                "<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
            )
            canvas.bind(
                "<Configure>",
                lambda e: canvas.itemconfig(self._window, width=e.width),
            )
            # Mouse-wheel scrolling.
            canvas.bind_all("<MouseWheel>", self._on_mousewheel)
            canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
            canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))

        def _header_row(self, parent: "ttk.Frame") -> None:
            labels = [
                ("Use", 5), ("Sleep Date", 12), ("ZQ", 5),
                ("Start: original", 18), ("-> corrected (editable)", 20),
                ("End: original", 18), ("-> corrected (editable)", 20),
                ("Rise: original", 18), ("-> corrected (editable)", 20),
            ]
            for col, (text, width) in enumerate(labels):
                ttk.Label(parent, text=text, width=width, anchor="w",
                          font=("TkDefaultFont", 9, "bold")).grid(row=0, column=col, padx=2, sticky="w")

        def _build_statusbar(self) -> None:
            self.status = tk.StringVar(value="Ready.")
            bar = ttk.Frame(self.root, padding=(8, 4))
            bar.pack(side="bottom", fill="x")
            ttk.Label(bar, textvariable=self.status, anchor="w").pack(side="left")

        # ---- data loading ---------------------------------------------
        def _initial_load(self) -> None:
            try:
                if self.csv and os.path.isfile(self.csv):
                    self._load(lambda: decoder.load_csv_file(self.csv),
                               f"Loaded CSV: {self.csv}")
                elif os.path.isfile(self.jar) and os.path.isfile(self.dat):
                    self._load(lambda: decoder.load_from_dat(self.dat, self.jar, tz=self.tz),
                               f"Decoded: {self.dat}")
                else:
                    self.set_status("Choose a .DAT file to decode, or open a CSV.")
            except DecoderError as exc:
                messagebox.showerror("Load failed", str(exc))
                self.set_status("Load failed. Use the toolbar to choose a file.")

        def _load(self, loader, message: str) -> None:
            fieldnames, rows = loader()
            self.collection = NightCollection.from_rows(fieldnames, rows)
            self._render_rows()
            self.set_status(f"{message}  ({len(self.collection.nights)} nights)")

        def choose_dat(self) -> None:
            path = filedialog.askopenfilename(
                title="Select Zeo .DAT file",
                filetypes=[("Zeo data", "*.DAT *.dat"), ("All files", "*.*")],
            )
            if not path:
                return
            try:
                self.dat = path
                self._load(lambda: decoder.load_from_dat(path, self.jar, tz=self.tz),
                           f"Decoded: {path}")
            except DecoderError as exc:
                messagebox.showerror("Decode failed", str(exc))

        def choose_csv(self) -> None:
            path = filedialog.askopenfilename(
                title="Open decoded CSV",
                filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
            )
            if not path:
                return
            try:
                self.csv = path
                self._load(lambda: decoder.load_csv_file(path), f"Loaded CSV: {path}")
            except DecoderError as exc:
                messagebox.showerror("Open failed", str(exc))

        # ---- rows ------------------------------------------------------
        def _render_rows(self) -> None:
            for child in self.rows_frame.winfo_children():
                child.destroy()
            self.include_vars = []
            self.override_entries = []

            assert self.collection is not None
            for index, night in enumerate(self.collection.nights):
                self._render_one(index, night)

        def _render_one(self, index: int, night: Night) -> None:
            include = tk.BooleanVar(value=night.selected)
            self.include_vars.append(include)

            def on_toggle(n=night, v=include):
                n.selected = v.get()
                self._update_count()

            ttk.Checkbutton(self.rows_frame, variable=include, command=on_toggle,
                            width=4).grid(row=index, column=0, padx=2, sticky="w")
            ttk.Label(self.rows_frame, text=night.sleep_date, width=12, anchor="w").grid(
                row=index, column=1, padx=2, sticky="w")
            ttk.Label(self.rows_frame, text=night.zq, width=5, anchor="w").grid(
                row=index, column=2, padx=2, sticky="w")

            entries = {}
            col = 3
            for column in TIME_COLUMNS:
                ttk.Label(self.rows_frame, text=night.original(column) or "(none)",
                          width=18, anchor="w").grid(row=index, column=col, padx=2, sticky="w")
                entry = ttk.Entry(self.rows_frame, width=20)
                entry.insert(0, night.corrected(column))
                entry.grid(row=index, column=col + 1, padx=2, sticky="w")
                entry.bind("<FocusOut>", lambda e, n=night, c=column, ent=entry: self._commit(n, c, ent))
                entries[column] = entry
                col += 2
            self.override_entries.append(entries)

        def _commit(self, night: Night, column: str, entry) -> None:
            value = entry.get().strip()
            default = night.default_corrected(column)
            try:
                if value:
                    parse_zeo_datetime(value)  # validate
                # Store as override only when it differs from the rule result.
                night.set_override(column, value if value != default else None)
            except ValueError:
                entry.configure(foreground="red")
                self.set_status(f"Invalid time '{value}'. Expected MM/DD/YYYY HH:MM.")
                return
            entry.configure(foreground="")
            # Visually flag user-overridden values.
            entry.configure(foreground="#0a58ca" if night.is_overridden(column) else "")

        def _set_all(self, value: bool) -> None:
            if not self.collection:
                return
            self.collection.select_all(value)
            for var in self.include_vars:
                var.set(value)
            self._update_count()

        def _reset_overrides(self) -> None:
            if not self.collection:
                return
            for night, entries in zip(self.collection.nights, self.override_entries):
                night.overrides.clear()
                for column, entry in entries.items():
                    entry.delete(0, "end")
                    entry.insert(0, night.default_corrected(column))
                    entry.configure(foreground="")
            self.set_status("Corrections reset to computed defaults.")

        # ---- output ----------------------------------------------------
        def _commit_all_visible(self) -> None:
            """Flush every entry widget into the model before exporting."""
            if not self.collection:
                return
            for night, entries in zip(self.collection.nights, self.override_entries):
                for column, entry in entries.items():
                    self._commit(night, column, entry)

        def generate(self) -> None:
            if not self.collection:
                messagebox.showinfo("Nothing to export", "Load some data first.")
                return
            self._commit_all_visible()
            selected = self.collection.selected
            if not selected:
                messagebox.showinfo("No nights selected",
                                    "Tick at least one night to include in the output.")
                return
            path = filedialog.asksaveasfilename(
                title="Save OSCAR CSV",
                defaultextension=".csv",
                initialfile="zeosleep_for_oscar.csv",
                filetypes=[("CSV", "*.csv")],
            )
            if not path:
                return
            try:
                count = self.collection.write_output(path, only_selected=True)
            except (OSError, ValueError) as exc:
                messagebox.showerror("Export failed", str(exc))
                return
            self.set_status(f"Wrote {count} night(s) to {path}")
            messagebox.showinfo("Export complete", f"Wrote {count} night(s) to:\n{path}")

        # ---- misc ------------------------------------------------------
        def _on_mousewheel(self, event) -> None:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _update_count(self) -> None:
            if not self.collection:
                return
            total = len(self.collection.nights)
            chosen = len(self.collection.selected)
            self.set_status(f"{chosen} of {total} night(s) selected.")

        def set_status(self, text: str) -> None:
            self.status.set(text)

    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0
