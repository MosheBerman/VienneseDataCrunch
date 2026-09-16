#!/usr/bin/env python3
"""
Production 7-column splitter for Band 2 IV. Teil.
CLAHE + nearperfect divider detection. Outputs 7 column crops per page.

Usage: python3 split7_production.py <scan_num> <out_dir>
  Renders scan page from Lehmanns1938Band2.pdf at 135 DPI,
  detects 6 dividers, saves 7 column PNGs as <out_dir>/p<scan>-c<i>.png
  Prints divider coords to stdout.
"""
import sys
import os
import subprocess
import math
import numpy as np
import cv2
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from split7 import find_content_edges

DPI = 135
PDF = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   'Lehmanns1938Band2.pdf')

def _find_candidates(im, n_keep=12):
    """Shared candidate detection. Returns (enh, h, w, xs, white_of, left_edge, right_edge)."""
    w, h = im.size
    a = np.array(im.convert('L'))
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enh = clahe.apply(a)
    left_edge, right_edge = find_content_edges(im)
    y_top, y_bot = int(h * 0.18), int(h * 0.92)
    x_left, x_right = left_edge + 20, right_edge - 20
    band = enh[y_top:y_bot, x_left:x_right]
    white = (band > 180).sum(axis=0).astype(float)

    candidates = []
    for i in range(80, len(white) - 80):
        x = x_left + i
        if white[i] > white[i-1] and white[i] > white[i+1] and white[i] > 50:
            candidates.append((white[i], x))
    candidates.sort(reverse=True)
    selected = []
    for val, x in candidates:
        if all(abs(x - sx) >= 80 for _, sx in selected):
            selected.append((val, x))
        if len(selected) == n_keep:
            break
    selected.sort(key=lambda t: t[1])
    xs = [x for _, x in selected]
    white_of = {x: v for v, x in selected}
    return enh, h, w, xs, white_of, left_edge, right_edge


def _refine_dividers(enh, h, w, gutter_x):
    """Refine divider x-positions with 5-point line fit. Returns list of (m, b)."""
    def gw(y_c, ax, sr=25, bh=50):
        y0_ = max(0, y_c - bh); y1_ = min(h, y_c + bh)
        x0 = max(0, ax - sr); x1 = min(w, ax + sr)
        b = enh[y0_:y1_, x0:x1]
        wf = (b > 180).sum(axis=0)
        return x0 + int(np.argmax(wf))

    ysamp = [int(h * f) for f in [0.25, 0.40, 0.55, 0.70, 0.85]]
    divs = []
    for gx in gutter_x:
        pts = [(y, gw(y, gx)) for y in ysamp]
        for _ in range(2):
            ys = np.array([y for y, x in pts])
            xs2 = np.array([x for y, x in pts])
            A = np.vstack([ys, np.ones(len(ys))]).T
            m, b_ = np.linalg.lstsq(A, xs2, rcond=None)[0]
            mask = np.abs(xs2 - (m * ys + b_)) <= 12
            if mask.sum() < 4:
                break
            pts = [(y, x) for (y, x), k in zip(pts, mask) if k]
        ys = np.array([y for y, x in pts])
        xs2 = np.array([x for y, x in pts])
        A = np.vstack([ys, np.ones(len(ys))]).T
        m, b_ = np.linalg.lstsq(A, xs2, rcond=None)[0]
        divs.append((m, b_))  # x = m*y + b_
    return divs


def detect_dividers(im):
    enh, h, w, xs, white_of, left_edge, right_edge = _find_candidates(im, n_keep=10)

    # Best 6 with consistent spacing
    best_seq, best_var = None, float('inf')
    for i in range(len(xs) - 5):
        seq = xs[i:i+6]
        sp = [seq[j+1] - seq[j] for j in range(5)]
        var = np.var(sp)
        if all(100 <= s <= 160 for s in sp) and var < best_var:
            best_var, best_seq = var, seq
    if best_seq is None:
        # Fallback: best 5 + extrapolate
        for i in range(len(xs) - 4):
            seq = xs[i:i+5]
            sp = [seq[j+1] - seq[j] for j in range(4)]
            var = np.var(sp)
            mean_sp = np.mean(sp)
            if 120 <= mean_sp <= 150 and var < best_var:
                best_var, best_seq = var, seq
        if best_seq is None:
            raise ValueError(f'No divider sequence in {xs}')
        mean_sp = np.mean([best_seq[i+1] - best_seq[i] for i in range(4)])
        gutter_x = list(best_seq)
        if best_seq[0] > left_edge + 150:
            gutter_x = [int(best_seq[0] - mean_sp)] + gutter_x
        elif best_seq[-1] < right_edge - 150:
            gutter_x = gutter_x + [int(best_seq[-1] + mean_sp)]
        gutter_x.sort()
    else:
        gutter_x = best_seq

    divs = _refine_dividers(enh, h, w, gutter_x[:6])
    return im, divs, (left_edge, right_edge)


