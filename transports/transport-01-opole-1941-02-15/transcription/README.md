# Transport 1 transcription — pilot (2026-11-11)

First-pass machine transcription of the Transport 1 list (Vienna → Opole,
15 Feb 1941), from the Arolsen scans in the parent folder. **Draft, not
verified data**: every row carries its raw OCR line and quality flags so a
reviewer can audit it against the scan.

## Deliverable

`../transport-01_transcription.csv` — 995 rows:
`list_no, page, surname, given_names, birth_date, surname_raw, surname_fix, flags, ocr_line`

Supporting files in `out/rowbox_full/`: the raw row table, per-page OCR
line dumps, and `review.csv` (the 808 rows carrying at least one flag).

## Pipeline (all local, zero cost)

1. `ocr_pilot.py` — engine comparison on page 1 against hand-checked
   ground truth (`ground_truth_page01.csv`, 34 rows). Vanilla full-page
   Tesseract was structurally unusable (margin noise, dropped lines).
2. `rowbox_ocr.py` — the winning approach:
   - **Deskew** (the scans are rotated ~2°; on page 1 the date column
     sits ~35 px lower than the name column, so un-deskewed strips slice
     through dates). Angle by projection sharpness.
   - Crop to the table; detect line bands by horizontal ink projection
     over the name column only (gaps are clean there); split merged
     bands at the ink valley.
   - OCR each strip (Tesseract, `deu`, psm 7) with fallbacks (psm 6 with
     taller padding, then Otsu strip) when a strip comes back non-row-like.
   - Parse with the printed list number as primary key: digit-confusion
     normalization (l/I→1, S→5…), Hamming-1 misread tolerance, explicit
     `gap_before` flags — rows are never silently renumbered.
3. `repair_pass.py` — number-zone and date-zone OCR with digit
   whitelists: filled 36 missing dates, recovered 12 rows whose numbers
   had been missed or misread into collisions (52, 57, 72, 187, 270,
   279, 304, 374, 401, 458, 477, 491).
4. `postprocess.py` — surname/given split (handles "BERMANN false
   LEHRHAUPT"), within-transport surname clustering (families travel in
   blocks; 179 variant spellings canonicalized, each recorded in
   `surname_fix`). No rows are dropped and no numbers renumbered at this
   stage: heuristics that tried either silently ate real rows, so the
   problems stay visible and flagged instead.

## Measured accuracy (page 1, 34 rows, hand-checked)

- Rows: 34/34. **Name CER 0.080, date CER 0.041** for the pipeline as run
  (before surname clustering, which only helps names).
- Whole transport: 995 rows over numbers 1–1003, no duplicates;
  **8 numbers not recovered** (204, 405, 414, 431, 434, 753, 894, 914);
  **134 rows (13%) have no parsed birth date** yet.

## Known defects (found by spot-checking pages 6 and 12 against the scans)

- **Closing sheets drift.** Each hundred ends with a short signed sheet
  (e.g. pp. 6, 12). There the sequential numbering can shift by one:
  on page 12 the block is offset from row 392, ELSTER Mika (399) is
  missing, and EISINGER Josefine appears at both 400 and 401. Page 30's
  tail is offset by +2 (printed numbers in `ocr_line` run 993–1000; the
  list's last printed number is 1000, the CSV's is 1003, and one
  signature band survives as a garbage row at 1003).
- Occasional **band misalignment**: rows 733/735 (page 22) hold the text
  of the following row.
- **Digit confusions** typical of this typewriter face: 3↔5 (several
  dates), 8→3 in number zones. Dates with a 5 in day/year are the least
  trustworthy.
- Surname clustering can over-merge distinct names (NAHLER→KANLER is
  doubtful); `surname_raw` always preserves the original reading.
- Row 189's date (31.12.1923) sits unparsed in the name field
  ("31.141923" defeated the date patterns).

## Follow-up experiments (2026-11-11, second pass)

