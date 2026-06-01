# Zeo → Oscar

Decode Zeo `.DAT` sleep records, fix the decoder's timestamp bugs, pick which
nights to keep, and export an Oscar-ready CSV.

## Requirements

- **Python 3.9+** with Tkinter (bundled with the standard python.org installers
  on Windows and macOS; on Debian/Ubuntu install `python3-tk`).
- **Java** on your `PATH` (needed by `ZeoDataDecoder.jar`).

## Running the app

```sh
python3 zeo_oscar.py
```

On launch it looks for `ZEOSLEEP.DAT` and `ZeoDataDecoder.jar` next to the
script and decodes automatically. You can also point it at other files with the
**Browse…** buttons, then **Decode .DAT**. If you already have a decoder CSV,
use **Load CSV…** instead.

For each night the table shows the original Start of Night / End of Night /
Rise Time alongside the auto-corrected values:

- **Tick the "Export" box** (single click) to include a night in the output.
  Use *Select all* / *Select none* for bulk changes.
- **Double-click a "corrected" cell** to override the time. Enter it as
  `MM/DD/YYYY HH:MM` (e.g. `05/31/2026 23:50`); press Enter to save, Esc to
  cancel.
- **Generate Oscar CSV…** writes the selected nights to a CSV with every
  original column preserved and only the three time columns corrected.

## How the times are corrected

`ZeoDataDecoder.jar` emits three timestamps that need fixing (see `README.txt`):

1. **+5 hours** is added to Start of Night, End of Night and Rise Time.
2. A timestamp that **falls before midnight** — detected when its date is
   earlier than that night's End of Night date, which is normally just the
   Start of Night — gets an **additional +12 hours** to fix the missing
   24-hour/PM notation.

Example (from `zeosleep_corrected.csv`):

| Field          | Decoder output      | Corrected           |
|----------------|---------------------|---------------------|
| Start of Night | `05/31/2026 06:50`  | `05/31/2026 23:50`  |
| End of Night   | `06/01/2026 03:48`  | `06/01/2026 08:48`  |
| Rise Time      | `06/01/2026 03:50`  | `06/01/2026 08:50`  |

> **Note on timezones:** the decoder renders times in your computer's local
> timezone, so the raw output (and thus the +5h rule) assumes the same
> environment you have always used. If a corrected time ever looks off by an
> hour (e.g. daylight-saving boundaries), just override it in the table.

## Project layout

- `zeo_oscar.py` — the Tkinter GUI application.
- `zeo_core.py` — decoding, timestamp correction and CSV writing (no GUI).
- `test_zeo_core.py` — tests, validated against `zeosleep_corrected.csv`.

Run the tests with:

```sh
python3 test_zeo_core.py
```
