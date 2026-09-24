"""Bundles generated invoice files into a ZIP archive using Python's zipfile.

Only the requested files are included - no stray temp files or directories.
"""
import zipfile
from io import BytesIO

from .utils import safe_filename


def build_zip(invoices, file_type='pdf') -> bytes:
    buffer = BytesIO()
    used_names = set()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for invoice in invoices:
            file_field = invoice.pdf_file if file_type == 'pdf' else invoice.docx_file
            if not file_field:
                continue
            ext = 'pdf' if file_type == 'pdf' else 'docx'
            name = f'{safe_filename(invoice.invoice_number)}.{ext}'
            counter = 1
            base_name = name
            while name in used_names:
                name = f'{safe_filename(invoice.invoice_number)}_{counter}.{ext}'
                counter += 1
            used_names.add(name)
            try:
                file_field.open('rb')
                zf.writestr(name, file_field.read())
            finally:
                file_field.close()
    return buffer.getvalue()


def build_mixed_zip(invoices) -> bytes:
    """ZIP containing both PDF and DOCX for each invoice, in pdf/ and docx/ folders."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for invoice in invoices:
            base = safe_filename(invoice.invoice_number)
            if invoice.pdf_file:
                invoice.pdf_file.open('rb')
                zf.writestr(f'pdf/{base}.pdf', invoice.pdf_file.read())
                invoice.pdf_file.close()
            if invoice.docx_file:
                invoice.docx_file.open('rb')
                zf.writestr(f'docx/{base}.docx', invoice.docx_file.read())
                invoice.docx_file.close()
    return buffer.getvalue()
