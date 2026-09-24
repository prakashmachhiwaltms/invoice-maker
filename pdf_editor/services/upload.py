import os

import pymupdf as fitz
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction

from . import security
from ..models import PdfBatch, PdfDocument, PdfVersion


@transaction.atomic
def create_batch_from_files(files, user, batch_name=''):
    """Validate + ingest a list of uploaded PDF files into a new PdfBatch.

    Returns (batch, created_documents, per_file_errors) - a bad file among a
    multi-file upload doesn't abort the rest.
    """
    batch = PdfBatch.objects.create(name=batch_name, total_files=len(files), created_by=user)
    created = []
    errors = []

    for f in files:
        try:
            security.validate_pdf_upload(f)
            document = _ingest_single_file(batch, f, user)
            created.append(document)
        except ValidationError as exc:
            errors.append({'filename': f.name, 'error': '; '.join(exc.messages)})
        except Exception as exc:  # malformed PDF that fails to open, etc.
            errors.append({'filename': f.name, 'error': f'Could not process file: {exc}'})

    batch.processed_count = len(created)
    batch.failed_count = len(errors)
    batch.status = PdfBatch.STATUS_COMPLETED if not errors or created else PdfBatch.STATUS_FAILED
    batch.save(update_fields=['processed_count', 'failed_count', 'status'])
    return batch, created, errors


def _ingest_single_file(batch, uploaded_file, user):
    from . import extraction

    document = PdfDocument.objects.create(
        batch=batch, original_file=uploaded_file, filename=os.path.basename(uploaded_file.name),
        uploaded_by=user, status=PdfDocument.STATUS_UPLOADED,
    )

    document.original_file.open('rb')
    try:
        pdf_bytes = document.original_file.read()
    finally:
        document.original_file.close()

    fitz_doc = fitz.open(stream=pdf_bytes, filetype='pdf')
    page_count = fitz_doc.page_count
    has_text = extraction.document_has_extractable_text(fitz_doc)
    fitz_doc.close()

    version = PdfVersion.objects.create(
        document=document, version_number=1,
        file=ContentFile(pdf_bytes, name=document.filename),
        note='Original upload', created_by=user,
    )
    document.current_version = version
    document.page_count = page_count
    document.has_extractable_text = has_text
    document.status = PdfDocument.STATUS_READY if has_text else PdfDocument.STATUS_SCANNED
    document.save(update_fields=['current_version', 'page_count', 'has_extractable_text', 'status'])
    return document
