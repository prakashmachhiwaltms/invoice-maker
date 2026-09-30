import pymupdf as fitz
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from pdf_editor.models import PdfBatch, PdfDocument
from pdf_editor.services.upload import create_batch_from_files


def _pdf_bytes(text='Hello'):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), text, fontsize=10, fontname='helv')
    data = doc.tobytes()
    doc.close()
    return data


def _uploaded_pdf(name):
    return SimpleUploadedFile(name, _pdf_bytes(name), content_type='application/pdf')


class UploadBatchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='uploadtester', password='x')

    def test_upload_with_no_existing_batch_creates_a_new_one(self):
        batch, created, errors = create_batch_from_files(
            [_uploaded_pdf('a.pdf'), _uploaded_pdf('b.pdf')], self.user, batch_name='My batch',
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(created), 2)
        self.assertEqual(batch.name, 'My batch')
        self.assertEqual(batch.total_files, 2)
        self.assertEqual(batch.processed_count, 2)
        self.assertEqual(PdfBatch.objects.count(), 1)

    def test_upload_into_existing_batch_appends_rather_than_replacing(self):
        batch, created1, _ = create_batch_from_files(
            [_uploaded_pdf('a.pdf')], self.user, batch_name='Existing batch',
        )
        self.assertEqual(batch.total_files, 1)

        batch2, created2, errors2 = create_batch_from_files(
            [_uploaded_pdf('c.pdf'), _uploaded_pdf('d.pdf')], self.user, existing_batch=batch,
        )

        # No second PdfBatch row was created.
        self.assertEqual(PdfBatch.objects.count(), 1)
        self.assertEqual(batch2.pk, batch.pk)

        batch.refresh_from_db()
        self.assertEqual(batch.total_files, 3)
        self.assertEqual(batch.processed_count, 3)
        self.assertEqual(errors2, [])
        self.assertEqual(len(created2), 2)

        # All three documents (original + 2 appended) belong to the same batch.
        self.assertEqual(PdfDocument.objects.filter(batch=batch).count(), 3)

    def test_appending_bad_file_does_not_lose_existing_batch_counts(self):
        batch, _, _ = create_batch_from_files([_uploaded_pdf('a.pdf')], self.user, batch_name='B')
        bad_file = SimpleUploadedFile('not-a-pdf.pdf', b'this is not a pdf', content_type='application/pdf')

        batch2, created, errors = create_batch_from_files([bad_file], self.user, existing_batch=batch)

        self.assertEqual(len(created), 0)
        self.assertEqual(len(errors), 1)
        batch.refresh_from_db()
        self.assertEqual(batch.total_files, 2)  # 1 original + 1 attempted
        self.assertEqual(batch.processed_count, 1)  # only the original succeeded
        self.assertEqual(batch.failed_count, 1)
