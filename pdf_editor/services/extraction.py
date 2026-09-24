"""Text-block extraction and page rendering for the PDF Invoice Editor.

The PDF file is always the source of truth - text blocks are read fresh from
it on every request rather than persisted to the database (see the "no
PdfTextElement table" note in the architecture plan).
"""
import hashlib

import pymupdf as fitz

from .fonts import base14_font, is_bold, is_italic, normalize_color

RENDER_DPI_ZOOM = 150 / 72  # ~150 DPI at 100%


def open_document(field_file):
    """Open a Django FieldFile (FileSystemStorage-backed) as a fitz.Document."""
    field_file.open('rb')
    try:
        data = field_file.read()
    finally:
        field_file.close()
    return fitz.open(stream=data, filetype='pdf')


def _span_id(page_index, block_i, line_i, span_i):
    raw = f'{page_index}:{block_i}:{line_i}:{span_i}'
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]


def get_page_text_blocks(doc, page_index):
    """Return a flat list of editable text spans for one page (0-indexed)."""
    page = doc[page_index]
    raw = page.get_text('dict')
    spans = []
    for b_i, block in enumerate(raw.get('blocks', [])):
        if block.get('type') != 0:  # skip image blocks
            continue
        for l_i, line in enumerate(block.get('lines', [])):
            for s_i, span in enumerate(line.get('spans', [])):
                text = span.get('text', '')
                if not text.strip():
                    continue
                x0, y0, x1, y1 = span['bbox']
                flags = span.get('flags', 0)
                font_name = span.get('font', '')
                spans.append({
                    'id': _span_id(page_index, b_i, l_i, s_i),
                    'page': page_index,
                    'text': text,
                    'x': round(x0, 2),
                    'y': round(y0, 2),
                    'width': round(x1 - x0, 2),
                    'height': round(y1 - y0, 2),
                    'font': font_name,
                    'mapped_font': base14_font(font_name, flags),
                    'font_size': round(span.get('size', 10), 2),
                    'bold': is_bold(font_name, flags),
                    'italic': is_italic(font_name, flags),
                    'color': normalize_color(span.get('color')),
                })
    return spans


def get_page_lines(doc, page_index):
    """Return per-line concatenated text + the spans that make it up (for
    matches that straddle a formatting boundary between adjacent spans)."""
    page = doc[page_index]
    raw = page.get_text('dict')
    lines = []
    for b_i, block in enumerate(raw.get('blocks', [])):
        if block.get('type') != 0:
            continue
        for l_i, line in enumerate(block.get('lines', [])):
            line_span_ids = []
            texts = []
            for s_i, span in enumerate(line.get('spans', [])):
                if not span.get('text', '').strip():
                    continue
                line_span_ids.append(_span_id(page_index, b_i, l_i, s_i))
                texts.append(span.get('text', ''))
            if texts:
                lines.append({'text': ''.join(texts), 'span_ids': line_span_ids})
    return lines


def page_has_text(doc, page_index):
    return len(doc[page_index].get_text('text').strip()) > 0


def document_has_extractable_text(doc):
    return any(page_has_text(doc, i) for i in range(doc.page_count))


def render_page_png(doc, page_index, zoom=RENDER_DPI_ZOOM):
    page = doc[page_index]
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    return pix.tobytes('png'), pix.width, pix.height
