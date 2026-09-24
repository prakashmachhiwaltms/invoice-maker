"""Bundles a batch's current-version PDFs into a ZIP archive (§35)."""
import os
import zipfile
from io import BytesIO


def build_batch_zip(documents) -> bytes:
    buffer = BytesIO()
    used_names = set()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for document in documents:
            field_file = document.current_file
            if not field_file:
                continue
            base = os.path.splitext(document.filename)[0]
            is_edited = document.current_version_id and document.current_version.version_number > 1
            name = f'{base}_edited.pdf' if is_edited else f'{base}.pdf'
            counter = 1
            while name in used_names:
                name = f'{base}_edited_{counter}.pdf'
                counter += 1
            used_names.add(name)
            try:
                field_file.open('rb')
                zf.writestr(name, field_file.read())
            finally:
                field_file.close()
    return buffer.getvalue()
