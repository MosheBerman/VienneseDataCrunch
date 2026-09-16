#!/usr/bin/env python3
"""
Parser for Lehmann 1938 Band 2 IV. Teil (Häuserverzeichnis) OCR output.

Input: OCR text files in ocr1938b2_iv/ named p<page>-c<col>.txt
Output: JSONL with one record per resident.

Usage: python3 parse_ivteil.py [--sample N] [--out FILE]
"""
import re
import json
import os
import sys
import glob
from collections import Counter

OCR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ocr1938b2_iv')
OUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'parsed_ivteil.jsonl')

# OCR error normalizations
def normalize_line(s):
    """Basic OCR cleanup for Fraktur misreads."""
    s = s.strip()
    # Fix common EZ misreads: E27, a t., E2, etc.
    s = re.sub(r'\bE27\b', 'EZ', s)
    s = re.sub(r'\ba\s+t\.', 'EZ', s)  # "a t." -> EZ
    s = re.sub(r'\bE2\b(?=\s+\d)', 'EZ', s)
    # Fix Stiege misreads
    s = re.sub(r'&\s*tiege', 'Stiege', s)
    s = re.sub(r'\bt\s+tege', 'Stiege', s)
    return s

# Patterns
STREET_RE = re.compile(r'^([IVX]{1,4})\.\s*([A-ZÄÖÜ][A-Za-zäöüÄÖÜß\- ]{2,40})$')
# House: "35", "49A", "35 EZ 721", "49A EZ 148", "4 EZ 1388", "13 EZ" (number may be missing)
# Note: letter (A-Z) comes after optional whitespace, e.g., "35 D"
HOUSE_RE = re.compile(r'^(\d{1,4})\s*([A-Z])?\s*(?:(EZ)\s*(\d{1,5})?)?\s*(\.|,)?\s*(s\.\s*a\..*)?$')
# Street suffixes (with OCR variants)
STREET_SUFFIX_RE = re.compile(r'(gasse|gaffe|gafie|gafle|straße|ftrafe|ftraf|ftr\.|platz|plag|weg|allee|ring|kai|damm)', re.IGNORECASE)
# Stiege: "1. Stiege", "2. Stiege" (OCR: tiege, tege, Stiege)
STIEGE_RE = re.compile(r'(\d+)\s*\.\s*(Stiege|stiege|Steige|tiege|tege)', re.IGNORECASE)
# Cross-street header: contains arrows
ARROW_RE = re.compile(r'[→←+]|>\s*$|^\s*>')
# Page header artifacts
HEADER_RE = re.compile(r'Lehmann|Teil\s*IV|^\d{3,4}$|^—+$|^\s*$\(EEE')
# Shop indicators (not residents, but context)
SHOP_RE = re.compile(r'Gassenladen|Gaffenladen', re.IGNORECASE)

def is_street_header(line):
    """Detect street headers like 'X. Favoritenstraße' or 'IX. Porzellangasse'.
    Handles OCR-mangled districts (e.g., 'g . Borzellangafie' for 'IX. Porzellangasse').
    Returns (district, street) or None."""
    # Pattern: district (roman numeral or single letter from OCR error) + period + street
    m = re.match(r'^([IVX]{1,4}|[A-Za-z])\s*\.\s*([A-ZÄÖÜ][A-Za-zäöüÄÖÜß\- ]{5,40})$', line)
    if m:
        district, street = m.groups()
        street = street.strip()
        # Must contain a street suffix and not be just a fragment
        if STREET_SUFFIX_RE.search(street):
            low = street.lower().rstrip('.:,')
            if low not in ('straße', 'strasse', 'gasse', 'gaffe', 'gafie', 'platz', 'weg', 'allee', 'ring', 'kai'):
                return district.strip(), street
    return None

