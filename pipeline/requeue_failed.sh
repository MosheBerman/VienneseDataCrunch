#!/bin/bash
# Re-queue environmentally-failed pages: test-split each page in failed.txt
# with cv2 present; pages that split OK are removed from failed.txt so the
# batch runner retries them. Genuine splitter failures stay listed.
set -u
cd ~/workspace/lehmann-map
FAILED="progress_ivteil/failed.txt"
TMPDIR_RE="/tmp/requeue_test"
mkdir -p "$TMPDIR_RE/cols"
: > "$TMPDIR_RE/frames.jsonl"
: > "$TMPDIR_RE/requeued.txt"
: > "$TMPDIR_RE/stillbad.txt"

total=$(wc -l < "$FAILED")
i=0
while read -r pid; do
    i=$((i+1))
    png="raw1938b2_iv/${pid}.png"
    if [ ! -f "$png" ]; then
        echo "$pid" >> "$TMPDIR_RE/stillbad.txt"   # no source image; keep failed
        continue
    fi
    if python3 split7_prod_ivteil.py "$png" "$TMPDIR_RE/cols" "$pid" "$TMPDIR_RE/frames.jsonl" >/dev/null 2>&1; then
        echo "$pid" >> "$TMPDIR_RE/requeued.txt"
        rm -f "$TMPDIR_RE/cols/${pid}"-c*.png
    else
        echo "$pid" >> "$TMPDIR_RE/stillbad.txt"
    fi
    if [ $((i % 50)) -eq 0 ]; then echo "tested $i/$total"; fi
done < "$FAILED"

# Rewrite failed.txt keeping only still-bad pages (atomic via temp file)
cp "$FAILED" "$FAILED.bak"
grep -vxF -f "$TMPDIR_RE/requeued.txt" "$FAILED.bak" > "$FAILED"
echo "requeued: $(wc -l < "$TMPDIR_RE/requeued.txt"), still failed: $(wc -l < "$TMPDIR_RE/stillbad.txt")"
echo "failed.txt now: $(wc -l < "$FAILED") lines"
