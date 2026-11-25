# Vienna deportation transport lists (Arolsen Archives)

Scans of the Vienna transport lists, Arolsen Archives unit **VCC.155.IV**,
"Deportations from the Gestapo area Vienna (1939-1945)", fetched from the
Arolsen online archive for transcription work.

## What is here

- `fetch_arolsen.py` — fetches one transport's page images from its
  archive page. Usage:
  `python3 fetch_arolsen.py <reference-code> <output-dir>`
  e.g. `python3 fetch_arolsen.py 12114001 transport-01-opole-1941-02-15`.
  Sequential downloads with a pause; re-running resumes (existing files
  are skipped). Each output folder gets a `manifest.json` pairing every
  page with its Arolsen document number and source URLs.
- `transport-01-opole-1941-02-15/` — Transport 1, Vienna to Opole,
  15 Feb 1941. Reference code 12114001, 30 pages, Arolsen document
  numbers 130500826-130500855. Fetched 2026-11-11.

The full unit holds the refreshed (DÖW cooperation, Oct 2020) lists for
Transports 1-48: about 1,453 pages in total, plus a separate set of old,
barely legible copies (1,699 pages). Further transports can be fetched
with the same script from their reference codes (12114002, 12114003, ...).

## License status — read before sharing or publishing

There is **no Creative Commons or public-domain license** on these
images. They are governed by the Arolsen Archives *General Terms of Use*
(24 Nov 2022):

- **Section 6:** a document may be published without separate approval
  only if the original is held by the Arolsen Archives. For the Vienna
  transport lists the archive metadata states "Existence and location
  of originals: **Austrian State Archive**" — Arolsen holds copies (the
  legible scans and metadata were supplied by the DÖW in Oct 2020), so
  publication approval has to come from the Austrian State Archive.
- **Section 7:** before any publication, Arolsen must be notified of
  the medium and place of publication, a specimen copy is due within
  three months, the Arolsen citation format must be used, and —
  critically — **digital copies may not be passed on to third parties
  or integrated into another archive without Arolsen's consent**.
  Private, non-commercial use is permitted.

Consequences for this repo:

- The downloaded JPGs are **gitignored** (`transports/**/*.jpg` in
  `.gitignore`). They live in this folder locally for transcription
  work only and must not be committed or pushed to the public repo
  until the ÖStA publication approval and the Arolsen notification /
  consent questions are settled (see the transport permission drafts of
  2026-10-27 in the Lehmann map goal files).
- Transcriptions (names, birth dates, list numbers) are factual data;
  how they may be published is covered by the same permission track.

## Citation format (Arolsen, Sept 2019)

`[Title of document], [Archival Unit Number]/[Digital Document Number]/ ITS Digital Archive, Arolsen Archives`

Example, Transport 1, page 1:
Transport 1: Deportation from Vienna to Opole, 1941/02/15,
1.2.1.1/130500826/ ITS Digital Archive, Arolsen Archives
(originals: Austrian State Archive).
