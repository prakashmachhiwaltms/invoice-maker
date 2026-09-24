"""Low-level PyMuPDF mutations. Each function mutates an open fitz.Document
in place; callers (document_service.py) are responsible for saving the
result as a new PdfVersion.
"""
import pymupdf as fitz

BASELINE_RATIO = 0.85  # approx ascent fraction of font_size, used to place insert_text()'s baseline


def _baseline_point(x0, y0, font_size):
    return fitz.Point(x0, y0 + font_size * BASELINE_RATIO)


def redact_box(page, x0, y0, x1, y1):
    """Permanently remove any glyphs/graphics inside the box and paint it
    white, so the original content is gone (not just covered)."""
    rect = fitz.Rect(x0, y0, x1, y1)
    page.add_redact_annot(rect, fill=(1, 1, 1))
    page.apply_redactions()


def insert_text(page, x0, y0, text, font_name='helv', font_size=10, color=(0, 0, 0)):
    point = _baseline_point(x0, y0, font_size)
    page.insert_text(point, text, fontname=font_name, fontsize=font_size, color=color)


def replace_span(doc, page_index, bbox, new_text, font_name='helv', font_size=10, color=(0, 0, 0)):
    page = doc[page_index]
    x0, y0, x1, y1 = bbox
    redact_box(page, x0, y0, x1, y1)
    if new_text:
        insert_text(page, x0, y0, new_text, font_name, font_size, color)


def hide_text(doc, page_index, bbox):
    page = doc[page_index]
    x0, y0, x1, y1 = bbox
    redact_box(page, x0, y0, x1, y1)


def add_text(doc, page_index, x, y, text, font_name='helv', font_size=11, color=(0, 0, 0)):
    page = doc[page_index]
    insert_text(page, x, y, text, font_name, font_size, color)


def move_text(doc, page_index, bbox, new_x, new_y, text, font_name='helv', font_size=10, color=(0, 0, 0)):
    page = doc[page_index]
    x0, y0, x1, y1 = bbox
    redact_box(page, x0, y0, x1, y1)
    insert_text(page, new_x, new_y, text, font_name, font_size, color)


def replace_region_autofit(doc, page_index, bbox, text, font_name='helv', max_size=10, min_size=6,
                            color=(0, 0, 0), align=0, extra_width=0):
    """Redact bbox and reinsert `text` inside it using insert_textbox(), which
    wraps automatically; if it still doesn't fit at max_size, shrink the font
    (down to min_size) until it does. Used by the Label & Value editor, where
    a replacement value/label can be considerably longer than the original -
    see field_service.apply_field_edit(). `extra_width` widens the box to the
    right (bounded by the caller) so a longer value has room without
    overlapping a neighboring column.
    """
    import pymupdf as fitz

    page = doc[page_index]
    x0, y0, x1, y1 = bbox
    redact_box(page, x0, y0, x1, y1)
    if not text:
        return

    rect = fitz.Rect(x0, y0 - 1, x1 + extra_width, y1 + max(6, (y1 - y0) * 2.2))
    size = max_size
    while size >= min_size:
        overflow = page.insert_textbox(
            rect, text, fontname=font_name, fontsize=size, color=color, align=align,
        )
        if overflow >= 0:
            return
        size -= 0.5
    # Last resort: insert at min_size even if it slightly overflows the box,
    # rather than silently dropping the text.
    page.insert_textbox(rect, text, fontname=font_name, fontsize=min_size, color=color, align=align)
