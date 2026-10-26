#!/bin/bash
# Double-click to start the Forest Type Downloader (macOS).
# First run: sets up a private Python environment (needs internet, ~1 min).

cd "$(dirname "$0")" || exit 1
APP_DIR="$HOME/Library/Application Support/ForestTypeDownloader"
VENV="$APP_DIR/venv"

alert() {
  osascript -e "display dialog \"$1\" buttons {\"OK\"} default button 1 with icon caution with title \"Forest Type Downloader\"" >/dev/null 2>&1
  echo "$1"
}

# Prefer the python.org install (it ships a working Tk for the window)
PY=""
for c in /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
         /Library/Frameworks/Python.framework/Versions/3.*/bin/python3 \
         /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if [ -x "$c" ] && "$c" -c "import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >/dev/null 2>&1; then
    PY="$c"; break
  fi
done

if [ -z "$PY" ]; then
  alert "Python is needed once. Your browser will open the Python download page: click the yellow 'Download Python' button, install it, then double-click this file again."
  open "https://www.python.org/downloads/macos/"
  exit 1
fi

if ! "$VENV/bin/python" -c "import requests, tkinter" >/dev/null 2>&1; then
  echo "First-time setup, please wait..."
  rm -rf "$VENV"
  mkdir -p "$APP_DIR"
  if ! "$PY" -m venv "$VENV" || ! "$VENV/bin/python" -m pip install --quiet --disable-pip-version-check requests; then
    alert "Setup failed. Please check the internet connection and try again."
    exit 1
  fi
fi

echo "Starting Forest Type Downloader... (you can leave this window open)"
exec "$VENV/bin/python" forest_downloader_gui.py
