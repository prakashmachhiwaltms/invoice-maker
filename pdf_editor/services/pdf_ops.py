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


def insert_textbox_autofit(page, rect, text, font_name='helv', max_size=10, min_size=6,
                            color=(0, 0, 0), align=0):
    """Insert `text` into `rect` using insert_textbox(), which wraps
    automatically; if it still doesn't fit at max_size, shrink the font
    (down to min_size) until it does. Does NOT redact first - the caller is
    responsible for clearing the area (see replace_region_autofit /
    replace_stacked_region, which both redact once and then call this)."""
    if not text:
        return
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


def replace_region_autofit(doc, page_index, bbox, text, font_name='helv', max_size=10, min_size=6,
                            color=(0, 0, 0), align=0, extra_width=0):
    """Redact bbox and reinsert `text` inside it, auto-wrapped and
    auto-shrunk to fit. Used by the Label & Value editor, where a
    replacement value/label can be considerably longer than the original -
    see field_service.apply_field_edit(). `extra_width` widens the box to
    the right (bounded by the caller) so a longer value has room without
    overlapping a neighboring column.
    """
    page = doc[page_index]
    x0, y0, x1, y1 = bbox
    redact_box(page, x0, y0, x1, y1)
    if not text:
        return
    rect = fitz.Rect(x0, y0 - 1, x1 + extra_width, y1 + max(6, (y1 - y0) * 2.2))
    insert_textbox_autofit(page, rect, text, font_name, max_size, min_size, color, align)


def replace_stacked_region(doc, page_index, label_bbox, value_bbox, new_label, new_value,
                            label_font='helv', label_size=10, label_color=(0, 0, 0),
                            value_font='helv', value_max_size=10, value_min_size=6, value_color=(0, 0, 0)):
    """For a "bare label heading + multi-line value" field (see PdfField.
    is_stacked): redact the combined label+value area once, then reinsert
    the label as a single line using its OWN font/weight (so it stays bold
    if it was bold) and the value as a separately word-wrapped block
    confined to the ORIGINAL value column's width - not the wider box
    replace_region_autofit uses for a single inline value, which would let
    a multi-line address spill across most of the page instead of wrapping
    at its normal column width.
    """
    page = doc[page_index]
    lx0, ly0 = label_bbox['x'], label_bbox['y']
    lx1, ly1 = lx0 + label_bbox['width'], ly0 + label_bbox['height']
    vx0, vy0 = value_bbox['x'], value_bbox['y']
    vx1, vy1 = vx0 + value_bbox['width'], vy0 + value_bbox['height']
    union_x0, union_y0 = min(lx0, vx0), min(ly0, vy0)
    union_x1, union_y1 = max(lx1, vx1), max(ly1, vy1)

    redact_box(page, union_x0, union_y0, union_x1, union_y1)
    if new_label:
        insert_text(page, lx0, ly0, new_label, label_font, label_size, label_color)
    if new_value:
        value_width = max(vx1 - vx0, 40)  # guard against a degenerate/zero-width original bbox
        value_rect = fitz.Rect(vx0, vy0 - 1, vx0 + value_width, union_y1 + max(6, (union_y1 - union_y0) * 2.2))
        insert_textbox_autofit(page, value_rect, new_value, value_font, value_max_size, value_min_size, value_color)