def detect_dividers_wide(im):
    """Wide 7-column mode: 6 dividers with ~225px spacing.

    Used for IV. Teil pages where the 7 columns are set wider than
    standard (the book uses a looser layout on some pages). Same
    interface as detect_dividers: returns (im, divs, (left_edge, right_edge))
    with 6 (m, b) dividers. Raises ValueError if not found.
    """
    import itertools
    enh, h, w, xs, white_of, left_edge, right_edge = _find_candidates(im, n_keep=12)

    # 6 dividers -> 5 gaps, each in [180, 270].
    # Dividers must be strictly inside the content: the first divider has
    # to be at least 150px right of the content edge (excludes the edge
    # gutter, which is as white as a real divider), and the last at least
    # 150px left of the right content edge.
    best, best_score = None, float('inf')
    for combo in itertools.combinations(xs, 6):
        seq = sorted(combo)
        if seq[0] < left_edge + 150 or seq[-1] > right_edge - 150:
            continue
        gaps = [seq[i+1] - seq[i] for i in range(5)]
        if all(180 <= g <= 270 for g in gaps):
            var = float(np.var(gaps))
            score = var - 0.001 * sum(white_of[x] for x in seq)
            if score < best_score:
                best_score, best = score, seq
    if best is None:
        raise ValueError(f'No wide divider sequence in {xs}')
    divs = _refine_dividers(enh, h, w, best)
    return im, divs, (left_edge, right_edge)


def detect_dividers_8(im):
    """Alias kept for compatibility; use detect_dividers_wide."""
    return detect_dividers_wide(im)


