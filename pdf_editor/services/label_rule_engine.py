"""Multi-rule label/value replacement engine for the bulk Label & Value
Editor. Pure matching/preview logic lives here; the only side effect is in
apply_rules(), which delegates the actual PDF mutation to field_service.

JSON rule shape (see the UI's label_rule_builder.js and views.py):
{
    "labels": ["Invoice To", "Bill To"],
    "match_type": "any" | "exact" | "contains" | "starts_with" | "ends_with" | "not_equal" | "regex",
    "current_value": "TMS PVT LTD",
    "case_sensitive": false,
    "whitespace_normalize": true,
    "change_label": false, "new_label": "",
    "change_separator": false, "new_separator": "",
    "new_value": "MAHENDRA PVT LTD"
}
"""
import re
from dataclasses import dataclass, field as dc_field

from . import field_service, pdf_label_detector

MATCH_TYPES = ('any', 'exact', 'contains', 'starts_with', 'ends_with', 'not_equal', 'regex')


@dataclass
class Rule:
    labels: list
    match_type: str = 'any'
    current_value: str = ''
    case_sensitive: bool = False
    whitespace_normalize: bool = True
    change_label: bool = False
    new_label: str = ''
    change_separator: bool = False
    new_separator: str = ''
    new_value: str = ''

    @property
    def label_keys(self):
        return {pdf_label_detector.normalize_label_key(l) for l in self.labels if l and l.strip()}

    def describe(self):
        labels_str = ' / '.join(self.labels) if self.labels else '(no label)'
        return f'{labels_str} → {self.match_type} → "{self.new_value}"'


def rule_from_dict(d):
    match_type = d.get('match_type') or 'any'
    if match_type not in MATCH_TYPES:
        match_type = 'any'
    labels = d.get('labels') or []
    if isinstance(labels, str):
        labels = [labels]
    return Rule(
        labels=[str(l).strip() for l in labels if str(l).strip()],
        match_type=match_type,
        current_value=d.get('current_value') or '',
        case_sensitive=bool(d.get('case_sensitive', False)),
        whitespace_normalize=bool(d.get('whitespace_normalize', True)),
        change_label=bool(d.get('change_label', False)),
        new_label=d.get('new_label') or '',
        change_separator=bool(d.get('change_separator', False)),
        new_separator=d.get('new_separator') or '',
        new_value=d.get('new_value') or '',
    )


def rules_from_payload(payload):
    return [rule_from_dict(d) for d in (payload or []) if isinstance(d, dict)]


def _normalize_whitespace(value):
    return re.sub(r'\s+', ' ', value or '').strip()


def value_matches(current_value, match_type, match_value, case_sensitive=False, whitespace_normalize=True):
    """Pure predicate for one of the 7 match types (§3-§9)."""
    current_value = current_value or ''
    match_value = match_value or ''

    if match_type == 'regex':
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            return bool(re.search(match_value, current_value, flags))
        except re.error:
            return False

    cur = _normalize_whitespace(current_value) if whitespace_normalize else current_value
    mv = _normalize_whitespace(match_value) if whitespace_normalize else match_value
    if not case_sensitive:
        cur = cur.lower()
        mv = mv.lower()

    if match_type == 'any':
        return True
    if match_type == 'exact':
        return cur == mv
    if match_type == 'contains':
        return mv in cur
    if match_type == 'starts_with':
        return cur.startswith(mv)
    if match_type == 'ends_with':
        return cur.endswith(mv)
    if match_type == 'not_equal':
        return cur != mv
    return False


def rule_matches_field(rule, pdf_field):
    if pdf_field.label_key not in rule.label_keys:
        return False
    return value_matches(
        pdf_field.value, rule.match_type, rule.current_value,
        rule.case_sensitive, rule.whitespace_normalize,
    )


@dataclass
class FieldMatch:
    field: object
    rule_indices: list

    @property
    def winning_rule_index(self):
        return min(self.rule_indices)

    @property
    def is_conflict(self):
        return len(self.rule_indices) > 1


def match_document(document, rules):
    """Sync fields to the document's current version, then return every
    FieldMatch for it (§24: detection is always live, never assumed)."""
    field_service.sync_detected_fields(document)
    matches = []
    for pdf_field in document.fields.exclude(status='REJECTED'):
        rule_indices = [i for i, rule in enumerate(rules) if rule_matches_field(rule, pdf_field)]
        if rule_indices:
            matches.append(FieldMatch(field=pdf_field, rule_indices=rule_indices))
    return matches


