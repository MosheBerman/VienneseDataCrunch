#!/usr/bin/env python3
"""Fetch document images for one Arolsen Archives archive unit.

The Arolsen online archive server-renders each archive page with one
thumbnail <img> per document, in list order, each paired with a link to
/en/document/<DocID>. This script parses that page, downloads the full
images in order, and writes a manifest.json next to them.

Usage:
    python3 fetch_arolsen.py <reference-code> <output-dir>

Example:
    python3 fetch_arolsen.py 12114001 transport-01-opole-1941-02-15

Notes:
- Images are downloaded for private, non-commercial research use under
  the Arolsen Archives General Terms of Use (24 Nov 2022). Section 7
  forbids passing digital copies to third parties or integrating them
  into another archive without Arolsen consent, so the downloaded JPGs
  are gitignored in this repo. See the transport folder README.
- Downloads are sequential with a short pause; re-running skips files
  that already exist with a plausible size (checkpoint / resume).
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (VienneseDataCrunch research fetch; contact: repo owner)"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    ref_code, out_dir = sys.argv[1], Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    archive_url = f"https://collections.arolsen-archives.org/en/archive/1-2-1-1_{ref_code}/"
    print(f"Archive page: {archive_url}")
    # The archive sometimes serves the bare SPA shell instead of the
    # server-rendered page; retry until the rendered document list is
    # present (it carries the /en/document/ links).
    html = ""
    for attempt in range(1, 7):
        html = fetch(archive_url).decode("utf-8", errors="ignore")
        if "/en/document/" in html:
            break
        print(f"Attempt {attempt}: shell page without document list, retrying...")
        time.sleep(8)
    if "/en/document/" not in html:
        print("ERROR: could not get the rendered archive page after retries.")
        return 1

    title_m = re.search(r"<title>(.*?)</title>", html, re.S)
    title = title_m.group(1).strip() if title_m else ""

    # Document links and image URLs in page order; the page interleaves
    # one image with one document link per document. Image URLs in the
    # server-rendered HTML have the "//" after https: backslash-escaped
    # (https:\\\\collections-server...), so the pattern tolerates
    # backslashes there; the rest of the path uses normal slashes.
    doc_ids = re.findall(r"/en/document/(\d+)", html)
    img_urls = re.findall(
        r"https:[\\/]+collections-server\.arolsen-archives\.org/[^\"' ]+?\.jpg", html
    )
    img_urls = [
        "https://collections-server" + u.split("collections-server", 1)[1]
        for u in img_urls
    ]
    # De-duplicate while preserving order (each appears twice in the HTML).
    doc_ids = list(dict.fromkeys(doc_ids))
    img_urls = list(dict.fromkeys(img_urls))
    print(f"Title: {title}")
    print(f"Documents found: {len(doc_ids)}, images found: {len(img_urls)}")
    if len(doc_ids) != len(img_urls):
        print("WARNING: document/image count mismatch; pairing by position anyway.")

    manifest = {
        "reference_code": ref_code,
        "archive_url": archive_url,
        "archive_title": title,
        "pages": [],
    }
    for i, (doc_id, img_url) in enumerate(zip(doc_ids, img_urls), start=1):
        fname = f"page-{i:02d}_doc-{doc_id}.jpg"
        dest = out_dir / fname
        entry = {
            "page": i,
            "doc_id": doc_id,
            "document_url": f"https://collections.arolsen-archives.org/en/document/{doc_id}",
            "image_url": img_url,
            "file": fname,
        }
        manifest["pages"].append(entry)
        if dest.exists() and dest.stat().st_size > 50_000:
            print(f"[{i}/{len(doc_ids)}] skip (exists) {fname}")
            continue
        data = fetch(img_url)
        dest.write_bytes(data)
        print(f"[{i}/{len(doc_ids)}] {fname}  {len(data)} bytes")
        time.sleep(0.5)

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Manifest: {out_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
