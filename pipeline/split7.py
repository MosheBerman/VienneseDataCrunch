"""7-column splitter for Band 2 Häuserverzeichnis (Teil IV).
Traces divider lines (which slant with page curvature) and splits along them.
Detects content edges to exclude binding shadow / adjacent page.
Includes header crop (top 15%) for street/district identification.

Page structure (per Moshe's visual analysis):
- Page header: first street (center) + last street (right) + district numeral, like dictionary guide words
- Inline header type 1: plain street name (e.g., "Trummelhofgasse") - starts new street section
- Inline header type 2: arrows (e.g., "→ Simmelgasse →") - indicates cross street
"""
from PIL import Image
import numpy as np

MARGIN = 6  # px inset from divider
HEADER_FRAC = 0.15  # top 15% is header

def find_content_edges(im):
    """Find left/right content boundaries, excluding shadow and adjacent page.
    
    Two cases (per Moshe):
    - (a) Other page visible: other page | shadow/gap | our page
    - (b) Shadow flush: shadow | our page
    
    In both cases, find the RIGHTMOST shadow region; content starts after it.
    Similarly for right edge: find LEFTMOST shadow region from right; content ends before it.
    
    Returns (left_x, right_x).
    """
    w, h = im.size
    a = np.array(im.convert('L'))
    
    # Use middle vertical band (avoid header/footer)
    y0, y1 = int(h*0.3), int(h*0.7)
    band = a[y0:y1, :]
    
    col_mean = band.mean(axis=0)
    col_std = band.std(axis=0)
    
    # Shadow: dark (mean < 100) and uniform (std < 20)
    is_shadow = (col_mean < 100) & (col_std < 20)
    
    # Find left edge: rightmost shadow in left third, content starts after
    left_third = w // 3
    left_x = 0
    # Find the rightmost contiguous shadow region in left third
    in_shadow = False
    last_shadow_end = 0
    for x in range(left_third):
        if is_shadow[x]:
            if not in_shadow:
                in_shadow = True
        else:
            if in_shadow:
                in_shadow = False
                last_shadow_end = x
    # Content starts after the last shadow region
    # If no shadow found, start at 0 (but skip pure scan background)
    if last_shadow_end > 0:
        left_x = last_shadow_end
    else:
        # No shadow: find first non-background (not uniform light)
        for x in range(left_third):
            if col_std[x] > 15 or col_mean[x] < 180:
                left_x = x
                break
    
    # Find right edge: leftmost shadow in right third, content ends before
    right_third_start = 2 * w // 3
    right_x = w
    in_shadow = False
    first_shadow_start = w
    for x in range(w-1, right_third_start-1, -1):
        if is_shadow[x]:
            if not in_shadow:
                in_shadow = True
                first_shadow_start = x
        else:
            if in_shadow:
                in_shadow = False
                break
    if first_shadow_start < w:
        right_x = first_shadow_start
    else:
        # No shadow: find last non-background
        for x in range(w-1, right_third_start-1, -1):
            if col_std[x] > 15 or col_mean[x] < 180:
                right_x = x + 1
                break
    
    return left_x, right_x

def find_gutter_x(im_array, y_center, x_min, x_max, band_half=30):
    """Find gutter (divider) X at a specific Y.
    Returns X of minimum dark-pixel density in [x_min, x_max].
    """
    h, w = im_array.shape
    y0 = max(0, y_center - band_half)
    y1 = min(h, y_center + band_half)
    x0 = max(0, x_min)
    x1 = min(w, x_max)
    
    band = im_array[y0:y1, x0:x1]
    dark = (band < 128).sum(axis=0).astype(float)
    kernel = np.ones(9)/9
    smooth = np.convolve(dark, kernel, mode='same')
    min_idx = int(np.argmin(smooth))
    return x0 + min_idx

