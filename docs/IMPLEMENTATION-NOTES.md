# Implementation notes and Phase 0 measurements

This file records what was built, the decisions taken, and the measured
bundle results.  It complements `DEV_PLAN.md` (the source plan) and
`README-GUI.md` (user documentation).

## Status against the plan

| Phase | Scope | Status |
|---|---|---|
| 0 | Feasibility: fork/pin upstream, Tk one-file build, measure size/startup | Done on Windows; the Linux build is defined in CI (no Linux host in this workspace) |
| 1 | `kicad_core` extraction, auth helpers, timeout, fixed upsert, parameterized SQL, tests | Done |
| 2 | Main window, theme, search, results, detail panel, mapping, add/update, DB open/create, auth dialog, worker queue, banners | Done |
| 3 | CSV validation/preview, batch worker, progress, cancel, 429/5xx backoff, log/summary | Done |
| 4 | Database tab: browse/filter, edit mapping, duplicate report, delete with confirmation | Done |
| 5 | Icons, PyInstaller spec, local build scripts, GitHub Actions, README, notices, checksums | Done (release run pending on CI/Linux) |

## Measured results (Windows 11, x64, Python 3.13.15, Tk 8.6)

Build tool: PyInstaller 6.22.3.  Measurements on the development workspace,
which is hosted on OneDrive and scanned by Windows Defender, so they are
pessimistic versus a local SSD.

| Artifact | Size | Self-test | Window shown + closed |
|---|---:|---:|---:|
| `KiCadLibGen-1.0.0-win64.exe` (one file) | **13.04 MB** | 6.67 s | **7.18 s** |
| One-dir fallback (`KiCadLibGenDir`) | 14.58 MB zipped | 0.86 s | **1.46 s** |
| Source run (`python gui_main.py --startup-test`) | — | 0.49 s | ~1.0 s |

- The **size target (≤30 MB)** is met comfortably: 13.0 MB one file.
- The **startup target (≤3 s)** is met by the one-dir build (1.7 s including a
  deliberate 0.25 s lifetime) but **not by the one-file build on this
  machine**.  One-file startup is dominated by extracting ~13 MB into
  `%TEMP%` while OneDrive/Defender scan the workspace.  A locally installed
  copy on a normal disk is expected to be faster, but the plan's fallback is
  the correct answer here: ship the one-dir ZIP alongside the one-file EXE.
- The session's default `%TEMP%` has a restrictive ACL that blocks PyInstaller's
  one-file extraction (`Could not create temporary directory`).  Verification
  therefore pointed `TEMP`/`TMP` at a writable workspace directory.  This is
  an environment constraint, not an application bug; one-file extraction
  works with a normal user `%TEMP%`.
- Because the workspace is OneDrive-hosted, the Tk `tcl8.6` files can
  occasionally be dehydrated; a GUI test then skips with "no display
  available".  Hydrating the Python install (or using a local, non-synced
  Python) makes the GUI tests deterministic.  The bundled executables carry
  their own Tcl/Tk copy and are unaffected.

## Decisions

1. **Repository shape** — this folder is the fork: the upstream CLI files
   (`kicad_cip.py`, `digikey_auth.py`, `digikey_search.py`, `colors.py`) are
   present, and `kicad_core/` is the shared, GUI-free extraction.  The CLI
   keeps its public names; `kicad_cip` re-exports the parser helpers.
2. **Database tab** — included, including delete with confirmation.
3. **Token storage** — plaintext JSON with mode `0600` on POSIX, atomic
   replace, and an inter-process lock during refresh.  No keyring in v1.
4. **Code signing** — none.  SHA256 files are generated; SmartScreen is
   documented as a known limitation.
5. **Linux range** — build on Ubuntu 22.04 in CI, target Ubuntu 22.04/24.04,
   Debian 12 and Fedora 40+ (X11/XWayland).  RHEL 8-era glibc is out of scope.
6. **Name** — `KiCad LibGen`, subtitle `Component Database Manager`.

## Behavioural changes from upstream

- **Upsert** is now explicit `UPDATE`-then-`INSERT` in `BEGIN IMMEDIATE`.
  Re-adding an MPN updates the record (and reports how many legacy duplicate
  rows were touched) instead of inserting a duplicate.
- **HTTP timeout** defaults to 30 s and is configurable; timeouts map to a
  friendly message.
- **Defensive parser**: missing keys become empty strings, `QuantityAvailable`
  missing becomes `"0"`, and more than 32 parameters are truncated.
- **OAuth** is split into reusable helpers with `state` validation, atomic
  token writes and a process lock; the CLI prompts remain.
- **Batch** adds pacing, 429/5xx exponential backoff, cancellation, a
  per-row error log and a summary; one bad row no longer aborts the CLI
  batch.
- **Schema comment** at the top of the CLI now matches the executed DDL (80
  columns, no `UNIQUE` index).

## Tests

`pytest` covers parser (fixtures, missing fields, truncation, value
overrides), auth (round-trip, refresh, expiry, state mismatch, atomic write),
database (80 columns, no duplicate on re-add, duplicate reporting, locked
database, quoted MPNs), search (401 refresh/retry, 403/429/5xx/timeout/JSON
mapping), batch (BOM/CRLF/quoted fields, header errors, skip/overwrite,
cancel, backoff, abort, log format), config paths/portable mode, the CLI
regression path, and GUI smoke tests that construct the real window, save a
part and browse the database.

Current result: **84 passed**.  `--self-test` also passes from source, from
the one-dir build, and from the one-file build.

## Packaging details

- `build/kicad_lib_gen_gui.spec` builds one file; `prompt_toolkit`, test and
  lint tooling are excluded.  Tk, `requests` and CA certificates are bundled.
- `build/build_windows.ps1` and `build/build_linux.sh` generate icons, run
  tests, build, self-test, measure and hash.
- `.github/workflows/build.yml` runs tests + lint on Windows and Ubuntu 22.04,
  builds both artifacts on tags/PRs, and publishes a release on `v*` tags.
- `build/make_assets.py` generates the 16/32 px toolbar icons and the app
  ICO/PNG; generated files are committed.

## Remaining risks / follow-ups

- Linux artifact has not been built on this machine; CI is authoritative.
- One-file startup on this workspace is above the plan target; distribute the
  one-dir ZIP as the fallback (works in 1.7 s and avoids temp extraction).
- Code signing and a keyring-backed token store remain v1.1 candidates.
- The OAuth browser copy/paste flow still depends on the user copying the
  `localhost:8000` URL; the dialog explains this in three steps.
