#!/bin/bash
# Production OCR: Lehmann 1938 Band 2 IV. Teil (1289 pages)
# Native tesseract 5.5.1, 7-column split, crop frames recorded.
# Resumable via progress_ivteil/done.txt
# Batch mode: pass max pages as $1 (0/unset = unlimited). Designed for cron-driven
# runs — each invocation processes a batch and exits, so no long-lived daemon.
set -u
cd ~/workspace/lehmann-map

PDF="Lehmanns1938Band2-IVTeil.pdf"
PAGES_DIR="raw1938b2_iv"
COLS_DIR="cols1938b2_iv"
OCR_DIR="ocr1938b2_iv"
PROG="progress_ivteil/done.txt"
FAILED="progress_ivteil/failed.txt"
FRAMES="progress_ivteil/crop_frames.jsonl"
LOG="progress_ivteil/prod.log"
LOCKDIR="progress_ivteil/worker.lock"

mkdir -p "$PAGES_DIR" "$COLS_DIR" "$OCR_DIR" progress_ivteil
touch "$PROG" "$FAILED" "$FRAMES"

# Single-instance lock (mkdir is atomic). If another batch is running, exit quietly.
if ! mkdir "$LOCKDIR" 2>/dev/null; then
    exit 0
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null' EXIT

export TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata/
TESS="$HOME/workspace/lehmann-map/tesseract-builds/build-native/bin/tesseract"
DPI=200

# NOTE: stdout/stderr of this script are redirected to $LOG by the caller,
# so log() just echoes (no tee — tee caused every line to be written twice).
log() { echo "[$(date '+%H:%M:%S')] $*"; }

BATCH="${1:-0}"
TOTAL=1289
done_n=$(wc -l < "$PROG")
log "Starting IV Teil batch OCR: $done_n/$TOTAL done (batch limit: ${BATCH})"
processed=0

for (( p=1; p<=TOTAL; p++ )); do
    if [ "$BATCH" -gt 0 ] && [ "$processed" -ge "$BATCH" ]; then
        break
    fi
    scan=$((478 + p - 1))  # original scan number
    page_id="p${scan}"
    if grep -qx "$page_id" "$PROG" 2>/dev/null; then continue; fi
    if grep -qx "$page_id" "$FAILED" 2>/dev/null; then continue; fi
    mark_failed() { grep -qx "$page_id" "$FAILED" 2>/dev/null || echo "$page_id" >> "$FAILED"; }

    png="$PAGES_DIR/${page_id}.png"
    if [ ! -f "$png" ]; then
        pdftoppm -f "$p" -l "$p" -r "$DPI" -png -singlefile "$PDF" "${png%.png}" >/dev/null 2>&1
        # pdftoppm -singlefile with prefix foo writes foo.png
        if [ ! -f "$png" ] && [ -f "${png%.png}.png" ]; then mv "${png%.png}.png" "$png"; fi
        if [ ! -f "$png" ]; then log "EXTRACT FAIL $page_id"; mark_failed; processed=$((processed+1)); continue; fi
    fi

    # Split (records frames)
    if ! python3 split7_prod_ivteil.py "$png" "$COLS_DIR" "$page_id" "$FRAMES" >/dev/null 2>&1; then
        log "SPLIT FAIL $page_id"; mark_failed; processed=$((processed+1)); continue
    fi

    # OCR each column
    ok=1
    for ci in 0 1 2 3 4 5 6; do
        col="$COLS_DIR/${page_id}-c${ci}.png"
        [ -f "$col" ] || { ok=0; break; }
        "$TESS" "$col" "$OCR_DIR/${page_id}-c${ci}" -l frk+deu --psm 4 >/dev/null 2>&1 \
            || { ok=0; break; }
    done
    if [ "$ok" = 1 ]; then
        echo "$page_id" >> "$PROG"
        # Save disk: remove page png and column pngs after OCR (frames kept)
        rm -f "$png" "$COLS_DIR/${page_id}"-c*.png
    else
        log "OCR FAIL $page_id"; mark_failed
    fi
    processed=$((processed+1))

    done_n=$(wc -l < "$PROG")
    if [ $((done_n % 25)) -eq 0 ]; then
        log "Progress: $done_n/$TOTAL"
    fi
done

log "Batch done: $(wc -l < "$PROG")/$TOTAL pages ($processed attempted this run)"
