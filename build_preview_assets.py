#!/usr/bin/env python3
"""Build preview metadata assets for the VienneseDataCrunch site.

Outputs (in the repo root):
  og-image.png         1200x630 social preview, built on the real map screenshot
  favicon.svg          vector map-pin
  favicon.ico          multi-size raster pin (64/48/32/16)
  apple-touch-icon.png 180x180 pin on white
"""
from PIL import Image, ImageDraw, ImageFont
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
PIN_BLUE = (37, 99, 235)      # #2563eb
DARK = (17, 24, 39)           # #111827 (site brand bar)

def font(bold, size):
    name = "NotoSans-Bold.ttf" if bold else "NotoSans-Regular.ttf"
    p = f"/usr/share/fonts/truetype/noto/{name}"
    try:
        return ImageFont.truetype(p, size)
    except OSError:
        return ImageFont.load_default()

def draw_pin(d, cx, cy, r, color=PIN_BLUE):
    """Map pin: circle with a tapered point, white center dot."""
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    d.polygon([(cx - r * 0.72, cy + r * 0.35),
               (cx + r * 0.72, cy + r * 0.35),
               (cx, cy + r * 1.75)], fill=color)
    d.ellipse([cx - r * 0.42, cy - r * 0.42, cx + r * 0.42, cy + r * 0.42],
              fill=(255, 255, 255))

# ---------- og:image ----------
base = Image.open(os.path.join(ROOT, "screenshots", "map.png")).convert("RGB")
# cover-fit to 1200x630
tw, th = 1200, 630
scale = max(tw / base.width, th / base.height)
nw, nh = int(base.width * scale + 0.5), int(base.height * scale + 0.5)
base = base.resize((nw, nh), Image.LANCZOS)
x0 = (nw - tw) // 2
y0 = max(0, (nh - th) // 2 - 40)  # bias slightly upward, header bar stays visible
img = base.crop((x0, y0, x0 + tw, y0 + th))

band_h = 190
overlay = Image.new("RGBA", (tw, band_h), DARK + (235,))
img.paste(overlay, (0, th - band_h), overlay)
d = ImageDraw.Draw(img)
d.text((48, th - band_h + 34), "Viennese Data Crunch",
       font=font(True, 64), fill=(255, 255, 255))
subtitle = "Lehmann\u2019s Wohnungsanzeiger \u00b7 1938\u20131942 \u00b7 Vienna address books on a map"
sub_size, max_w = 30, tw - 48 - 170  # keep clear of the pin accent
while sub_size > 18:
    f = font(False, sub_size)
    if d.textbbox((0, 0), subtitle, font=f)[2] <= max_w:
        break
    sub_size -= 1
d.text((50, th - band_h + 112), subtitle, font=f, fill=(209, 213, 219))
# small pin accent in the band
draw_pin(d, tw - 90, th - band_h + 95, 34)
img.save(os.path.join(ROOT, "og-image.png"), optimize=True)
print("og-image.png", img.size)

# ---------- favicon.svg ----------
svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<path d="M32 4C19.3 4 9 14.3 9 27c0 15.9 20.5 32 21.4 32.7a2.2 2.2 0 0 0 3.2 0C34.5 59 55 42.9 55 27 55 14.3 44.7 4 32 4z" fill="#2563eb"/>
<circle cx="32" cy="27" r="9.5" fill="#fff"/>
</svg>
"""
with open(os.path.join(ROOT, "favicon.svg"), "w") as f:
    f.write(svg)

# ---------- favicon.ico (multi-size) ----------
sizes = [64, 48, 32, 16]
big = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
d = ImageDraw.Draw(big)
draw_pin(d, 128, 108, 92)   # leaves room for the point below
frames = [big.resize((s, s), Image.LANCZOS) for s in sizes]
frames[0].save(os.path.join(ROOT, "favicon.ico"), sizes=[(s, s) for s in sizes])
print("favicon.ico", [f.size for f in frames])

# ---------- apple-touch-icon.png ----------
touch = Image.new("RGB", (180, 180), (255, 255, 255))
d = ImageDraw.Draw(touch)
draw_pin(d, 90, 78, 62)
touch.save(os.path.join(ROOT, "apple-touch-icon.png"))
print("apple-touch-icon.png", touch.size)
