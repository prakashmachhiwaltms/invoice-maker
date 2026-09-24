"""Excel/CSV import: header detection, column mapping, and row validation.

Column names in real-world spreadsheets vary, so headers are matched against a
configurable alias table rather than hard-coded exact strings.
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO

import pandas as pd

REQUIRED_FIELDS = [
    'invoice_number', 'invoice_date', 'supplier_name', 'supplier_address',
    'description', 'hsn', 'taxable_value', 'tax_amount', 'total',
]

FIELD_LABELS = {
    'invoice_number': 'Invoice number',
    'invoice_date': 'Date',
    'supplier_name': 'Name of supplier',
    'supplier_address': 'Address',
    'country': 'Country',
    'description': 'Description of service',
    'hsn': 'HSN',
    'taxable_value': 'Taxable Value',
    'tax_amount': 'Tax amount',
    'total': 'Total',
    'in_figures': 'In figures',
    'quantity': 'Quantity',
    'state': 'State',
    'state_code': 'State Code',
    'place_of_supply': 'Place of Supply',
    'supplier_gstin': 'Supplier GSTIN',
    'invoice_to': 'Invoice To',
    'discount': 'Discount',
    'tax_rate': 'Tax Rate',
    'freight': 'Freight',
    'insurance': 'Insurance',
    'packing': 'Packing',
}

# canonical field -> set of normalized header aliases
COLUMN_ALIASES = {
    'invoice_number': {'invoice number', 'invoice no', 'invoice_no', 'inv no', 'invoice#'},
    'invoice_date': {'date', 'invoice date', 'date of invoice', 'inv date'},
    'supplier_name': {'name of supplier', 'supplier name', 'supplier', 'name', 'vendor name'},
    'supplier_address': {'address', 'supplier address'},
    'country': {'country'},
    'description': {'description of service', 'description', 'description of goods service', 'service description', 'description of goodsservice'},
    'hsn': {'hsn', 'hsn sac', 'hsn code', 'sac'},
    'taxable_value': {'taxable value', 'taxable amt', 'taxable amount'},
    'tax_amount': {'tax amount', 'tax amt'},
    'total': {'total', 'total value', 'total amount', 'grand total'},
    'in_figures': {'in figures', 'in words', 'amount in words'},
    'quantity': {'qty', 'quantity', 'qty units', 'units'},
    'state': {'state'},
    'state_code': {'state code'},
    'place_of_supply': {'place of supply'},
    'supplier_gstin': {'gstin', 'supplier gstin', 'gstn'},
    'invoice_to': {'invoice to'},
    'discount': {'discount', 'disc'},
    'tax_rate': {'tax rate', 'rate', 'gst rate'},
    'freight': {'freight'},
    'insurance': {'insurance'},
    'packing': {'packing'},
}

DATE_FORMATS_DASH = ['%d-%m-%Y', '%Y-%m-%d', '%d-%b-%Y', '%d-%B-%Y']
DATE_FORMATS_SLASH = ['%m/%d/%Y', '%d/%m/%Y']


def normalize_header(header) -> str:
    header = str(header or '').strip().lower()
    header = re.sub(r'[^a-z0-9]+', ' ', header)
    return re.sub(r'\s+', ' ', header).strip()


def build_column_map(columns) -> dict:
    """Return {canonical_field: original_column_name} for the detected header row."""
    mapping = {}
    normalized_lookup = {normalize_header(c): c for c in columns}
    for field_name, aliases in COLUMN_ALIASES.items():
        for norm, original in normalized_lookup.items():
            if norm in aliases:
                mapping[field_name] = original
                break
    return mapping


def parse_date_value(raw):
    if raw is None or raw == '':
        return None, 'Date is missing'
    if isinstance(raw, datetime):
        return raw.date(), None
    if isinstance(raw, date):
        return raw, None
    if isinstance(raw, pd.Timestamp):
        return raw.date(), None

    text = str(raw).strip()
    if not text:
        return None, 'Date is missing'

    formats = DATE_FORMATS_SLASH if '/' in text else DATE_FORMATS_DASH
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date(), None
        except ValueError:
            continue
    try:
        parsed = pd.to_datetime(text, dayfirst='/' not in text)
        if pd.isna(parsed):
            raise ValueError
        return parsed.date(), None
    except Exception:
        return None, f'Invalid date format: "{text}"'


def parse_decimal_value(raw, field_label, required=True):
    if raw is None or (isinstance(raw, float) and pd.isna(raw)) or str(raw).strip() == '':
        if required:
            return None, f'{field_label} is missing'
        return Decimal('0'), None
    text = str(raw).strip().replace(',', '').replace('₹', '').replace('$', '')
    try:
        return Decimal(text), None
    except InvalidOperation:
        return None, f'Invalid numeric value for {field_label}: "{raw}"'


@dataclass
class ProcessedRow:
    row_number: int
    data: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def is_valid(self):
        return not self.errors


@dataclass
class ProcessResult:
    total_rows: int = 0
    valid_rows: list = field(default_factory=list)
    invalid_rows: list = field(default_factory=list)
    column_map: dict = field(default_factory=dict)
    missing_required_columns: list = field(default_factory=list)
    global_error: str = ''

    @property
    def all_rows(self):
        return sorted(self.valid_rows + self.invalid_rows, key=lambda r: r.row_number)


def read_spreadsheet(file_obj, filename: str) -> pd.DataFrame:
    lower = filename.lower()
    content = file_obj.read()
    buffer = BytesIO(content)
    if lower.endswith('.csv'):
        df = pd.read_csv(buffer, dtype=str, keep_default_na=False, skip_blank_lines=True)
    else:
        engine = 'xlrd' if lower.endswith('.xls') else 'openpyxl'
        df = pd.read_excel(buffer, dtype=str, engine=engine, keep_default_na=False)
    return df


def process_spreadsheet(file_obj, filename: str, existing_invoice_numbers=None) -> ProcessResult:
    existing_invoice_numbers = {str(n).strip().lower() for n in (existing_invoice_numbers or [])}
    result = ProcessResult()

    try:
        df = read_spreadsheet(file_obj, filename)
    except Exception as exc:
        result.global_error = f'Unable to read the uploaded file. Please check the file format. ({exc})'
        return result

    if df.empty:
        result.global_error = 'The uploaded file contains no data rows.'
        return result

    column_map = build_column_map(df.columns)
    result.column_map = column_map

    missing = [f for f in REQUIRED_FIELDS if f not in column_map]
    result.missing_required_columns = missing
    if missing:
        labels = ', '.join(FIELD_LABELS.get(f, f) for f in missing)
        result.global_error = f'The uploaded file is missing required column(s): {labels}.'
        return result

    seen_in_file = {}
    row_number = 1
    total_considered = 0

    for _, raw_row in df.iterrows():
        row_number += 1  # account for header row -> spreadsheet row numbers start at 2

        values = {col: raw_row.get(col, '') for col in df.columns}
        if all(str(v).strip() == '' for v in values.values()):
            continue  # ignore completely blank rows

        total_considered += 1
        errors = []
        data = {}

        def get_raw(field_name):
            col = column_map.get(field_name)
            return values.get(col, '') if col else ''

        invoice_number = str(get_raw('invoice_number')).strip()
        if not invoice_number:
            errors.append('Invoice number is missing')
        else:
            key = invoice_number.lower()
            if key in seen_in_file:
                errors.append(f'Duplicate invoice number in this file (also row {seen_in_file[key]})')
            elif key in existing_invoice_numbers:
                errors.append('Invoice number already exists in the system')
            seen_in_file.setdefault(key, row_number)
        data['invoice_number'] = invoice_number

        parsed_date, err = parse_date_value(get_raw('invoice_date'))
        if err:
            errors.append(err)
        data['invoice_date'] = parsed_date

        supplier_name = str(get_raw('supplier_name')).strip()
        if not supplier_name:
            errors.append('Name of supplier is missing')
        data['supplier_name'] = supplier_name

        supplier_address = str(get_raw('supplier_address')).strip()
        if not supplier_address:
            errors.append('Address is missing')
        data['supplier_address'] = supplier_address

        description = str(get_raw('description')).strip()
        if not description:
            errors.append('Description of service is missing')
        data['description'] = description

        hsn = str(get_raw('hsn')).strip()
        if not hsn:
            errors.append('HSN is missing')
        data['hsn'] = hsn

        for money_field in ('taxable_value', 'tax_amount', 'total'):
            val, err = parse_decimal_value(get_raw(money_field), FIELD_LABELS[money_field])
            if err:
                errors.append(err)
            data[money_field] = val

        data['country'] = str(get_raw('country')).strip()
        data['state'] = str(get_raw('state')).strip()
        data['state_code'] = str(get_raw('state_code')).strip()
        data['place_of_supply'] = str(get_raw('place_of_supply')).strip()
        data['supplier_gstin'] = str(get_raw('supplier_gstin')).strip() or 'NA'
        data['invoice_to'] = str(get_raw('invoice_to')).strip()

        qty, _ = parse_decimal_value(get_raw('quantity'), 'Quantity', required=False)
        data['quantity'] = qty or Decimal('1')

        discount, _ = parse_decimal_value(get_raw('discount'), 'Discount', required=False)
        data['discount'] = discount or Decimal('0')

        tax_rate_raw = get_raw('tax_rate')
        if str(tax_rate_raw).strip():
            tax_rate, _ = parse_decimal_value(tax_rate_raw, 'Tax Rate', required=False)
            data['tax_rate'] = tax_rate
        else:
            data['tax_rate'] = None

        for opt_field in ('freight', 'insurance', 'packing'):
            v, _ = parse_decimal_value(get_raw(opt_field), FIELD_LABELS[opt_field], required=False)
            data[opt_field] = v or Decimal('0')

        row = ProcessedRow(row_number=row_number, data=data, errors=errors, raw={k: values.get(v, '') for k, v in column_map.items()})
        if row.is_valid:
            result.valid_rows.append(row)
        else:
            result.invalid_rows.append(row)

    result.total_rows = total_considered
    return result
