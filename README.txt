# Zeo to Oscar CSV Exporter

This project streamlines the transfer of Zeo sleep records into Oscar. It wraps
the provided `ZeoDataDecoder.jar`, corrects the timestamps that Oscar needs, and
lets you choose which nights to export.

## Problem being solved

The raw `ZeoDataDecoder.jar` CSV has two timestamp issues for Oscar imports:

1. `Start of Night`, `End of Night`, and `Rise Time` need a 5-hour correction.
2. `Start of Night` values that are before midnight are emitted as if they were
   morning times, so the exporter first advances those start times by 12 hours
   before applying the 5-hour correction.

For example, the included `zeosleep.csv` row for `05/31/2026` contains:

- Original start: `05/31/2026 06:50`
- Corrected start: `05/31/2026 23:50`
- Original end: `06/01/2026 03:48`
- Corrected end: `06/01/2026 08:48`
- Original rise: `06/01/2026 03:50`
- Corrected rise: `06/01/2026 08:50`

`zeosleep_corrected.csv` is an example of a manually corrected export.

## Requirements

- Python 3.10 or newer
- Java, available as `java` on your `PATH`
- The provided files in this directory:
  - `ZeoDataDecoder.jar`
  - `ZEOSLEEP.DAT`

No third-party Python packages are required; the GUI uses the Python standard
library's Tkinter module.

## Run the GUI

```bash
python zeo_oscar.py
```

By default, the app decodes `ZEOSLEEP.DAT` with `ZeoDataDecoder.jar`, shows all
records in a table, and suggests corrected timestamp values. The Java decoder is
run with `TZ=Etc/GMT+5` so its output is stable and matches the decoder CSV shape
described above, regardless of your computer's local timezone or daylight-saving
settings.

In the GUI you can:

- Select or deselect nights for export.
- Compare original decoder times against corrected times.
- Double-click any corrected `Start of Night`, `End of Night`, or `Rise Time`
  value to manually override it.
- Click **Export CSV** to write an Oscar-ready CSV.

## Command-line usage

Export all decoded nights without opening the GUI:

```bash
python zeo_oscar.py --no-gui --output oscar_zeosleep.csv
```

Export selected dates only:

```bash
python zeo_oscar.py --no-gui --dates 05/31/2026 2026-05-30 --output oscar_zeosleep.csv
```

Use an existing decoder CSV instead of decoding the `.DAT` file:

```bash
python zeo_oscar.py --csv zeosleep.csv --no-gui --output oscar_zeosleep.csv
```

Use alternate input files:

```bash
python zeo_oscar.py --dat /path/to/ZEOSLEEP.DAT --decoder /path/to/ZeoDataDecoder.jar
```

Use the host timezone when running the Java decoder instead of the default fixed
UTC-5 decoder timezone:

```bash
python zeo_oscar.py --decoder-timezone "" --no-gui
```

Disable the 12-hour start-time fix if you are processing data that is already in
24-hour notation:

```bash
python zeo_oscar.py --no-start-pm-fix --no-gui
```

## Tests

```bash
python -m unittest -v
```
