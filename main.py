#!/usr/bin/env python3
"""Convenience launcher: ``python main.py`` opens the zeo2oscar GUI.

All command-line flags are forwarded to ``zeo2oscar.cli`` (run with --help).
"""

from zeo2oscar.cli import main

if __name__ == "__main__":
    main()
