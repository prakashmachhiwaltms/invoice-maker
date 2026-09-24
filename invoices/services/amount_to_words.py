"""Reusable amount-to-words service.

The source spreadsheets typically contain an "In figures" column holding a
broken Excel formula (`#NAME?`). We never rely on that value — the amount in
words is always generated server-side from the numeric total, using the
Indian (Lakh/Crore) numbering system.
"""
import re
from decimal import ROUND_HALF_UP, Decimal

from num2words import num2words

_DIGIT_WORDS = ['Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine']


def _clean(words: str) -> str:
    words = words.replace(',', ' ').replace(' and ', ' ')
    words = words.replace('-', ' ')
    words = re.sub(r'\s+', ' ', words).strip()
    return ' '.join(w.capitalize() for w in words.split(' '))


def _int_to_words(n: int) -> str:
    if n == 0:
        return 'Zero'
    return _clean(num2words(n, lang='en_IN'))


def amount_to_words(
    value,
    fmt='currency',
    currency_name='Rupees',
    subunit_name='Paise',
    zero_subunit_suffix='Only',
) -> str:
    """Convert a monetary value to words.

    fmt='currency' -> "Nine Thousand Two Hundred Twenty Six Rupees and Eighteen Paise Only"
    fmt='plain'     -> "Nine Thousand Two Hundred Twenty Six Point One Eight"
    """
    if value is None:
        value = Decimal('0')
    value = Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    rupees = int(value)
    paise = int((value - rupees) * 100)

    rupee_words = _int_to_words(rupees)

    if fmt == 'plain':
        if paise:
            digit_words = ' '.join(_DIGIT_WORDS[int(d)] for d in f'{paise:02d}')
            return f'{rupee_words} Point {digit_words}'
        return rupee_words

    # currency style (default)
    if paise:
        paise_words = _int_to_words(paise)
        return f'{rupee_words} {currency_name} and {paise_words} {subunit_name} {zero_subunit_suffix}'
    return f'{rupee_words} {currency_name} {zero_subunit_suffix}'
