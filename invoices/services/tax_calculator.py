"""Centralized, Decimal-based tax calculation logic for invoices.

All financial math must go through this module rather than being scattered
across views/templates, and must use Decimal (never binary float) to avoid
rounding errors in money calculations.
"""
from decimal import ROUND_HALF_UP, Decimal
from typing import NamedTuple


def to_decimal(value, default='0') -> Decimal:
    if value is None or value == '':
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def round_money(value: Decimal, precision: int = 2) -> Decimal:
    quant = Decimal('1').scaleb(-precision) if precision > 0 else Decimal('1')
    return to_decimal(value).quantize(quant, rounding=ROUND_HALF_UP)


class TaxBreakdown(NamedTuple):
    taxable_value: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    cgst_rate: Decimal
    cgst_amount: Decimal
    sgst_rate: Decimal
    sgst_amount: Decimal
    igst_rate: Decimal
    igst_amount: Decimal
    freight: Decimal
    insurance: Decimal
    packing: Decimal
    total: Decimal


def calculate_tax(
    taxable_value,
    tax_rate=None,
    tax_amount=None,
    tax_type='IGST',
    freight=0,
    insurance=0,
    packing=0,
    precision=2,
) -> TaxBreakdown:
    """Compute the full tax breakdown for one invoice line.

    If `tax_amount` is supplied (e.g. imported directly from a spreadsheet) it is
    trusted as the source of truth and `tax_rate` is derived/validated from it when
    possible; otherwise tax_amount is derived from taxable_value * tax_rate / 100.
    """
    taxable_value = to_decimal(taxable_value)
    freight = to_decimal(freight)
    insurance = to_decimal(insurance)
    packing = to_decimal(packing)

    if tax_amount is not None and tax_amount != '':
        tax_amount = to_decimal(tax_amount)
        if tax_rate is None or tax_rate == '':
            tax_rate = (tax_amount / taxable_value * Decimal('100')) if taxable_value else Decimal('0')
        else:
            tax_rate = to_decimal(tax_rate)
    else:
        tax_rate = to_decimal(tax_rate, default='18')
        tax_amount = (taxable_value * tax_rate / Decimal('100'))

    tax_amount = round_money(tax_amount, precision)
    tax_rate = round_money(tax_rate, 3 if precision < 3 else precision)

    if tax_type == 'CGST_SGST':
        half_rate = round_money(tax_rate / 2, 3)
        cgst_rate = sgst_rate = half_rate
        cgst_amount = sgst_amount = round_money(tax_amount / 2, precision)
        igst_rate = Decimal('0')
        igst_amount = Decimal('0')
    else:
        cgst_rate = sgst_rate = Decimal('0')
        cgst_amount = sgst_amount = Decimal('0')
        igst_rate = tax_rate
        igst_amount = tax_amount

    total = round_money(taxable_value + tax_amount + freight + insurance + packing, precision)

    return TaxBreakdown(
        taxable_value=round_money(taxable_value, precision),
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        cgst_rate=cgst_rate,
        cgst_amount=cgst_amount,
        sgst_rate=sgst_rate,
        sgst_amount=sgst_amount,
        igst_rate=igst_rate,
        igst_amount=igst_amount,
        freight=round_money(freight, precision),
        insurance=round_money(insurance, precision),
        packing=round_money(packing, precision),
        total=total,
    )


def calculate_total(taxable_value, tax_amount, freight=0, insurance=0, packing=0, precision=2) -> Decimal:
    return round_money(
        to_decimal(taxable_value) + to_decimal(tax_amount) + to_decimal(freight) + to_decimal(insurance) + to_decimal(packing),
        precision,
    )
