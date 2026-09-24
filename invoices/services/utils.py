import re


def safe_filename(value: str) -> str:
    """Sanitize a value (e.g. invoice number) so it is safe to use as a filename."""
    value = str(value).strip()
    value = re.sub(r'[\\/:*?"<>|]', '-', value)
    value = re.sub(r'\s+', '_', value)
    value = re.sub(r'[^A-Za-z0-9_\-.]', '', value)
    value = value.strip('.').strip('-')
    return value or 'invoice'