def detect_binding_side(im):
    """Detect which side has the binding gutter (page curve).
    The gutter is a GRADUAL brightness dip located IN from the image edge
    (page curving into the spine), not a sharp shadow AT the edge.
    Returns 'left', 'right', or None.
    """
    w, h = im.size
    a = np.array(im.convert('L'))
    y0, y1 = int(h * 0.2), int(h * 0.9)
    bg = np.percentile(a[y0:y1, :], 92, axis=0).astype(float)
    bg = cv2.GaussianBlur(bg.reshape(1, -1), (1, 101), 0).flatten()
    flat = np.median(bg[w // 4:3 * w // 4])

    def gutter_strength(side):
        # search outer 300px for a brightness dip
        if side == 'left':
            seg, offset = bg[:300], 0
        else:
            seg, offset = bg[-300:], w - 300
        i_min = int(np.argmin(seg))
        x_min = offset + i_min
        drop = (flat - seg[i_min]) / flat
        # distance from image edge
        dist_edge = x_min if side == 'left' else (w - 1 - x_min)
        # gutter: significant dip (>0.15) located >30px in from edge
        if drop > 0.15 and dist_edge > 30:
            return drop
        return -1

    ls, rs = gutter_strength('left'), gutter_strength('right')
    if ls < 0 and rs < 0:
        return None
    return 'right' if rs > ls else 'left'


def dewarp_gutter_column(crop, flat_ref):
    """Dewarp a gutter-affected column crop via 1D horizontal remap.
    Stretches regions where background shading indicates page curve,
    using flat_ref as the undistorted brightness reference.
    Output is WIDER than input (gutter region expanded to true width).
    Returns dewarped PIL Image.
    """
    w, h = crop.size
    a = np.array(crop.convert('L'))
    y0, y1 = int(h * 0.2), int(h * 0.9)
    bg = np.percentile(a[y0:y1, :], 92, axis=0).astype(float)
    bg = cv2.GaussianBlur(bg.reshape(1, -1), (1, 31), 0).flatten()
    # stretch where shading indicates foreshortening
    stretch = np.clip(flat_ref / np.maximum(bg, 1), 1.0, 2.5)
    drop = (flat_ref - bg) / flat_ref
    stretch[drop < 0.05] = 1.0  # don't amplify noise in flat areas
    stretch = cv2.GaussianBlur(stretch.reshape(1, -1), (1, 15), 0).flatten()
    if np.all(stretch == 1.0):
        return crop  # no warp detected
    # Forward map: x_out(x_in) = integral of stretch. Output is wider.
    x_out = np.cumsum(stretch)
    x_out = x_out - x_out[0]  # start at 0
    out_w = int(np.ceil(x_out[-1])) + 1
    # Invert: for each output x, find the input x to sample
    in_x = np.interp(np.arange(out_w), x_out, np.arange(w))
    map_x = np.tile(in_x.astype(np.float32), (h, 1))
    map_y = np.tile(np.arange(h, dtype=np.float32).reshape(-1, 1), (1, out_w))
    dw = cv2.remap(np.array(crop), map_x, map_y, cv2.INTER_LINEAR)
    return Image.fromarray(dw)

def split_page(scan_num, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    tmp = f'/tmp/split7-prod-{scan_num}.png'
    subprocess.run(['pdftoppm', '-f', str(scan_num), '-l', str(scan_num),
                    '-r', str(DPI), '-png', '-singlefile', PDF, tmp[:-4]],
                   capture_output=True, check=True)
    im = Image.open(tmp + '.png') if os.path.exists(tmp + '.png') else Image.open(tmp)
    # pdftoppm -singlefile names it tmp (no .png) when given prefix without ext
    if not os.path.exists(tmp):
        # try with .png
        im = Image.open(tmp + '.png')
        os.rename(tmp + '.png', tmp)
    else:
        im = Image.open(tmp)
    w, h = im.size
    im, divs, (left_edge, right_edge) = detect_dividers(im)

    # Column boundaries: infer outer edges from measured divider spacing
    # (find_content_edges is unreliable for the right edge)
    # Get divider x at mid-height
    y_mid = h // 2
    div_x = [int(m * y_mid + b_) for m, b_ in divs]
    spacings = [div_x[i+1] - div_x[i] for i in range(5)]
    mean_sp = np.mean(spacings)
    left_edge = int(div_x[0] - mean_sp)
    right_edge = int(div_x[5] + mean_sp)
    left_edge = max(0, left_edge)
    right_edge = min(w, right_edge)

    bounds = []  # list of (m, b) or None for edges
    bounds.append(None)  # left edge = vertical at left_edge
    for m, b_ in divs:
        bounds.append((m, b_))
    bounds.append(None)  # right edge

    crops = []
    for ci in range(7):
        # x_left(y), x_right(y)
        def xl(y):
            if bounds[ci] is None:
                return left_edge
            m, b_ = bounds[ci]
            return int(m * y + b_)
        def xr(y):
            if bounds[ci+1] is None:
                return right_edge
            m, b_ = bounds[ci+1]
            return int(m * y + b_)
        # For slanted dividers, use min/max to get a rectangular crop
        # that contains the column (we'll mask, but rect is simpler for OCR)
        xs_l = [xl(y) for y in range(0, h, 50)]
        xs_r = [xr(y) for y in range(0, h, 50)]
        x0c, x1c = min(xs_l), max(xs_r)
        # 3px inset to avoid divider line (reverted 2026-09-15: the "no inset"
        # + whitening experiments raised CER from 0.34 to 0.59. The inset
        # gives the best overall CER; clipping edge cases are documented
        # in SPLITTER_ISSUES.md but don't justify breaking the measurement.)
        x0c += 3
        x1c -= 3
        crop = im.crop((max(0, x0c), 0, min(w, x1c), h))
        out = os.path.join(out_dir, f'p{scan_num}-c{ci}.png')
        crop.save(out)
        crops.append(out)
        m_info = 'edge' if bounds[ci] is None else f'{bounds[ci][0]:+.4f}'
        print(f'  col {ci}: x=[{x0c},{x1c}] w={x1c-x0c}', flush=True)
    os.remove(tmp)
    return crops

if __name__ == '__main__':
    scan = int(sys.argv[1])
    out_dir = sys.argv[2]
    print(f'Scan {scan}:', flush=True)
    crops = split_page(scan, out_dir)
    print(f'Wrote {len(crops)} crops to {out_dir}')
