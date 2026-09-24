"""Multi-document ("entire batch" / "selected PDFs") plain-text Find & Replace.

Label-based bulk replacement now lives in services/label_rule_engine.py
(a full multi-rule engine), not here.
"""
from dataclasses import dataclass

from . import document_service


@dataclass
class BulkPreviewRow:
    document: object
    match_count: int


def preview_bulk_replace(documents, find_text):
    rows = []
    for doc in documents:
        count = document_service.count_matches(doc, find_text)
        rows.append(BulkPreviewRow(document=doc, match_count=count))
    return rows


def apply_bulk_replace(documents, find_text, replace_text, user):
    """Only documents that actually contain find_text get a new version.
    Returns (affected_count, total_replacements)."""
    affected = 0
    total = 0
    for doc in documents:
        version, count = document_service.apply_replace_all(doc, user, find_text, replace_text)
        if version is not None:
            affected += 1
            total += count
    return affected, total
