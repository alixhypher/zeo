"""Run the bundled ``ZeoDataDecoder.jar`` and parse its CSV output."""

from __future__ import annotations

import csv
import io
import os
import shutil
import subprocess
from typing import List, Tuple

# Pinning the JVM timezone makes the decoder output reproducible across hosts.
# The decoder renders the device's timestamps in the local timezone, and the
# project's reference output (zeosleep.csv) was produced at a fixed UTC-5 (EST)
# offset.  ``Etc/GMT+5`` is UTC-5 with no daylight-saving shifts (note the
# inverted POSIX sign), reproducing that reference output exactly.
DEFAULT_DECODE_TZ = "Etc/GMT+5"

DEFAULT_JAR = "ZeoDataDecoder.jar"
DEFAULT_DAT = "ZEOSLEEP.DAT"


class DecoderError(RuntimeError):
    """Raised when the decoder cannot be run or fails."""


def find_java() -> str:
    """Return the path to the ``java`` executable, or raise DecoderError."""
    java = shutil.which("java")
    if not java:
        raise DecoderError(
            "Java runtime not found on PATH. Install a JRE (e.g. OpenJDK) to "
            "decode the .DAT file, or load an already-decoded CSV instead."
        )
    return java


def decode_dat(
    dat_path: str,
    jar_path: str = DEFAULT_JAR,
    *,
    tz: str = DEFAULT_DECODE_TZ,
    java_path: str | None = None,
    timeout: int = 120,
) -> str:
    """Decode a ``.DAT`` file and return the decoder's CSV output as text."""
    if not os.path.isfile(jar_path):
        raise DecoderError(f"Decoder jar not found: {jar_path}")
    if not os.path.isfile(dat_path):
        raise DecoderError(f"Input .DAT file not found: {dat_path}")

    java = java_path or find_java()
    cmd = [java, f"-Duser.timezone={tz}", "-jar", jar_path, dat_path]
    env = dict(os.environ, TZ=tz)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - defensive
        raise DecoderError(f"Decoder timed out after {timeout}s") from exc

    if result.returncode != 0:
        raise DecoderError(
            f"Decoder exited with status {result.returncode}:\n{result.stderr.strip()}"
        )
    if not result.stdout.strip():
        raise DecoderError("Decoder produced no output.")
    return result.stdout


def parse_csv_text(text: str) -> Tuple[List[str], List[dict]]:
    """Parse decoder CSV text into (fieldnames, list-of-row-dicts)."""
    reader = csv.reader(io.StringIO(text))
    rows = [row for row in reader if row and any(cell.strip() for cell in row)]
    if not rows:
        raise DecoderError("No rows found in decoder output.")
    fieldnames = rows[0]
    records = []
    for row in rows[1:]:
        # Pad/truncate defensively so a malformed row cannot break the mapping.
        padded = row + [""] * (len(fieldnames) - len(row))
        records.append(dict(zip(fieldnames, padded)))
    return fieldnames, records


def load_csv_file(path: str) -> Tuple[List[str], List[dict]]:
    """Load an already-decoded CSV file from disk."""
    if not os.path.isfile(path):
        raise DecoderError(f"CSV file not found: {path}")
    with open(path, "r", newline="", encoding="utf-8") as handle:
        return parse_csv_text(handle.read())


def load_from_dat(
    dat_path: str, jar_path: str = DEFAULT_JAR, **kwargs
) -> Tuple[List[str], List[dict]]:
    """Decode a ``.DAT`` file and parse the result in one step."""
    return parse_csv_text(decode_dat(dat_path, jar_path, **kwargs))
