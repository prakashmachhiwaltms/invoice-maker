"""Generic Label -> Value pair detection for arbitrary PDF text.

Pure function module: takes a fitz.Document, returns candidate dicts. Does not
touch the database - see field_service.sync_detected_fields() for the
DB-facing upsert that persists these as PdfField rows.

No hard-coded field list is used to decide WHAT counts as a field (per the
"do not limit detection to predefined labels" requirement) - a small
vocabulary of common invoice words is only used as a confidence *signal*,
never as a filter.
"""
import re

from .fonts import base14_font, is_bold, is_italic, normalize_color

SEPARATORS = [':', '-', '–', '=', '|', '/']
SEPARATOR_CLASS = r'[:\-–=|/]'
LABEL_VALUE_RE = re.compile(
    r'^(?P<label>.{1,50}?)\s*(?P<sep>' + SEPARATOR_CLASS + r')\s*(?P<value>.+)$'
)
BARE_LABEL_RE = re.compile(r'^(?P<label>[A-Za-z][A-Za-z0-9 /.&()#]{1,40})\s*(?P<sep>' + SEPARATOR_CLASS + r')?\s*$')

COMMON_LABEL_WORDS = (
    'invoice', 'date', 'gstin', 'address', 'name', 'supplier', 'customer', 'client',
    'description', 'hsn', 'sac', 'tax', 'amount', 'total', 'place', 'state', 'reference',
    'bill', 'ship', 'company', 'no', 'number', 'code', 'phone', 'email', 'pan', 'account',
    'bank', 'ifsc', 'rate', 'quantity', 'value', 'due', 'terms', 'signatory', 'for',
)

MAX_VERTICAL_GAP_RATIO = 1.8  # multiple of line height allowed when absorbing continuation lines
MAX_ABSORBED_LINES = 6


def _page_lines(doc, page_index):
    """Group spans into lines with combined text + geometry, same primitive
    approach as extraction.get_page_lines() but keeping span-level detail
    needed for the two-span split."""
    page = doc[page_index]
    raw = page.get_text('dict')
    lines = []
    for b_i, block in enumerate(raw.get('blocks', [])):
        if block.get('type') != 0:
            continue
        for l_i, line in enumerate(block.get('lines', [])):
            spans = []
            for span in line.get('spans', []):
                text = span.get('text', '')
                if not text.strip():
                    continue
                x0, y0, x1, y1 = span['bbox']
                spans.append({
                    'text': text, 'x': x0, 'y': y0, 'width': x1 - x0, 'height': y1 - y0,
                    'font': span.get('font', ''), 'flags': span.get('flags', 0),
                    'size': span.get('size', 10), 'color': span.get('color'),
                })
            if not spans:
                continue
            full_text = ''.join(s['text'] for s in spans)
            x0 = min(s['x'] for s in spans)
            y0 = min(s['y'] for s in spans)
            x1 = max(s['x'] + s['width'] for s in spans)
            y1 = max(s['y'] + s['height'] for s in spans)
            lines.append({
                'page': page_index, 'text': full_text, 'spans': spans,
                'x': x0, 'y': y0, 'width': x1 - x0, 'height': y1 - y0,
            })
    lines.sort(key=lambda l: (round(l['y'], 1), l['x']))
    return lines


def _looks_label_like(label_text):
    label_text = label_text.strip()
    if not label_text or len(label_text) > 50:
        return False
    words = re.findall(r'[A-Za-z]+', label_text)
    if not words:
        return False
    return True


def _confidence_for(label_text, sep, absorbed=False):
    words = label_text.strip().lower().split()
    common_hit = any(w.strip('.:') in COMMON_LABEL_WORDS for w in words)
    short_label = len(label_text) <= 30 and len(words) <= 6
    if absorbed:
        return 'MEDIUM'
    if sep == ':' and short_label and common_hit:
        return 'HIGH'
    if short_label:
        return 'HIGH' if common_hit else 'MEDIUM'
    return 'MEDIUM'


def normalize_label_key(label_text):
    return re.sub(r'\s+', ' ', label_text.strip().lower()).strip(' .:-')


def _span_font_info(span):
    font_name = span.get('font', '')
    flags = span.get('flags', 0)
    return {
        'font': base14_font(font_name, flags),
        'font_size': round(span.get('size', 10), 2),
        'font_weight': 'bold' if is_bold(font_name, flags) else 'normal',
        'color': list(normalize_color(span.get('color'))),
    }


def _try_two_span_split(line):
    spans = line['spans']
    if len(spans) < 2:
        return None
    first = spans[0]
    stripped = first['text'].strip()
    if not stripped or stripped[-1] not in SEPARATORS:
        return None
    label_text = stripped[:-1].strip()
    sep = stripped[-1]
    if not _looks_label_like(label_text):
        return None
    value_spans = spans[1:]
    value_text = ''.join(s['text'] for s in value_spans).strip()
    if not value_text:
        return None
    label_bbox = {'x': first['x'], 'y': first['y'], 'width': first['width'], 'height': first['height']}
    vx0 = min(s['x'] for s in value_spans)
    vy0 = min(s['y'] for s in value_spans)
    vx1 = max(s['x'] + s['width'] for s in value_spans)
    vy1 = max(s['y'] + s['height'] for s in value_spans)
    value_bbox = {'x': vx0, 'y': vy0, 'width': vx1 - vx0, 'height': vy1 - vy0}
    return {
        'page': line['page'], 'label': label_text, 'value': value_text, 'separator': sep,
        'label_bbox': label_bbox, 'value_bbox': value_bbox,
        'confidence': _confidence_for(label_text, sep),
        **_span_font_info(value_spans[0]),
    }


