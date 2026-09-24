"""Access control and upload validation for the PDF Invoice Editor.

Kept separate from invoices/views.py's can_edit_invoice() because PDF Editor
documents are scoped more strictly (owner-or-admin can even *view* a document,
not just edit it) - see spec requirement: "Users should only access PDFs they
are authorized to access. Admin can access all."
"""
from django.conf import settings
from django.core.exceptions import ValidationError

PDF_MAGIC = b'%PDF-'


def is_admin_user(user):
    profile = getattr(user, 'profile', None)
    return user.is_superuser or bool(profile and profile.is_admin)


def can_access_document(user, document):
    return is_admin_user(user) or document.uploaded_by_id == user.id


def validate_pdf_upload(uploaded_file):
    """Raises ValidationError if the uploaded file is not an acceptable PDF."""
    import os

    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in settings.ALLOWED_PDF_EXTENSIONS:
        raise ValidationError(f'"{uploaded_file.name}" is not a .pdf file.')
    if uploaded_file.size > settings.MAX_PDF_SIZE_BYTES:
        max_mb = settings.MAX_PDF_SIZE_BYTES // (1024 * 1024)
        raise ValidationError(f'"{uploaded_file.name}" exceeds the {max_mb} MB size limit.')

    head = uploaded_file.read(5)
    uploaded_file.seek(0)
    if head != PDF_MAGIC:
        raise ValidationError(f'"{uploaded_file.name}" does not look like a valid PDF file.')
