#!/usr/bin/env python3
"""Production 7-column splitter for Lehmann 1938 Band 2 IV. Teil.
Takes a page image path, splits into 7 columns, records crop frames.
Usage: python3 split7_prod_ivteil.py <input_png> <out_dir> <page_id> <frames_jsonl>
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from split7_production import (detect_dividers, detect_dividers_wide,
                               detect_binding_side, dewarp_gutter_column)
from PIL import Image
import numpy as np
import cv2

def split_image(im_path, out_dir, page_id, frames_path):
    os.makedirs(out_dir, exist_ok=True)
    im = Image.open(im_path).convert('RGB')
    w, h = im.size
    try:
        im_proc, divs, (left_edge, right_edge) = detect_dividers(im)
        mode = 'standard'
    except ValueError:
        im_proc, divs, (left_edge, right_edge) = detect_dividers_wide(im)
        mode = 'wide'
    ncols = 7
    ndiv = 6

    y_mid = h // 2
    div_x = [int(m * y_mid + b_) for m, b_ in divs]
    spacings = [div_x[i+1] - div_x[i] for i in range(ndiv - 1)]
    mean_sp = float(np.mean(spacings))
    left_edge = int(div_x[0] - mean_sp)
    right_edge = int(div_x[-1] + mean_sp)
    left_edge = max(0, left_edge)
    right_edge = min(w, right_edge)

    bounds = [None] + [(m, b_) for m, b_ in divs] + [None]

    # Record frames
    frame_rec = {
        'page_id': page_id,
        'ncols': ncols,
        'mode': mode,
        'img_w': w, 'img_h': h,
        'dividers': [{'m': float(m), 'b': float(b_)} for m, b_ in divs],
        'left_edge': left_edge, 'right_edge': right_edge,
        'mean_spacing': mean_sp,
        'columns': []
    }

    crops = []
    # Detect binding side for gutter dewarp (perspective correction)
    binding = detect_binding_side(im)
    # flat brightness reference from middle columns (never in gutter)
    flat_ref = None
    if binding:
        a_full = np.array(im.convert('L'))
        y0, y1 = int(h * 0.2), int(h * 0.9)
        mid = a_full[y0:y1, w // 3:2 * w // 3]
        flat_ref = float(np.percentile(mid, 92))

    for ci in range(ncols):
        def xl(y, ci=ci):
            if bounds[ci] is None: return left_edge
            m, b_ = bounds[ci]; return int(m * y + b_)
        def xr(y, ci=ci):
            if bounds[ci+1] is None: return right_edge
            m, b_ = bounds[ci+1]; return int(m * y + b_)
        xs_l = [xl(y) for y in range(0, h, 50)]
        xs_r = [xr(y) for y in range(0, h, 50)]
        x0c, x1c = min(xs_l), max(xs_r)
        x0c += 3; x1c -= 3  # inset to avoid divider
        x0c = max(0, x0c); x1c = min(w, x1c)
        crop = im.crop((x0c, 0, x1c, h))
        # Dewarp the gutter-side column (binding warp correction)
        dewarped = False
        dw_w = x1c - x0c
        if binding and flat_ref:
            is_gutter = (binding == 'right' and ci == ncols - 1) or \
                        (binding == 'left' and ci == 0)
            if is_gutter:
                crop = dewarp_gutter_column(crop, flat_ref)
                dewarped = True
                dw_w = crop.size[0]
        out = os.path.join(out_dir, f'{page_id}-c{ci}.png')
        crop.save(out)
        crops.append(out)
        frame_rec['columns'].append({
            'col': ci, 'x0': x0c, 'x1': x1c, 'width': x1c - x0c,
            'left_bound': 'edge' if bounds[ci] is None else {'m': float(bounds[ci][0]), 'b': float(bounds[ci][1])},
            'right_bound': 'edge' if bounds[ci+1] is None else {'m': float(bounds[ci+1][0]), 'b': float(bounds[ci+1][1])},
            'dewarped': dewarped,
            'dewarped_width': dw_w,
            'binding': binding,
        })
    with open(frames_path, 'a') as f:
        f.write(json.dumps(frame_rec) + '\n')
    return crops

if __name__ == '__main__':
    im_path, out_dir, page_id, frames_path = sys.argv[1:5]
    crops = split_image(im_path, out_dir, page_id, frames_path)
    print(f'{page_id}: wrote {len(crops)} crops', flush=True)
