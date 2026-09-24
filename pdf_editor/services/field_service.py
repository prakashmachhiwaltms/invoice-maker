"""DB-facing orchestration for the Label & Value Editor.

Bridges pdf_label_detector.py (pure detection) and pdf_ops.py (pure PyMuPDF
mutation) with the PdfField / PdfVersion / PdfEditOperation models.
"""
from django.db import transaction

from . import document_service, extraction, pdf_label_detector, pdf_ops
from ..models import PdfDocument, PdfEditOperation, PdfField

MIN_FONT_SIZE = 6


class FieldNotFound(Exception):
    pass


def sync_detected_fields(document: PdfDocument):
    """(Re)detect label/value candidates against the document's current
    version and upsert PdfField rows. DETECTED/CONFIRMED/EDITED rows are
    refreshed to track the live PDF; REJECTED/MANUAL rows are left alone.
    Returns the full, current queryset of fields for this document.
    """
    if not document.has_extractable_text:
        return document.fields.all()

    doc = document_service.open_fitz(document)
    candidates = pdf_label_detector.detect_candidates(doc)

    def _row_key(page, x, y):
        # Identity is POSITION, not label text - the whole point of this
        # editor is that the label itself can change, so keying by label
        # would orphan a row (and create a duplicate) the moment its label
        # is edited or undone back. Bucketing absorbs sub-pixel jitter across
        # re-scans while distinct occurrences of an identically-named label
        # on one page (e.g. a two-column invoice with "Name" for both the
        # supplier and the recipient, at the same y but a different x) stay
        # separate rows because their x differs.
        return (page, round(x / 50), round(y / 6))

    existing = {
        _row_key(f.page, (f.label_bbox or {}).get('x', 0), (f.label_bbox or {}).get('y', 0)): f
        for f in document.fields.all()
    }
    seen = set()

    for cand in candidates:
        label_key = pdf_label_detector.normalize_label_key(cand['label'])
        if not label_key:
            continue
        key = _row_key(cand['page'], cand['label_bbox']['x'], cand['label_bbox']['y'])
        if key in seen:
            continue
        seen.add(key)

        existing_field = existing.get(key)
        if existing_field is None:
            PdfField.objects.create(
                document=document, page=cand['page'],
                label=cand['label'], original_label=cand['label'], label_key=label_key,
                value=cand['value'], original_value=cand['value'],
                separator=cand['separator'], original_separator=cand['separator'],
                label_bbox=cand['label_bbox'], value_bbox=cand['value_bbox'],
                font=cand['font'], font_size=cand['font_size'], font_weight=cand['font_weight'],
                color=cand['color'], confidence=cand['confidence'],
                status=PdfField.STATUS_DETECTED, is_detected=True, is_manual=False,
            )
        elif existing_field.status in (PdfField.STATUS_DETECTED, PdfField.STATUS_CONFIRMED, PdfField.STATUS_EDITED):
            existing_field.label = cand['label']
            existing_field.value = cand['value']
            existing_field.separator = cand['separator']
            existing_field.label_bbox = cand['label_bbox']
            existing_field.value_bbox = cand['value_bbox']
            existing_field.font = cand['font']
            existing_field.font_size = cand['font_size']
            existing_field.font_weight = cand['font_weight']
            existing_field.color = cand['color']
            existing_field.confidence = cand['confidence']
            existing_field.save()
        # REJECTED / MANUAL rows: never touched by re-detection.

    return document.fields.all()


def _union_bbox(label_bbox, value_bbox):
    boxes = [b for b in (label_bbox, value_bbox) if b]
    if not boxes:
        return (0, 0, 0, 0)
    x0 = min(b['x'] for b in boxes)
    y0 = min(b['y'] for b in boxes)
    x1 = max(b['x'] + b['width'] for b in boxes)
    y1 = max(b['y'] + b['height'] for b in boxes)
    return (x0, y0, x1, y1)


def _format_field_text(label, separator, value):
    label = (label or '').strip()
    value = (value or '').strip()
    separator = (separator or '').strip()
    if separator:
        return f'{label} {separator} {value}'.strip()
    return f'{label} {value}'.strip()


