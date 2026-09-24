"""Orchestrates PyMuPDF operations (pdf_ops.py) with the Django models
(PdfDocument / PdfVersion / PdfEditOperation), including the linear
undo/redo version pointer.
"""
import os

from django.core.files.base import ContentFile
from django.db import transaction

from . import extraction, pdf_ops
from ..models import PdfDocument, PdfEditOperation, PdfVersion


class SpanNotFound(Exception):
    pass


def open_fitz(document: PdfDocument):
    return extraction.open_document(document.current_file)


def _versioned_filename(document: PdfDocument, version_number: int) -> str:
    base = os.path.splitext(document.filename)[0]
    return f'{base}_v{version_number}.pdf'


@transaction.atomic
def _save_new_version(document: PdfDocument, fitz_doc, user, note: str) -> PdfVersion:
    current_number = document.current_version.version_number if document.current_version_id else 0

    # Truncate the redo branch: a fresh edit from a non-tip version discards
    # every version that came after it (standard linear undo/redo).
    stale = PdfVersion.objects.filter(document=document, version_number__gt=current_number)
    for stale_version in stale:
        stale_version.file.delete(save=False)
    stale.delete()

    new_number = current_number + 1
    pdf_bytes = fitz_doc.tobytes(garbage=3, deflate=True)
    version = PdfVersion.objects.create(
        document=document,
        version_number=new_number,
        file=ContentFile(pdf_bytes, name=_versioned_filename(document, new_number)),
        note=note,
        created_by=user,
    )
    document.current_version = version
    document.save(update_fields=['current_version', 'updated_at'])
    return version


def save_new_version(document: PdfDocument, fitz_doc, user, note: str) -> PdfVersion:
    """Public entry point for other services (e.g. field_service) to persist
    a new version - thin wrapper so callers don't reach into the
    underscore-prefixed helper directly."""
    return _save_new_version(document, fitz_doc, user, note)


def _find_span(doc, page_index, span_id):
    for span in extraction.get_page_text_blocks(doc, page_index):
        if span['id'] == span_id:
            return span
    raise SpanNotFound(span_id)


def apply_replace(document: PdfDocument, user, page_index: int, span_id: str, new_text: str) -> PdfVersion:
    doc = open_fitz(document)
    span = _find_span(doc, page_index, span_id)
    font = 'hebo' if span['bold'] and not span['italic'] else span['mapped_font']
    pdf_ops.replace_span(
        doc, page_index,
        (span['x'], span['y'], span['x'] + span['width'], span['y'] + span['height']),
        new_text, font_name=font, font_size=span['font_size'], color=span['color'],
    )
    note = f'Replaced "{span["text"]}" -> "{new_text}"'
    version = _save_new_version(document, doc, user, note)
    PdfEditOperation.objects.create(
        document=document, version=version, operation_type=PdfEditOperation.OP_REPLACE,
        original_text=span['text'], replacement_text=new_text, page=page_index,
        coordinates={'x': span['x'], 'y': span['y'], 'width': span['width'], 'height': span['height']},
        created_by=user,
    )
    return version


def apply_hide(document: PdfDocument, user, page_index: int, span_id: str) -> PdfVersion:
    doc = open_fitz(document)
    span = _find_span(doc, page_index, span_id)
    pdf_ops.hide_text(doc, page_index, (span['x'], span['y'], span['x'] + span['width'], span['y'] + span['height']))
    version = _save_new_version(document, doc, user, f'Hid "{span["text"]}"')
    PdfEditOperation.objects.create(
        document=document, version=version, operation_type=PdfEditOperation.OP_DELETE,
        original_text=span['text'], page=page_index,
        coordinates={'x': span['x'], 'y': span['y'], 'width': span['width'], 'height': span['height']},
        created_by=user,
    )
    return version


def apply_move(document: PdfDocument, user, page_index: int, span_id: str, new_x: float, new_y: float) -> PdfVersion:
    doc = open_fitz(document)
    span = _find_span(doc, page_index, span_id)
    font = 'hebo' if span['bold'] and not span['italic'] else span['mapped_font']
    pdf_ops.move_text(
        doc, page_index,
        (span['x'], span['y'], span['x'] + span['width'], span['y'] + span['height']),
        new_x, new_y, span['text'], font_name=font, font_size=span['font_size'], color=span['color'],
    )
    version = _save_new_version(document, doc, user, f'Moved "{span["text"]}"')
    PdfEditOperation.objects.create(
        document=document, version=version, operation_type=PdfEditOperation.OP_MOVE,
        original_text=span['text'], replacement_text=span['text'], page=page_index,
        coordinates={'x': new_x, 'y': new_y, 'width': span['width'], 'height': span['height']},
        created_by=user,
    )
    return version


def apply_add_text(document: PdfDocument, user, page_index: int, x: float, y: float, text: str,
                    font_size: float = 11, bold: bool = False, italic: bool = False) -> PdfVersion:
    from .fonts import base14_font
    flags = (1 << 4 if bold else 0) | (1 << 1 if italic else 0)
    font = base14_font('', flags)
    doc = open_fitz(document)
    pdf_ops.add_text(doc, page_index, x, y, text, font_name=font, font_size=font_size)
    version = _save_new_version(document, doc, user, f'Added "{text}"')
    PdfEditOperation.objects.create(
        document=document, version=version, operation_type=PdfEditOperation.OP_ADD,
        replacement_text=text, page=page_index, coordinates={'x': x, 'y': y}, created_by=user,
    )
    return version