def is_house_number(line, has_street=True):
    """Detect house numbers. Returns (house_num, letter, ez_num, trailing) or None.
    trailing: any text after the house pattern (e.g., merged resident "Be." in
    "4 EZ 1539 Be.") — caller should parse it as a resident.
    has_street: for weak signals (standalone numbers), only detect if we have
    a street context (avoids false positives in garbage OCR like standalone
    '3' on damaged pages). Strong EZ signals are detected regardless."""
    # Skip if line is too long (resident lines can have numbers)
    if len(line) > 30:
        return None
    # If line has many words, it's not a house number
    # (Note: we do NOT filter on comma here — house headers often merge with
    # the first resident like "4 EZ 1539 Be.", and the regexes below won't
    # match genuine resident lines which don't start with digits.)
    if len(line.split()) > 5:
        return None
    
    # Strategy 1: Look for "N EZ M" pattern at start of line (strong signal).
    # Handles OCR noise like "1.)19 EZ 768" where prefix garbles the start.
    # Requires no letters before the number (avoids matching "Wohnung 5 EZ 827"
    # where 5 is an apartment, not a house).
    # This is a strong signal, so we detect it even without street context.
    # Captures trailing text (merged resident) for the caller to parse.
    m = re.match(r'^[^A-Za-z]*?(\d{1,4})([A-Z])?\s+(EZ|Ez|ez)\s+(\d{1,5})(.*)$', line)
    if m:
        num, letter, _, ez_num, trailing = m.groups()
        return num, letter or '', ez_num or '', trailing.strip()
    
    # Strategy 2: Standalone number at start of line (e.g., "35", "35 D").
    # DISABLED: Standalone numbers without EZ are overwhelmingly false positives
    # (OCR artifacts, list markers, etc.). Real houses in the Häuserverzeichnis
    # have EZ numbers. We only trust the EZ pattern (Strategy 1).
    # if not has_street:
    #     return None
    # m = HOUSE_RE.match(line)
    # if not m:
    #     return None
    # num, letter, ez, ez_num, _, _ = m.groups()
    # if len(num) == 1 and not letter and not ez:
    #     return None
    # return num, letter or '', ez_num or '', ''
    
    # Strategy 3: Digit before a name (e.g., "48 Sue und", "5 E28 f. en a").
    # The number is a house number that applies until the next number appears.
    # This is the Häuserverzeichnis format: house number introduces the residents.
    # Only applies with street context (avoids false positives in headers).
    # Excludes stiege markers ("1. Stiege") — those are handled by is_stiege.
    # Requires trailing to start with UPPERCASE (a name), not street suffixes
    # like "Gaffe" (Gasse) or garbage like "a 8", "x,".
    if has_street:
        if 'stiege' not in line.lower():
            m = re.match(r'^(\d{1,4})\s+(.+)$', line)
            if m:
                num, trailing = m.groups()
                trailing = trailing.strip()
                # Remove leading punctuation from trailing
                trailing = re.sub(r'^[\s\.,;:\-]+', '', trailing)
                # Must start with uppercase letter (name), have alphabetic content,
                # and not be a street suffix or single-char garbage
                if (trailing and len(trailing) >= 2
                        and trailing[0].isupper()
                        and any(c.isalpha() for c in trailing)
                        and not STREET_SUFFIX_RE.match(trailing)
                        and not re.match(r'^[A-Z]\s*[,;.]?$', trailing)):
                    return num, '', '', trailing
    return None

def is_stiege(line):
    m = STIEGE_RE.search(line)
    if m and len(line) < 20:
        return m.group(1)
    return None

def is_cross_street(line):
    # Arrows indicating cross-street headers
    if ARROW_RE.search(line) and len(line) < 40:
        return True
    return False

def is_page_header(line):
    if HEADER_RE.search(line):
        return True
    # Single numbers (page numbers)
    if re.match(r'^\d{3,4}$', line.strip()):
        return True
    return False