- **Otsu strips**: binarizing each strip before OCR (vs grayscale)
  improved page-1 date CER 0.041 → 0.012 but worsened name CER
  0.080 → 0.094; on the two worst pages (23/24) it changed nothing
  material (page 24: 6/~40 dates parsed either way — its problem is
  print/scan quality, not thresholding). Not adopted wholesale; a
  date-zone-only Otsu read is the promising hybrid.
- **Scored clustering (v2)**: scoring v1's fixes (Jaro-Winkler +
  Levenshtein blend + frequency prior) showed only 28/179 high
  confidence, 108 low — v1 had chained unrelated names through garbage
  tokens (KOHN→ARON, SINGER→BERGER, WOLF→GOLPE). `postprocess.py` now
  applies only scored fixes (≥0.90, canonical attested in the Lehmann
  1940/41 surname index or ≥2× as frequent): **20 applied, all
  high-scoring on re-check; 25 weaker ones demoted to
  `surname_suggestion:` flags.** Analysis in `cluster_scores.py` /
  `out/cluster_scores.csv`.
- **Map cross-match** (`crossmatch.py`, `out/crossmatch.csv`): first
  against the 1940 (534,392) and 1941 (543,836) directory records —
  exact 13.0%, near1 8.8%, near2 53.2%, none 25.0%. Then extended to
  **1938 (481,219; lives in `data/`, not `data38/`) and 1939 (459,980)**,
  with given-name variants (the directories use Yiddish forms: Josef
  appears as "Jossel"): **exact 19.4% (193), near1 10.8%, near2 50.3%,
  none 19.6%**; 1938 alone contributed 26 exact matches found in no
  later year. Ceiling is still structural: only 48% of the transport's
  surnames appear in the 1941 directory at all (directories list heads
  of household), and exact matches are often ambiguous (3+ "Berger
  Josef" addresses). Near-1 "corrections" proved treacherous
  (PICK→Wick, SPIELMANN→Pilmann) and were NOT applied. Validation case:
  row 30's directory entry exists and is exact once the surname is
  read correctly — "Bermann Jossel, Wallensteinstraße 62, XX" (1938);
  the OCR garble BÜRHANN (distance 2 from BERMANN) is all that keeps
  the row at near2. The match file serves as candidate addresses per
  row and as the attestation source for clustering (widened to
  1938–1941 surnames: applied fixes 20 → 25, all high-scoring).
- **Surname-only match pass** (`crossmatch_surnames.py`,
  `out/crossmatch_surnames.csv`): dropping given names entirely —
  **exact surname attested in 1938–1941: 58.6% (583), near1 20.4%,
  near2 1.0%, none 20.0% (199)**. This is the working set for manual
  review: ~79% of rows have a directory-attested surname at distance
  ≤1. (Curiosity: exactly one LEHRHAUPT in all four years — Elfriede,
  Angestellte, Ziegelofengasse 41, V, 1941 only; relation to the
  family unverified.) The review page shows each row's surname tier
  and candidates, with filters for "not in directories" and
  "near-match only".
- **Review page** (`review/index.html`): every row with its scan crop
  (945/995 matched — by number-zone OCR anchors plus monotone order
  interpolation; 161 unassigned bands shown at the end), editable
  surname/given/date fields, filters (flagged, missing date, gaps,
  recovered, no crop), autosave to localStorage, and an Export button
  that downloads the corrected CSV. Crops are scan derivatives and stay
  gitignored like the page images.

## Next steps when this is picked up again

1. Work the review page (or `review.csv`), worst flags first
   (`gap_before`, `row_recovered`, `date_missing`).
2. Re-anchor each hundred-block to its printed numbers with a global
   pass (the printed number is in `ocr_line` for nearly every row).
3. Cross-check names/dates against DÖW/Yad Vashem person records —
   resolves most remaining date and surname uncertainty mechanically.
