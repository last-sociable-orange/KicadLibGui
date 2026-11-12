# Third-party notices

KiCad LibGen GUI is MIT licensed.  The one-file builds bundle the following
components; their licences are reproduced or summarised here for
redistribution.

| Component | Version | Licence | Notes |
|---|---|---|---|
| CPython | 3.13.x | PSF License 2.0 | Bundled by PyInstaller |
| Tcl/Tk | 8.6 | Tcl/Tk BSD-style | Bundled by PyInstaller |
| PyInstaller | 6.22.3 | GPLv2-or-later with a bundling exception | Build tool only; the exception permits distributing non-GPL applications |
| requests | 2.32+ | Apache 2.0 | HTTP client |
| urllib3 | 2.x | MIT | requests dependency |
| certifi | latest | MPL 2.0 | CA bundle |
| charset-normalizer | 3.x | MIT | requests dependency |
| idna | 3.x | BSD-3-Clause | requests dependency |
| prompt-toolkit | 3.x | BSD-3-Clause | CLI only; excluded from the GUI bundle |

The upstream project [last-sociable-orange/kicad_lib_gen](https://github.com/last-sociable-orange/kicad_lib_gen)
is MIT licensed; its `kicad_cip.py`, `digikey_auth.py`, `digikey_search.py`
and `colors.py` were refactored into this repository.

Full licence texts for CPython, Tcl/Tk, PyInstaller and the Python packages
are available in the PyInstaller bundle's licence metadata and in each
project's repository.  Release archives include this file and `LICENSE`.