def parse_resident(text, state):
    """Parse a resident entry text into name and occupation."""
    # Text like "Bogner Stefanie, Blumenhandlung T."
    # Split on first comma
    parts = text.split(',', 1)
    if len(parts) == 2:
        name = parts[0].strip()
        occ = parts[1].strip()
        # Remove trailing "T." (Telefon indicator)
        occ = re.sub(r'\s*T\.\s*$', '', occ).strip()
    else:
        name = text.strip()
        occ = ''
        name = re.sub(r'\s*T\.\s*$', '', name).strip()
    
    return {
        'page_id': state['page_id'],
        'col': state['col'],
        'street': state['street'],
        'district': state['district'],
        'house_number': state['house'],
        'house_letter': state['house_letter'],
        'ez_number': state['ez'],
        'stiege': state['stiege'],
        'name': name,
        'occupation': occ,
        'raw': text,
    }

def parse_file(filepath, page_id, col, state=None):
    """Parse a single OCR column file. Returns list of resident records.
    If state is provided, uses it as initial state and updates it in-place
    (for carryover across columns/pages)."""
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        lines = [normalize_line(l) for l in f.readlines()]
    
    if state is None:
        state = {
            'page_id': page_id,
            'col': col,
            'street': '',
            'district': '',
            'house': '',
            'house_letter': '',
            'ez': '',
            'stiege': '',
        }
    else:
        # Update page/col. Street/district carry over (streets span pages),
        # but house/ez/stiege reset on page change (houses don't span pages).
        if state['page_id'] != page_id:
            state['house'] = ''
            state['house_letter'] = ''
            state['ez'] = ''
            state['stiege'] = ''
        state['page_id'] = page_id
        state['col'] = col
    
    records = []
    buffer = []  # for multi-line resident entries
    
    def flush_buffer():
        if buffer:
            text = ' '.join(buffer)
            # Skip garbage: too short, contains |, or no letters
            if len(text) >= 3 and '|' not in text and any(c.isalpha() for c in text):
                # Must have comma or be at least 2 words (name pattern)
                if ',' in text or len(text.split()) >= 2:
                    records.append(parse_resident(text, state))
            buffer.clear()
    
    for idx, line in enumerate(lines):
        if not line:
            flush_buffer()
            continue
        
        if is_page_header(line):
            flush_buffer()
            continue
        
        if is_cross_street(line):
            flush_buffer()
            continue
        
        # Street header?
        sh = is_street_header(line)
        if sh:
            flush_buffer()
            state['district'], state['street'] = sh
            # Reset house/stiege for new street
            state['house'] = ''
            state['house_letter'] = ''
            state['ez'] = ''
            state['stiege'] = ''
            continue
        
        # House number? (only if we have street context for weak signals)
        hn = is_house_number(line, has_street=bool(state['street']))
        # Strategy 3b: Standalone number on its own line, followed by resident text
        # on the next non-empty line (e.g., "48" then "Sue und"). The number is the
        # house that applies until the next number appears.
        # Requires 2+ digits (single digits 1-9 are overwhelmingly list markers,
        # page numbers, and OCR artifacts — not house numbers).
        if not hn and bool(state['street']) and re.match(r'^\d{2,4}$', line):
            # Look ahead to next non-empty line
            for j in range(idx + 1, min(idx + 4, len(lines))):
                nxt = lines[j].strip() if j < len(lines) else ''
                if not nxt:
                    continue
                # Next line has alphabetic content and isn't a header/stiege
                if (any(c.isalpha() for c in nxt) and len(nxt) < 40
                        and 'stiege' not in nxt.lower()
                        and not is_page_header(nxt)
                        and not is_cross_street(nxt)):
                    hn = (line, '', '', '')
                break
        if hn:
            flush_buffer()
            house_num, house_letter, ez_num, trailing = hn
            state['house'], state['house_letter'], state['ez'] = house_num, house_letter, ez_num
            state['stiege'] = ''  # reset stiege for new house
            # If house header merged with resident text (e.g., "4 EZ 1539 Be."),
            # parse the trailing text as a resident
            if trailing and len(trailing) >= 2 and any(c.isalpha() for c in trailing):
                buffer.append(trailing)
                if re.search(r'T\.\s*$|\.\s*$', trailing):
                    flush_buffer()
            continue
        
        # Stiege?
        st = is_stiege(line)
        if st:
            flush_buffer()
            state['stiege'] = st
            continue
        
        # Shop indicator? (context, not a resident)
        if SHOP_RE.search(line) and len(line) < 20:
            flush_buffer()
            continue
        
        # Otherwise, accumulate as resident text
        buffer.append(line)
        # If line ends with T. or period, likely end of entry
        if re.search(r'T\.\s*$|\.\s*$', line):
            flush_buffer()
    
    flush_buffer()
    return records