def _try_single_span_split(line):
    import pymupdf as fitz

    text = line['text'].strip()
    m = LABEL_VALUE_RE.match(text)
    if not m:
        return None
    label_text = m.group('label').strip()
    sep = m.group('sep')
    value_text = m.group('value').strip()
    if not _looks_label_like(label_text) or not value_text:
        return None

    first_span = line['spans'][0]
    font_name = first_span.get('font', '')
    font_size = first_span.get('size', 10)
    prefix = text[:m.start('value')]
    try:
        prefix_width = fitz.get_text_length(prefix, fontname=base14_font(font_name, first_span.get('flags', 0)), fontsize=font_size)
    except Exception:
        prefix_width = len(prefix) * font_size * 0.5

    label_bbox = {'x': line['x'], 'y': line['y'], 'width': min(prefix_width, line['width']), 'height': line['height']}
    value_x = line['x'] + min(prefix_width, line['width'] - 1)
    value_bbox = {'x': value_x, 'y': line['y'], 'width': max(line['width'] - (value_x - line['x']), 1), 'height': line['height']}
    return {
        'page': line['page'], 'label': label_text, 'value': value_text, 'separator': sep,
        'label_bbox': label_bbox, 'value_bbox': value_bbox,
        'confidence': _confidence_for(label_text, sep),
        **_span_font_info(first_span),
    }


def _absorb_multiline_values(lines, candidates):
    """A label whose value is empty/very short (e.g. a bare 'Address' line)
    absorbs following non-label lines within a small vertical gap."""
    used_line_indices = set()
    for cand in candidates:
        cand['_absorbed_from'] = None

    label_only = []
    for i, line in enumerate(lines):
        text = line['text'].strip()
        m = BARE_LABEL_RE.match(text)
        if m and _looks_label_like(m.group('label')):
            already_has_candidate = any(
                abs(c['label_bbox'].get('y', -999) - line['y']) < 0.5 for c in candidates
            )
            if not already_has_candidate:
                label_only.append((i, line, m.group('label').strip(), m.group('sep') or ':'))

    for i, line, label_text, sep in label_only:
        value_lines = []
        last_y = line['y']
        last_height = max(line['height'], 8)
        for j in range(i + 1, min(i + 1 + MAX_ABSORBED_LINES, len(lines))):
            nxt = lines[j]
            gap = nxt['y'] - last_y
            if gap > last_height * MAX_VERTICAL_GAP_RATIO or gap < 0:
                break
            # Stop absorbing once we hit a line that is itself a genuine
            # label:value or bare-label candidate (using the same
            # _looks_label_like-filtered check as the main pass) - a raw
            # regex match on LABEL_VALUE_RE is too loose here, since a value
            # line like "215-A, 2nd Floor..." also matches it (the hyphen in
            # "215-A" looks like a separator) and would wrongly end absorption.
            nxt_text = nxt['text'].strip()
            if _try_two_span_split(nxt) or _try_single_span_split(nxt):
                break
            bare = BARE_LABEL_RE.match(nxt_text)
            if bare and _looks_label_like(bare.group('label')):
                break
            value_lines.append(nxt)
            last_y = nxt['y']
            last_height = max(nxt['height'], 8)
            used_line_indices.add(j)
        if not value_lines:
            continue
        value_text = ' '.join(l['text'].strip() for l in value_lines)
        x0 = min(l['x'] for l in value_lines)
        y0 = min(l['y'] for l in value_lines)
        x1 = max(l['x'] + l['width'] for l in value_lines)
        y1 = max(l['y'] + l['height'] for l in value_lines)
        first_span = value_lines[0]['spans'][0]
        candidates.append({
            'page': line['page'], 'label': label_text, 'value': value_text, 'separator': sep,
            'label_bbox': {'x': line['x'], 'y': line['y'], 'width': line['width'], 'height': line['height']},
            'value_bbox': {'x': x0, 'y': y0, 'width': x1 - x0, 'height': y1 - y0},
            'confidence': _confidence_for(label_text, sep, absorbed=True),
            **_span_font_info(first_span),
        })


def detect_page(doc, page_index):
    lines = _page_lines(doc, page_index)
    candidates = []
    for line in lines:
        found = _try_two_span_split(line) or _try_single_span_split(line)
        if found:
            candidates.append(found)
    _absorb_multiline_values(lines, candidates)
    return candidates


def detect_candidates(doc):
    """Return every detected label/value candidate across all pages."""
    all_candidates = []
    for page_index in range(doc.page_count):
        all_candidates.extend(detect_page(doc, page_index))
    return all_candidates
