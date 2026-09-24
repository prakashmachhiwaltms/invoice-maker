# Invoice Generator

A production-ready Django web application that turns an uploaded Excel/CSV file into individually generated,
professional Tax Invoices (PDF + DOCX) — one invoice per valid spreadsheet row, never merged or grouped.

## Features

- Excel/CSV upload with drag & drop, column auto-mapping, row validation (dates, numbers, duplicates, missing fields)
- One valid row → one invoice → one PDF + one DOCX (never merged)
- Server-side amount-in-words generation (Indian Lakh/Crore numbering) — the spreadsheet's broken `#NAME?`
  "In figures" column is never used
- A4, print-ready invoice template modeled on the provided `RCM-001` reference layout, fully data-driven
  (company details, invoice title, "Invoice To", footer text, signatures — nothing hard-coded)
- Company Settings, Invoice Settings, and Signature management (admin-only)
- Find & Replace across a single invoice, selected invoices, an entire batch, or global settings/template text —
  operates on structured data, then regenerates the PDF/DOCX, never edits raw PDF bytes
- Individual invoice edit with "Save" vs "Save & Regenerate PDF"
- Bulk export: ZIP of PDFs, ZIP of DOCX, CSV re-export (with real amount-in-words)
- Invoice history with search/filters, batch management, activity log, dashboard with live stats
- Django auth with roles (Admin / User), user management, password reset/change
- Centralized Decimal-based tax calculation (`invoices/services/tax_calculator.py`) — no floating point money math

## Tech stack

- Backend: Python 3, Django, Django ORM, Django Admin, Django Auth
- Database: MySQL (via `PyMySQL`, managed through phpMyAdmin/XAMPP or any MySQL server)
- Frontend: Django Templates, Bootstrap 5, Bootstrap Icons, vanilla JS
- Excel/CSV: pandas, openpyxl, xlrd
- PDF: HTML/CSS invoice template rendered to PDF with `xhtml2pdf` (pure-Python — no native GTK/Pango
  dependency, unlike WeasyPrint, so it runs out of the box on Windows)
- DOCX: python-docx
- ZIP: Python's built-in `zipfile`

## Project layout

```
invoice-maker/
├── manage.py
├── requirements.txt
├── .env.example / .env
├── config/                 # settings, urls, wsgi/asgi
├── accounts/                # auth, users, roles, activity log
├── dashboard/                # dashboard view
├── invoices/
│   ├── models.py             # InvoiceBatch, Invoice
│   ├── services/
│   │   ├── excel_processor.py    # header mapping, validation
│   │   ├── invoice_generator.py  # orchestration + template context
│   │   ├── pdf_generator.py      # HTML -> PDF (xhtml2pdf)
│   │   ├── docx_generator.py     # HTML-equivalent -> DOCX
│   │   ├── tax_calculator.py     # Decimal tax math
│   │   ├── amount_to_words.py    # Indian numbering amount-in-words
│   │   ├── find_replace.py       # structured find & replace
│   │   ├── zip_generator.py      # ZIP bundling
│   │   └── export.py             # CSV export
│   └── templates/invoices/rcm_invoice.html   # the actual invoice document
├── settings_app/             # CompanySettings, InvoiceSettings, Signature
├── templates/                 # dashboard/auth/settings/shared templates
├── static/css/app.css         # application UI (separate from the invoice's own CSS)
├── static/css/invoice.css     # invoice document styling only
└── media/                      # uploads/, signatures/, generated/{pdf,docx,zip}
```

## Local setup

1. **Create a virtual environment and install dependencies**

   ```bash
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Create the MySQL database** (via phpMyAdmin, or the `mysql` CLI):

   ```sql
   CREATE DATABASE invoice_app CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```

3. **Configure environment variables** — copy `.env.example` to `.env` and fill in a real `SECRET_KEY`
   plus your MySQL credentials (`DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`). Never commit `.env`.

4. **Run migrations and create an admin user**

   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

5. **Run the dev server**

   ```bash
   python manage.py runserver
   ```

   Visit `http://127.0.0.1:8000/`.

## Sample data

`Invoice number, Date, Name of supplier, Address, Country, Description of service, HSN, Taxable Value,
Tax amount, Total, In figures` is the expected column set (column names are matched flexibly/case-insensitively —
see `invoices/services/excel_processor.py::COLUMN_ALIASES` to add more aliases). Optional columns: Country, State,
State Code, Place of Supply, Supplier GSTIN, Invoice To, Quantity, Discount, Tax Rate, Freight, Insurance, Packing.

## Configuring the invoice template's business data

Nothing about the company name, invoice title, "Invoice To", footer text, or signatures is hard-coded — set them
under **Company Settings**, **Invoice Settings**, and **Signatures** in the app (admin role required). Changing
"Tax Invoice" to "RCM Tax Invoice" or the company name to a new legal entity takes effect on the next PDF/DOCX
generated, with no code changes.

## Production deployment notes

- Set `DEBUG=False` and a real, secret `SECRET_KEY` in `.env`.
- Set `ALLOWED_HOSTS` to your real domain(s).
- Set `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` to `True` once served over HTTPS.
- Run `python manage.py collectstatic` and serve `staticfiles/` via your web server or a CDN.
- Point `MEDIA_ROOT` at persistent, backed-up storage (uploaded spreadsheets, signatures, and every generated
  PDF/DOCX live there).
- Bulk generation currently runs synchronously inside the request; the service layer
  (`invoices/services/invoice_generator.py::process_batch_rows`) is written so it can be dropped behind a
  Celery task for very large uploads without changing its public interface.
- Run behind a real WSGI server (gunicorn/uwsgi) rather than `runserver`.
