# zeo2oscar

Decode [Zeo](https://en.wikipedia.org/wiki/Zeo,_Inc.) sleep records and prepare
them for upload to [OSCAR](https://www.sleepfiles.com/OSCAR/).

The Zeo `.DAT` file is decoded with the bundled `ZeoDataDecoder.jar`, but its
output needs two fixes before OSCAR will accept it. `zeo2oscar` applies those
fixes automatically, lets you pick which nights to export and tweak any time by
hand, then writes a clean CSV.

## What it does

When you run it, the tool:

1. Decodes `ZEOSLEEP.DAT` with `ZeoDataDecoder.jar` (no manual `java` command
   needed).
2. Corrects the Start of Night / End of Night / Rise Time columns (see
   [Corrections](#corrections)).
3. Shows every night with its **original** and **corrected** times, lets you
   **select** which nights to export and **override** any corrected time.
4. Flags any night whose corrected times are not chronologically valid (the
   Start of Night must fall before the End of Night) so you can fix it before
   exporting — shown as a red date in the GUI and a `!` marker in `--list`.
5. Writes an OSCAR-ready CSV containing just the nights you chose.

## Requirements

- **Python 3.8+** (standard library only — no `pip install` needed).
- **Java** (a JRE such as OpenJDK) on your `PATH`, to run the decoder.
- **Tkinter** for the GUI. It ships with most Python installs; on Debian/Ubuntu
  install it with `sudo apt install python3-tk`. The command-line interface
  works without Tkinter.

## Usage

### GUI (default)

```bash
python main.py
```

This opens a window listing each night. Tick the nights you want, edit any
corrected time directly in its field if needed, then click
**Generate output CSV...**. Use **Decode .DAT...** or **Open CSV...** to load a
different file.

### Command line

The same functionality without a display — handy for scripting:

```bash
# Show every night with original -> corrected times
python main.py --list

# Export specific nights
python main.py --days "05/30/2026,05/31/2026" --out oscar.csv

# Export every night
python main.py --all --out oscar.csv

# Work from an already-decoded CSV instead of decoding the .DAT
python main.py --csv zeosleep.csv --all --out oscar.csv
```

Run `python main.py --help` for all options (`--dat`, `--jar`, `--tz`, ...).

## Corrections

The decoder's time columns have two issues, both handled automatically:

| Column         | Fix                                                              |
| -------------- | --------------------------------------------------------------- |
| Start of Night | **+5 hours**, then **+12 hours** (evening time in 12-hour form) |
| End of Night   | **+5 hours**                                                    |
| Rise Time      | **+5 hours**                                                    |

- The **+5 hours** undoes a timezone shift in the decoder. To keep the decode
  reproducible on any machine, the JVM timezone is pinned to `Etc/GMT+5` (UTC-5)
  when decoding, which exactly reproduces the project's reference output.
  Override it with `--tz` if your data was recorded elsewhere.
- The **+12 hours** on Start of Night converts an evening bedtime that the
  decoder wrote in 12-hour notation (e.g. `06:50` meaning 6:50 PM) into proper
  24-hour time (`23:50`).

These rules are verified against `zeosleep_corrected.csv`: the `05/31/2026`
record decodes to a Start of Night of `06:50` and corrects to `23:50`, with End
`03:48 → 08:48` and Rise `03:50 → 08:50`. If a particular night needs a
different value, override it in the GUI.

## Project layout

```
main.py                 Launcher (python main.py)
zeo2oscar/
  corrections.py        Time-correction rules
  decoder.py            Runs ZeoDataDecoder.jar, parses CSV
  records.py            Night / NightCollection model + CSV export
  cli.py                Command-line interface
  gui.py                Tkinter application
tests/                  Unit + end-to-end tests
ZeoDataDecoder.jar      Bundled decoder
ZEOSLEEP.DAT            Example input
zeosleep.csv            Example raw decoder output
zeosleep_corrected.csv  Example hand-corrected output (reference)
```

## Running the tests

```bash
python -m unittest discover -s tests
```

The suite covers the correction rules, the data model and CSV export, and —
when Java is available — an end-to-end decode of `ZEOSLEEP.DAT` that confirms the
corrected output matches `zeosleep_corrected.csv`.
