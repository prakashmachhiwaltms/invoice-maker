"""CSV export of processed invoice records, matching the original import
column layout but with a genuine amount-in-words value instead of #NAME?.
"""
import csv
import io


CSV_COLUMNS = [
    ('Invoice number', 'invoice_number'),
    ('Date', 'invoice_date'),
    ('Name of supplier', 'supplier_name'),
    ('Address', 'supplier_address'),
    ('Country', 'country'),
    ('Description of service', 'description'),
    ('HSN', 'hsn'),
    ('Taxable Value', 'taxable_value'),
    ('Tax amount', 'tax_amount'),
    ('Total', 'total'),
    ('In figures', 'amount_in_words'),
]


def build_invoices_csv(invoices) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([label for label, _ in CSV_COLUMNS])
    for invoice in invoices:
        row = []
        for _, attr in CSV_COLUMNS:
            value = getattr(invoice, attr)
            if attr == 'invoice_date' and value:
                value = value.strftime('%d-%m-%Y')
            row.append(value)
        writer.writerow(row)
    return output.getvalue()


def build_error_report_csv(invalid_rows) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Row #', 'Invoice number', 'Supplier', 'Errors'])
    for row in invalid_rows:
        writer.writerow([
            row.row_number,
            row.data.get('invoice_number', ''),
            row.data.get('supplier_name', ''),
            '; '.join(row.errors),
        ])
    return output.getvalue()