def resolved_replacement(rule, pdf_field):
    """What a field's label/separator/value become if `rule` wins for it."""
    new_label = rule.new_label if rule.change_label else pdf_field.label
    new_separator = rule.new_separator if rule.change_separator else pdf_field.separator
    new_value = rule.new_value
    return new_label, new_separator, new_value


@dataclass
class DocumentPreview:
    document: object
    status: str  # 'affected' | 'skipped'
    skip_reason: str = ''
    field_previews: list = dc_field(default_factory=list)  # [{field, before, after, rule_index, is_conflict, all_rule_indices}]


@dataclass
class PreviewResult:
    documents: list
    rule_summaries: list  # [{'rule_index', 'matched_pdfs', 'matched_fields'}]
    conflicts: list  # [{'document', 'field', 'rule_indices'}]
    total_pdfs: int = 0
    affected_pdfs: int = 0
    total_matches: int = 0


def build_preview(documents, rules):
    doc_previews = []
    rule_pdf_counts = {i: 0 for i in range(len(rules))}
    rule_field_counts = {i: 0 for i in range(len(rules))}
    conflicts = []
    total_matches = 0

    for document in documents:
        matches = match_document(document, rules)
        if not matches:
            labels = sorted({label for rule in rules for label in rule.labels})
            reason = f'No matching label found (looked for: {", ".join(labels)}).' if labels else 'No replacement rules configured.'
            doc_previews.append(DocumentPreview(document=document, status='skipped', skip_reason=reason))
            continue

        field_previews = []
        rules_won_here = set()
        for match in matches:
            winner = match.winning_rule_index
            rule = rules[winner]
            new_label, new_separator, new_value = resolved_replacement(rule, match.field)
            before = field_service._format_field_text(match.field.label, match.field.separator, match.field.value)
            after = field_service._format_field_text(new_label, new_separator, new_value)
            field_previews.append({
                'field': match.field, 'before': before, 'after': after,
                'rule_index': winner, 'is_conflict': match.is_conflict, 'all_rule_indices': match.rule_indices,
            })
            rules_won_here.add(winner)
            total_matches += 1
            if match.is_conflict:
                conflicts.append({'document': document, 'field': match.field, 'rule_indices': match.rule_indices})

        for i in rules_won_here:
            rule_pdf_counts[i] += 1
        for fp in field_previews:
            rule_field_counts[fp['rule_index']] += 1

        doc_previews.append(DocumentPreview(document=document, status='affected', field_previews=field_previews))

    rule_summaries = [
        {'rule_index': i, 'matched_pdfs': rule_pdf_counts[i], 'matched_fields': rule_field_counts[i]}
        for i in range(len(rules))
    ]
    affected = sum(1 for d in doc_previews if d.status == 'affected')
    return PreviewResult(
        documents=doc_previews, rule_summaries=rule_summaries, conflicts=conflicts,
        total_pdfs=len(documents), affected_pdfs=affected, total_matches=total_matches,
    )


@dataclass
class ApplyResult:
    affected: int = 0
    skipped: int = 0
    total_changes: int = 0


def apply_rules(documents, rules, user):
    """Recomputes matches fresh (never trusts a client-held preview) and
    applies at most one new PdfVersion per affected document (§30)."""
    result = ApplyResult()
    for document in documents:
        matches = match_document(document, rules)
        if not matches:
            result.skipped += 1
            continue
        edits = []
        for match in matches:
            rule = rules[match.winning_rule_index]
            new_label, new_separator, new_value = resolved_replacement(rule, match.field)
            edits.append((match.field, new_label, new_separator, new_value))
        version = field_service.apply_multiple_field_edits(document, user, edits)
        if version is not None:
            result.affected += 1
            result.total_changes += len(edits)
        else:
            result.skipped += 1
    return result


def discover_labels(documents):
    """Distinct labels across `documents` with how many contain each (§26)."""
    counts = {}
    display = {}
    for document in documents:
        field_service.sync_detected_fields(document)
        seen_keys_here = set()
        for pdf_field in document.fields.exclude(status='REJECTED'):
            if pdf_field.label_key in seen_keys_here:
                continue
            seen_keys_here.add(pdf_field.label_key)
            counts[pdf_field.label_key] = counts.get(pdf_field.label_key, 0) + 1
            display.setdefault(pdf_field.label_key, pdf_field.label)
    rows = [{'label': display[k], 'pdf_count': v} for k, v in counts.items()]
    rows.sort(key=lambda r: (-r['pdf_count'], r['label'].lower()))
    return rows
