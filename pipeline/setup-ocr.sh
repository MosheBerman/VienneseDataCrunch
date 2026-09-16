#!/bin/bash
# Restore tesseract + frk after a VM replacement (/usr is wiped, ~/workspace
# and /var/cache/apt/archives survive). Idempotent.
set -u
PROJ=~/workspace/lehmann-map
CACHE=/var/cache/apt/archives

if ! command -v tesseract >/dev/null 2>&1; then
  echo "tesseract missing, reinstalling..."
  if ls "$CACHE"/tesseract-ocr_5*.deb >/dev/null 2>&1; then
    echo "fast path: dpkg from apt cache"
    sudo dpkg -i "$CACHE"/libgif7_*.deb "$CACHE"/liblept5_*.deb \
      "$CACHE"/libtesseract5_*.deb 2>/dev/null
    sudo dpkg -i "$CACHE"/tesseract-ocr-eng_*.deb "$CACHE"/tesseract-ocr-osd_*.deb \
      "$CACHE"/tesseract-ocr-deu_*.deb 2>/dev/null
    sudo dpkg -i "$CACHE"/tesseract-ocr_5*.deb 2>/dev/null || \
      sudo apt-get install -f -y
  else
    echo "slow path: apt-get install"
    sudo apt-get update -qq 2>/dev/null || true
    sudo apt-get install -y -qq tesseract-ocr tesseract-ocr-deu
  fi
fi

TD=/usr/share/tesseract-ocr/5/tessdata
if [ ! -s "$TD/frk.traineddata" ] && [ -s "$PROJ/frk.traineddata" ]; then
  echo "restoring frk.traineddata from workspace backup"
  sudo cp "$PROJ/frk.traineddata" "$TD/frk.traineddata"
fi
tesseract --list-langs 2>&1 | tail -5