def undo(document: PdfDocument) -> bool:
    if not document.current_version_id:
        return False
    target_number = document.current_version.version_number - 1
    if target_number < 1:
        return False
    target = PdfVersion.objects.filter(document=document, version_number=target_number).first()
    if not target:
        return False
    document.current_version = target
    document.save(update_fields=['current_version', 'updated_at'])
    _resync_fields_after_version_change(document)
    return True


def redo(document: PdfDocument) -> bool:
    if not document.current_version_id:
        return False
    target_number = document.current_version.version_number + 1
    target = PdfVersion.objects.filter(document=document, version_number=target_number).first()
    if not target:
        return False
    document.current_version = target
    document.save(update_fields=['current_version', 'updated_at'])
    _resync_fields_after_version_change(document)
    return True


def _resync_fields_after_version_change(document: PdfDocument):
    """Keep the Label & Value Editor's field table honest after the active
    version changes underneath it. Imported lazily to avoid a circular
    import (field_service imports this module for open_fitz/save_new_version)."""
    from . import field_service
    field_service.sync_detected_fields(document)


def count_matches(document: PdfDocument, find_text: str) -> int:
    return len(search_document(document, find_text))


def _replace_all_in_open_doc(doc, find_text: str, replace_text: str) -> int:
    count = 0
    for page_index in range(doc.page_count):
        spans = extraction.get_page_text_blocks(doc, page_index)
        matched_span_ids = set()
        for span in spans:
            if find_text in span['text']:
                font = 'hebo' if span['bold'] and not span['italic'] else span['mapped_font']
                new_text = span['text'].replace(find_text, replace_text)
                pdf_ops.replace_span(
                    doc, page_index,
                    (span['x'], span['y'], span['x'] + span['width'], span['y'] + span['height']),
                    new_text, font_name=font, font_size=span['font_size'], color=span['color'],
                )
                matched_span_ids.add(span['id'])
                count += 1
        for line in extraction.get_page_lines(doc, page_index):
            if find_text in line['text'] and not (set(line['span_ids']) & matched_span_ids):
                line_spans = [s for s in spans if s['id'] in line['span_ids']]
                if not line_spans:
                    continue
                x0 = min(s['x'] for s in line_spans)
                y0 = min(s['y'] for s in line_spans)
                x1 = max(s['x'] + s['width'] for s in line_spans)
                y1 = max(s['y'] + s['height'] for s in line_spans)
                first = line_spans[0]
                font = 'hebo' if first['bold'] and not first['italic'] else first['mapped_font']
                new_text = line['text'].replace(find_text, replace_text)
                pdf_ops.replace_span(doc, page_index, (x0, y0, x1, y1), new_text,
                                      font_name=font, font_size=first['font_size'], color=first['color'])
                count += 1
    return count


def apply_replace_all(document: PdfDocument, user, find_text: str, replace_text: str):
    """Replace every occurrence of find_text in the document as a single new
    version. Returns (version_or_None, match_count)."""
    doc = open_fitz(document)
    count = _replace_all_in_open_doc(doc, find_text, replace_text)
    if count == 0:
        return None, 0
    note = f'Replaced all "{find_text}" -> "{replace_text}" ({count} match(es))'
    version = _save_new_version(document, doc, user, note)
    PdfEditOperation.objects.create(
        document=document, version=version, operation_type=PdfEditOperation.OP_REPLACE,
        original_text=find_text, replacement_text=replace_text, page=0,
        coordinates={'scope': 'whole_document', 'match_count': count}, created_by=user,
    )
    return version, count


def search_document(document: PdfDocument, find_text: str):
    """Return [{page, span_ids, text, x, y, width, height}] for every match
    of find_text, found either within a single span or across a whole line
    when the match straddles a formatting boundary."""
    if not find_text:
        return []
    doc = open_fitz(document)
    matches = []
    for page_index in range(doc.page_count):
        spans = extraction.get_page_text_blocks(doc, page_index)
        for span in spans:
            if find_text in span['text']:
                matches.append({
                    'page': page_index, 'span_ids': [span['id']], 'text': span['text'],
                    'x': span['x'], 'y': span['y'], 'width': span['width'], 'height': span['height'],
                })
        matched_span_ids = {sid for m in matches if m['page'] == page_index for sid in m['span_ids']}
        for line in extraction.get_page_lines(doc, page_index):
            if find_text in line['text'] and not (set(line['span_ids']) & matched_span_ids):
                line_spans = [s for s in spans if s['id'] in line['span_ids']]
                if not line_spans:
                    continue
                x0 = min(s['x'] for s in line_spans)
                y0 = min(s['y'] for s in line_spans)
                x1 = max(s['x'] + s['width'] for s in line_spans)
                y1 = max(s['y'] + s['height'] for s in line_spans)
                matches.append({
                    'page': page_index, 'span_ids': line['span_ids'], 'text': line['text'],
                    'x': x0, 'y': y0, 'width': x1 - x0, 'height': y1 - y0,
                })
    return matches
