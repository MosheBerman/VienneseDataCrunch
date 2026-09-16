# Lehmann OCR Pipeline

Scripts for the 1938/1942 Lehmann directory OCR pipeline: page splitting,
column extraction, and map building.

## Splitter

- `split7_production.py` — 7-column divider detection. Two modes:
  - Standard: ~135px column pitch
  - Wide: ~225px column pitch (IV. Teil loose layout)
  - Includes binding-gutter perspective correction (dewarp) via
    `detect_binding_side()` + `dewarp_gutter_column()`.
- `split7_prod_ivteil.py` — Wrapper: PNG in, 7 column crops out, frames to JSONL.
  Tries standard, falls back to wide. Applies gutter dewarp when detected.
- `split7.py` — Base utilities (content edge detection, etc.).

## OCR

- `prod_ocr_ivteil.sh` — Batch OCR worker (tesseract, 200 DPI, frk+deu, psm 4).
- `requeue_failed.sh` — Retests failed pages, requeues those that now split.
- `setup-ocr.sh` — Installs tesseract + frk model (re-run after VM replacement).

## Map build

- `build_mapbox.py` — Regenerates the site from parsed OCR output.
  Re-inject the Mapbox token after every rebuild (replaces `__MAPBOX_TOKEN__`).

## Data (not in git)

The following are gitignored: PDFs, raw page PNGs, OCR text output,
progress logs, crop frames. Only scripts are versioned.
