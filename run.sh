#!/bin/bash
cd "$(dirname "$(readlink -f "$0")")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 is not installed. Install Python 3.10+ first."
  exit 1
fi

if [ ! -x venv/bin/python ]; then
  echo "[INFO] Creating virtual environment..."
  python3 -m venv venv || { echo "[ERROR] Could not create venv. On Debian/Ubuntu: sudo apt install python3-venv"; exit 1; }
fi

echo "[INFO] Installing required packages..."
venv/bin/pip install -q --upgrade pip
grep -v -i '^pyinstaller' requirements.txt | venv/bin/pip install -q -r /dev/stdin || exit 1

echo "[INFO] Launching Discord Quest Completer..."
cd src && exec ../venv/bin/python app.py "$@"
