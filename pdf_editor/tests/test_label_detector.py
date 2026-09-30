import pymupdf as fitz
from django.test import TestCase

from pdf_editor.services import pdf_label_detector as det


def _make_pdf(lines, line_height=13, fontsize=10):
    doc = fitz.open()
    page = doc.new_page()
    y = 50
    for line in lines:
        if line is not None:
            page.insert_text((50, y), line, fontsize=fontsize, fontname='helv')
        y += line_height
    return doc


class LabelDetectorTests(TestCase):
    def test_detects_simple_colon_pair(self):
        doc = _make_pdf(['Invoice To: TMS PVT LTD'])
        candidates = det.detect_candidates(doc)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]['label'], 'Invoice To')
        self.assertEqual(candidates[0]['value'], 'TMS PVT LTD')
        self.assertEqual(candidates[0]['separator'], ':')

    def test_detects_dash_separator(self):
        doc = _make_pdf(['Reference No. - INV-001'])
        candidates = det.detect_candidates(doc)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]['separator'], '-')
        self.assertEqual(candidates[0]['value'], 'INV-001')

    def test_no_false_positive_without_any_separator(self):
        doc = _make_pdf(['Just a plain sentence with no separator'])
        candidates = det.detect_candidates(doc)
        self.assertEqual(candidates, [])

    def test_arbitrary_unseen_label_is_detected(self):
        """§10/§38: detection must not be limited to a hard-coded field list."""
        doc = _make_pdf(['Zorbnaxian Reference Code: XQ-999'])
        candidates = det.detect_candidates(doc)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]['label'], 'Zorbnaxian Reference Code')
        self.assertEqual(candidates[0]['value'], 'XQ-999')

    def test_multiline_value_absorption(self):
        """§12/TEST 11: a bare label line absorbs following lines as one value."""
        doc = _make_pdf([
            'Address',
            '215-A, 2nd Floor, Chinar Incube Business Center,',
            'Hoshangabad Road, Bhopal, Madhya Pradesh, 462026',
        ])
        candidates = det.detect_candidates(doc)
        addr = next((c for c in candidates if c['label'] == 'Address'), None)
        self.assertIsNotNone(addr, f'no Address field found in {candidates}')
        self.assertIn('215-A', addr['value'])
        self.assertIn('Hoshangabad Road', addr['value'])
        self.assertIn('462026', addr['value'])

    def test_real_world_bill_to_block_with_name_and_slash_in_address(self):
        """Regression test for a live-reported bug: a "Bill To" heading
        followed by a multi-line recipient block (name, a flat number
        containing "/", city/state, country code, phone, email) must all be
        absorbed as ONE "Bill To" field - short lines like "TMS" or "IN"
        must not be mistaken for new labels that cut the absorption short,
        and "G5/1, NARMADA BHAWAN..." must not be split into a fake
        "G5" -> "1, NARMADA BHAWAN..." field via the "/" in the flat number.
        """
        doc = _make_pdf([
            'Bill To',
            'TMS',
            'HARSHIT SHRIVASTAVA',
            'G5/1, NARMADA BHAWAN, TULSI NAGAR',
            'BHOPAL, Madhya Pradesh 462003',
            'IN',
            '6266781548',
            'weberdomenick8@gmail.com',
        ])
        candidates = det.detect_candidates(doc)
        labels = [c['label'] for c in candidates]

        bill_to = next((c for c in candidates if c['label'] == 'Bill To'), None)
        self.assertIsNotNone(bill_to, f'no "Bill To" field found in {labels}')
        for expected in ('TMS', 'HARSHIT SHRIVASTAVA', 'G5/1, NARMADA BHAWAN, TULSI NAGAR',
                         'BHOPAL, Madhya Pradesh 462003', 'IN', '6266781548', 'weberdomenick8@gmail.com'):
            self.assertIn(expected, bill_to['value'], f'"{expected}" missing from Bill To value: {bill_to["value"]!r}')

        # None of the address lines should have been split off into their
        # own spurious fields (the "G5" / "IN" false positives from before).
        self.assertNotIn('G5', labels)
        self.assertNotIn('IN', labels)
        self.assertNotIn('TMS', labels)
        self.assertNotIn('HARSHIT SHRIVASTAVA', labels)

    def test_two_column_bare_label_does_not_absorb_other_column(self):
        """Regression test for a live-reported bug: on a two-column layout
        (e.g. seller info on the left, a "Bill To" recipient block on the
        right), a bare label's multi-line absorption must not sweep in
        lines from the OTHER column just because they land at a similar Y
        position. It previously merged both columns' text into one garbled
        value and - worse - corrupted the bbox used to re-insert an edited
        value, so editing the field visually moved it into the wrong
        column and deleted unrelated text from the other one.
        """
        doc = fitz.open()
        page = doc.new_page()
        left = [
            (50, 100, 'Anthropic, PBC'),
            (50, 115, '548 Market Street'),
            (50, 130, 'San Francisco, California 94104'),
            (50, 145, 'support@anthropic.com'),
        ]
        right = [
            (300, 105, 'Bill To'),
            (300, 120, 'Deepak Verma'),
            (300, 135, 'Bhopal, Madhya Pradesh'),
        ]
        for x, y, text in left + right:
            page.insert_text((x, y), text, fontsize=10, fontname='helv')

        candidates = det.detect_candidates(doc)
        bill_to = next((c for c in candidates if c['label'] == 'Bill To'), None)
        self.assertIsNotNone(bill_to, f'no "Bill To" field found in {candidates}')
        self.assertIn('Deepak Verma', bill_to['value'])
        self.assertIn('Bhopal, Madhya Pradesh', bill_to['value'])
        self.assertNotIn('Anthropic', bill_to['value'])
        self.assertNotIn('548 Market Street', bill_to['value'])
        self.assertNotIn('support@anthropic.com', bill_to['value'])

    def test_two_column_same_y_do_not_collide(self):
        """Two fields with the same label at the same y but different x (a
        common two-column supplier/recipient layout) must both be detected."""
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 100), 'Name : ABC LIMITED', fontsize=10, fontname='helv')
        page.insert_text((300, 100), 'Name : XYZ CORP', fontsize=10, fontname='helv')
        candidates = det.detect_candidates(doc)
        names = [c for c in candidates if c['label'] == 'Name']
        self.assertEqual(len(names), 2)
        values = {c['value'] for c in names}
        self.assertEqual(values, {'ABC LIMITED', 'XYZ CORP'})