def trace_dividers(im, n_cols=7):
    """Trace divider lines from top to bottom.
    Returns list of dividers, each is a list of (y, x) points (polyline).
    Uses 9 Y samples with outlier rejection for robustness against curvature.
    """
    w, h = im.size
    a = np.array(im.convert('L'))
    
    # Find approximate divider positions using middle band
    y0, y1 = int(h*0.4), int(h*0.6)
    band = a[y0:y1, :]
    dark = (band < 128).sum(axis=0).astype(float)
    kernel = np.ones(15)/15
    smooth = np.convolve(dark, kernel, mode='same')
    
    left_edge, right_edge = find_content_edges(im)
    col_width = 135
    
    search_start = left_edge + 20
    search_end = min(right_edge, int(left_edge + col_width * 1.2))
    region = smooth[search_start:search_end]
    minima = []
    for x in range(1, len(region)-1):
        if region[x] < region[x-1] and region[x] < region[x+1]:
            minima.append((region[x], search_start + x))
    if not minima:
        return []
    minima.sort()
    first_approx = minima[0][1]
    
    def gutter_at_y(y_center, x_min, x_max, band_half=25):
        y0_ = max(0, y_center - band_half)
        y1_ = min(h, y_center + band_half)
        b = a[y0_:y1_, max(0,x_min):min(w,x_max)]
        d = (b < 128).sum(axis=0).astype(float)
        k = np.ones(9)/9
        s = np.convolve(d, k, mode='same')
        return max(0,x_min) + int(np.argmin(s))
    
    # Sample at 9 Y positions from 15% to 85%
    y_samples = [int(h*f) for f in [0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.8, 0.85]]
    
    dividers = []  # each is list of (y, x)
    for i in range(n_cols - 1):
        approx_x = int(first_approx + col_width * i)
        x_min = max(0, approx_x - 30)
        x_max = min(w, approx_x + 30)
        
        points = []
        for y in y_samples:
            x = gutter_at_y(y, x_min, x_max)
            points.append((y, x))
        
        # Outlier rejection: median filter
        xs = [x for y, x in points]
        med = np.median(xs)
        # Keep points within 20px of median, or if too few, keep all
        filtered = [(y, x) for y, x in points if abs(x - med) <= 20]
        if len(filtered) < 5:
            filtered = points
        
        dividers.append(filtered)
    
    return dividers

def split_7col(im):
    """Split into 7 columns, handling slanted dividers.
    Returns (cols, header, dividers).
    cols: list of PIL Images (straightened columns)
    header: PIL Image (top 15%)
    dividers: list of (x_top, x_bottom) tuples
    """
    w, h = im.size
    dividers = trace_dividers(im, 7)
    
    # Header crop (top 15%)
    header_y1 = int(h * HEADER_FRAC)
    header = im.crop((0, 0, w, header_y1))
    
    if len(dividers) != 6:
        # Fallback: simple split (should not happen)
        return [], header, []
    
    # Content edges
    left_edge, right_edge = find_content_edges(im)
    
    # Build divider X positions as functions of Y (linear interpolation)
    # dividers[i] = (x_top, x_bot) for i=0..5
    # Column boundaries:
    #   col0: left_edge to div0
    #   col1: div0 to div1
    #   ...
    #   col6: div5 to right_edge
    
    y_top = int(h * 0.25)
    y_bot = int(h * 0.75)
    
    def div_x_at_y(div_idx, y):
        """Get divider X at specific Y via linear interpolation."""
        x_top, x_bot = dividers[div_idx]
        if y <= y_top:
            return x_top
        if y >= y_bot:
            return x_bot
        frac = (y - y_top) / (y_bot - y_top)
        return int(x_top + frac * (x_bot - x_top))
    
    # Extract columns row-by-row to handle slant (straightening)
    cols = []
    col_y0 = header_y1
    col_y1 = int(h * 0.98)
    col_h = col_y1 - col_y0
    
    # We'll build each column as a rectangular image
    # For each y in [col_y0, col_y1), find left/right X, extract row segment
    
    im_array = np.array(im.convert('RGB'))
    
    for col_idx in range(7):
        # Determine left/right divider indices
        # For each y, compute x_left(y) and x_right(y)
        
        # We'll create output image of width = max column width, height = col_h
        # First pass: find max width
        max_w = 0
        for y in range(col_y0, col_y1):
            if col_idx == 0:
                x_l = left_edge
            else:
                x_l = div_x_at_y(col_idx - 1, y)
            if col_idx == 6:
                x_r = right_edge
            else:
                x_r = div_x_at_y(col_idx, y)
            # Apply margin
            x_l += MARGIN
            x_r -= MARGIN
            max_w = max(max_w, x_r - x_l)
        
        # Create output image
        col_img = Image.new('RGB', (max_w, col_h), color='white')
        col_array = np.array(col_img)
        
        # Second pass: extract rows
        for out_y, y in enumerate(range(col_y0, col_y1)):
            if col_idx == 0:
                x_l = left_edge + MARGIN
            else:
                x_l = div_x_at_y(col_idx - 1, y) + MARGIN
            if col_idx == 6:
                x_r = right_edge - MARGIN
            else:
                x_r = div_x_at_y(col_idx, y) - MARGIN
            
            # Extract row segment
            if x_r > x_l and x_l >= 0 and x_r < w:
                row = im_array[y, x_l:x_r, :]
                # Place in output (left-aligned)
                rw = x_r - x_l
                if rw > 0:
                    col_array[out_y, 0:rw, :] = row
        
        cols.append(Image.fromarray(col_array))
    
    return cols, header, dividers

if __name__ == '__main__':
    import sys
    im = Image.open(sys.argv[1])
    cols, header, dividers = split_7col(im)
    print(f'Dividers (top, bottom): {dividers}')
    print(f'Columns: {len(cols)}')
    left, right = find_content_edges(im)
    print(f'Content edges: {left} to {right}')
