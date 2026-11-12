#!/usr/bin/env bash
# Build the Linux one-file executable.
#
# Usage (from anywhere):
#   ./build/build_linux.sh
#   SKIP_TESTS=1 ./build/build_linux.sh
#
# Requires Python 3.13 with Tkinter (uv python install 3.13 is the easiest
# way to get one) and the packages in requirements-build.txt.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON="$ROOT/.venv/bin/python"
elif command -v python3.13 >/dev/null 2>&1; then
    PYTHON="python3.13"
else
    PYTHON="python3"
fi

echo "Using $PYTHON"
"$PYTHON" - <<'PY'
import sys, tkinter
assert sys.version_info >= (3, 13), sys.version
print("Python", sys.version.split()[0], "Tk", tkinter.TkVersion)
PY

if [[ "${SKIP_TESTS:-0}" != "1" ]]; then
    if "$PYTHON" -c "import pytest" >/dev/null 2>&1; then
        echo "Running tests..."
        "$PYTHON" -m pytest -q
    else
        echo "pytest not installed; skipping tests." >&2
    fi
fi

echo "Generating assets..."
"$PYTHON" build/make_assets.py

echo "Running PyInstaller..."
"$PYTHON" -m PyInstaller --clean --noconfirm build/kicad_lib_gen_gui.spec

VERSION="$("$PYTHON" -c "import version; print(version.__version__)")"
BUILT="$ROOT/dist/KiCadLibGen"
ARTIFACT="$ROOT/dist/kicad-lib-gen-${VERSION}-linux-x86_64"

if [[ ! -f "$BUILT" ]]; then
    echo "Expected build output not found: $BUILT" >&2
    exit 1
fi
mv -f "$BUILT" "$ARTIFACT"
chmod +x "$ARTIFACT"
SIZE_MB=$(du -m "$ARTIFACT" | cut -f1)
echo "Artifact: $ARTIFACT (${SIZE_MB} MB)"

echo "Self-test..."
"$ARTIFACT" --self-test

if command -v xvfb-run >/dev/null 2>&1; then
    echo "Smoke test under Xvfb..."
    xvfb-run -a "$ARTIFACT" --smoke-test
    echo "Measuring cold start (includes a 0.25 s deliberate lifetime)..."
    START=$(date +%s.%N)
    xvfb-run -a "$ARTIFACT" --startup-test
    END=$(date +%s.%N)
    awk -v s="$START" -v e="$END" 'BEGIN { printf "Cold start: %.2f s\n", e - s }'
fi

tar -C "$ROOT/dist" -czf "$ARTIFACT.tar.gz" "$(basename "$ARTIFACT")"
sha256sum "$ARTIFACT.tar.gz" | sed "s|$ROOT/dist/||" > "$ARTIFACT.tar.gz.sha256"
echo "Archive: $ARTIFACT.tar.gz"
echo "Done."
