"""zeo2oscar - decode Zeo sleep records and prepare them for upload to OSCAR.

The package turns the raw output of ``ZeoDataDecoder.jar`` into a clean CSV
whose Start of Night / End of Night / Rise Time columns have been corrected,
ready to import into OSCAR.

See ``corrections`` for the time-correction rules, ``decoder`` for running the
bundled Java decoder, ``records`` for the data model, ``cli`` for the headless
interface and ``gui`` for the Tkinter application.
"""

__version__ = "1.0.0"

__all__ = ["__version__"]