@transaction.atomic
def apply_multiple_field_edits(document: PdfDocument, user, edits):
    """Apply N (field, new_label, new_separator, new_value) edits to one
    document as a single PDF mutation pass / single new PdfVersion (used by
    both the single-field Label Editor and the bulk rule engine, so a batch
    apply doesn't create one version per matched field - §30). `None` in any
    of new_label/new_separator/new_value means "keep the field's current
    value". Returns the new PdfVersion, or None if `edits` is empty.
    """
    if not edits:
        return None

    doc = document_service.open_fitz(document)
    prepared = []
    for pdf_field, new_label, new_separator, new_value in edits:
        new_label = new_label if new_label is not None else pdf_field.label
        new_separator = new_separator if new_separator is not None else pdf_field.separator
        new_value = new_value if new_value is not None else pdf_field.value

        old_text = _format_field_text(pdf_field.label, pdf_field.separator, pdf_field.value)
        new_text = _format_field_text(new_label, new_separator, new_value)
        bbox = _union_bbox(pdf_field.label_bbox, pdf_field.value_bbox)
        page = doc[pdf_field.page]
        page_width = page.rect.width
        extra_width = max(0, min(250, page_width - bbox[2] - 20))
        color = tuple(pdf_field.color) if pdf_field.color else (0, 0, 0)

        pdf_ops.replace_region_autofit(
            doc, pdf_field.page, bbox, new_text,
            font_name=pdf_field.font or 'helv', max_size=pdf_field.font_size or 10,
            min_size=min(MIN_FONT_SIZE, pdf_field.font_size or 10), color=color,
            extra_width=extra_width,
        )
        prepared.append((pdf_field, old_text, new_text, new_label, new_separator, new_value, bbox))

    note = f'{len(prepared)} field(s) changed' if len(prepared) > 1 else f'Field "{prepared[0][0].label}" changed: "{prepared[0][1]}" -> "{prepared[0][2]}"'
    version = document_service.save_new_version(document, doc, user, note)

    for pdf_field, old_text, new_text, new_label, new_separator, new_value, bbox in prepared:
        PdfEditOperation.objects.create(
            document=document, version=version, operation_type=PdfEditOperation.OP_LABEL_EDIT,
            original_text=old_text, replacement_text=new_text, page=pdf_field.page,
            coordinates={'x': bbox[0], 'y': bbox[1], 'width': bbox[2] - bbox[0], 'height': bbox[3] - bbox[1]},
            field=pdf_field, old_label=pdf_field.label, new_label=new_label,
            old_separator=pdf_field.separator, new_separator=new_separator, created_by=user,
        )
        pdf_field.label = new_label
        pdf_field.separator = new_separator
        pdf_field.value = new_value
        pdf_field.label_key = pdf_label_detector.normalize_label_key(new_label)
        if pdf_field.status != PdfField.STATUS_MANUAL:
            pdf_field.status = PdfField.STATUS_EDITED
        pdf_field.save()

    sync_detected_fields(document)
    return version


def apply_field_edit(document: PdfDocument, user, field_id, new_label, new_separator, new_value):
    """Change one field's label/separator/value (any subset), preserving
    position/font/size/color as the baseline (§15) with auto-shrink-to-fit
    for longer replacement text (§15, §16, §17)."""
    try:
        field = document.fields.get(pk=field_id)
    except PdfField.DoesNotExist:
        raise FieldNotFound(field_id)
    return apply_multiple_field_edits(document, user, [(field, new_label, new_separator, new_value)])


def create_manual_field(document: PdfDocument, user, page_index, span_id, label, value, separator):
    """Define a field manually from a clicked text span, for when automatic
    detection misses it (§21)."""
    doc = document_service.open_fitz(document)
    span = None
    for s in extraction.get_page_text_blocks(doc, page_index):
        if s['id'] == span_id:
            span = s
            break
    if span is None:
        raise FieldNotFound(span_id)

    bbox = {'x': span['x'], 'y': span['y'], 'width': span['width'], 'height': span['height']}
    label = (label or '').strip() or 'Custom Field'
    value = value if value is not None else span['text']
    separator = separator if separator is not None else ':'

    return PdfField.objects.create(
        document=document, page=page_index,
        label=label, original_label=label, label_key=pdf_label_detector.normalize_label_key(label),
        value=value, original_value=value, separator=separator, original_separator=separator,
        label_bbox=bbox, value_bbox=bbox,
        font=span['mapped_font'], font_size=span['font_size'],
        font_weight='bold' if span['bold'] else 'normal', color=list(span['color']),
        confidence=PdfField.CONFIDENCE_HIGH, status=PdfField.STATUS_MANUAL,
        is_detected=False, is_manual=True,
    )


def confirm_field(field: PdfField):
    field.status = PdfField.STATUS_CONFIRMED
    field.save(update_fields=['status', 'updated_at'])
    return field


def reject_field(field: PdfField):
    field.status = PdfField.STATUS_REJECTED
    field.save(update_fields=['status', 'updated_at'])
    return field