def find_page_streets(files):
    """First pass: find the street header for each page.
    Returns dict {page_id: (district, street)}."""
    page_streets = {}
    for fp in files:
        m = re.search(r'p(\d+)-c(\d+)\.txt$', fp)
        if not m:
            continue
        page_id = f"p{m.group(1)}"
        # Skip if we already found a street for this page
        if page_id in page_streets:
            continue
        with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                norm = normalize_line(line.strip())
                sh = is_street_header(norm)
                if sh:
                    page_streets[page_id] = sh
                    break
    return page_streets

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--sample', type=int, default=0, help='Parse only N files for testing')
    ap.add_argument('--out', default=OUT_FILE, help='Output JSONL file')
    args = ap.parse_args()
    
    files = sorted(glob.glob(os.path.join(OCR_DIR, 'p*.txt')))
    # Sort by page then column: p1000-c0, p1000-c1, ..., p1001-c0, ...
    def file_key(fp):
        m = re.search(r'p(\d+)-c(\d+)\.txt$', fp)
        return (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    files = sorted(files, key=file_key)
    if args.sample:
        files = files[:args.sample]
    
    print(f"Parsing {len(files)} files...", file=sys.stderr)
    
    all_records = []
    stats = Counter()
    
    # State carries across files (street/house persist across columns/pages)
    state = {
        'page_id': '',
        'col': 0,
        'street': '',
        'district': '',
        'house': '',
        'house_letter': '',
        'ez': '',
        'stiege': '',
    }
    
    def reset_house():
        """Reset house-related state (called on page change or street change)."""
        state['house'] = ''
        state['house_letter'] = ''
        state['ez'] = ''
        state['stiege'] = ''
    
    prev_page_id = None
    
    for i, fp in enumerate(files):
        if i % 500 == 0:
            print(f"  {i}/{len(files)}...", file=sys.stderr)
        # Extract page_id and col from filename: p1003-c0.txt
        m = re.search(r'p(\d+)-c(\d+)\.txt$', fp)
        if not m:
            continue
        page_id, col = f"p{m.group(1)}", int(m.group(2))
        
        # Reset house when page changes (house does not carry across pages)
        if page_id != prev_page_id:
            reset_house()
            prev_page_id = page_id
        try:
            recs = parse_file(fp, page_id, col, state)
            all_records.extend(recs)
            stats['files_ok'] += 1
            stats['residents'] += len(recs)
            if recs:
                stats['files_with_residents'] += 1
        except Exception as e:
            stats['files_error'] += 1
            print(f"Error {fp}: {e}", file=sys.stderr)
    
    # Write output
    with open(args.out, 'w', encoding='utf-8') as out:
        for r in all_records:
            out.write(json.dumps(r, ensure_ascii=False) + '\n')
    
    print(f"\nDone. {len(all_records)} residents from {len(files)} files.", file=sys.stderr)
    print(f"Stats: {dict(stats)}", file=sys.stderr)

if __name__ == '__main__':
    main()
