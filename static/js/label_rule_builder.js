document.addEventListener('DOMContentLoaded', function () {
    var root = document.getElementById('rule-builder-app');
    if (!root) return;

    function getCookie(name) {
        var m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
        return m ? decodeURIComponent(m.pop()) : '';
    }
    var csrftoken = getCookie('csrftoken');

    function escapeHtml(str) {
        return String(str == null ? '' : str).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function postJson(url, body) {
        return fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
            body: JSON.stringify(body || {}),
        }).then(function (resp) {
            if (!resp.ok) {
                return resp.json().catch(function () { return {}; }).then(function (data) {
                    throw new Error(data.error || ('Request failed: ' + resp.status));
                });
            }
            return resp.json();
        }).catch(function (err) {
            window.alert(err.message || 'Something went wrong.');
            throw err;
        });
    }

    var MATCH_TYPE_OPTIONS = [
        ['any', 'Any Value'], ['exact', 'Exact Match'], ['contains', 'Contains'],
        ['starts_with', 'Starts With'], ['ends_with', 'Ends With'],
        ['not_equal', 'Does Not Equal'], ['regex', 'Regex (Advanced)'],
    ];

    function makeEmptyRule(overrides) {
        var rule = {
            labels: [], match_type: 'any', current_value: '',
            case_sensitive: false, whitespace_normalize: true,
            change_label: false, new_label: '',
            change_separator: false, new_separator: '',
            new_value: '',
        };
        return Object.assign(rule, overrides || {});
    }

    function normalizeLoadedRule(r) {
        return makeEmptyRule({
            labels: r.labels || [], match_type: r.match_type || 'any',
            current_value: r.current_value || '', case_sensitive: !!r.case_sensitive,
            whitespace_normalize: r.whitespace_normalize !== false,
            change_label: !!r.change_label, new_label: r.new_label || '',
            change_separator: !!r.change_separator, new_separator: r.new_separator || '',
            new_value: r.new_value || '',
        });
    }

    var state = {
        rules: [],
        scope: root.getAttribute('data-initial-scope') || 'batch',
        batchId: root.getAttribute('data-initial-batch-id') || '',
        documentIds: root.getAttribute('data-initial-document-ids') || '',
        lastPreview: null,
    };

    var rulesContainer = root.querySelector('[data-rules-container]');
    var previewPanel = root.querySelector('[data-preview-panel]');
    var applyBtn = root.querySelector('[data-action-apply]');
    var scopeSummary = root.querySelector('[data-document-scope-summary]');
    var batchPicker = root.querySelector('[data-batch-picker]');

    // ---- Rule card rendering ----
    function ruleCardHtml(rule, index) {
        var labelsHtml = rule.labels.map(function (l, li) {
            return '<span class="label-chip">' + escapeHtml(l) +
                '<button type="button" data-remove-label="' + li + '" aria-label="Remove">&times;</button></span>';
        }).join('');
        var isAny = rule.match_type === 'any';
        var isRegex = rule.match_type === 'regex';
        var matchOptionsHtml = MATCH_TYPE_OPTIONS.map(function (o) {
            return '<option value="' + o[0] + '"' + (rule.match_type === o[0] ? ' selected' : '') + '>' + o[1] + '</option>';
        }).join('');

        return '' +
            '<div class="rule-card" data-rule-index="' + index + '">' +
                '<div class="rule-card-header">' +
                    '<span class="rule-card-title">Rule ' + (index + 1) + '</span>' +
                    '<div class="d-flex gap-1">' +
                        '<button type="button" class="btn btn-sm btn-outline-soft" data-rule-action="duplicate" title="Duplicate Rule"><i class="bi bi-files"></i></button>' +
                        '<button type="button" class="btn btn-sm btn-outline-soft" data-rule-action="up" title="Move Up"><i class="bi bi-arrow-up"></i></button>' +
                        '<button type="button" class="btn btn-sm btn-outline-soft" data-rule-action="down" title="Move Down"><i class="bi bi-arrow-down"></i></button>' +
                        '<button type="button" class="btn btn-sm btn-outline-danger" data-rule-action="delete" title="Delete Rule"><i class="bi bi-trash"></i></button>' +
                    '</div>' +
                '</div>' +
                '<div class="row g-2">' +
                    '<div class="col-md-5">' +
                        '<label class="form-label small mb-1">Matching Labels</label>' +
                        '<div class="label-chip-input">' + labelsHtml +
                            '<input type="text" placeholder="Type a label, press Enter" data-new-label-input>' +
                        '</div>' +
                    '</div>' +
                    '<div class="col-md-3">' +
                        '<label class="form-label small mb-1">Match Type</label>' +
                        '<select class="form-select form-select-sm" data-field="match_type">' + matchOptionsHtml + '</select>' +
                    '</div>' +
                    '<div class="col-md-4">' +
                        '<label class="form-label small mb-1">' + (isRegex ? 'Regex Pattern' : 'Current Value') + '</label>' +
                        '<input type="text" class="form-control form-control-sm" data-field="current_value" value="' + escapeHtml(rule.current_value) + '"' +
                            (isAny ? ' disabled placeholder="Not needed for Any Value"' : (isRegex ? ' placeholder="e.g. ^INV-\\d+$"' : '')) + '>' +
                    '</div>' +
                '</div>' +
                '<div class="row g-2 mt-1">' +
                    '<div class="col-md-4">' +
                        '<div class="form-check"><input class="form-check-input" type="checkbox" data-field="case_sensitive" id="rb-cs-' + index + '"' + (rule.case_sensitive ? ' checked' : '') + '>' +
                        '<label class="form-check-label small" for="rb-cs-' + index + '">Case Sensitive</label></div>' +
                    '</div>' +
                    '<div class="col-md-4">' +
                        '<div class="form-check"><input class="form-check-input" type="checkbox" data-field="whitespace_normalize" id="rb-ws-' + index + '"' + (rule.whitespace_normalize ? ' checked' : '') + '>' +
                        '<label class="form-check-label small" for="rb-ws-' + index + '">Normalize Whitespace</label></div>' +
                    '</div>' +
                '</div>' +
                '<hr class="my-2">' +
                '<div class="row g-2">' +
                    '<div class="col-md-4">' +
                        '<div class="form-check"><input class="form-check-input" type="checkbox" data-field="change_label" id="rb-cl-' + index + '"' + (rule.change_label ? ' checked' : '') + '>' +
                        '<label class="form-check-label small" for="rb-cl-' + index + '">Change Label</label></div>' +
                        '<input type="text" class="form-control form-control-sm mt-1" data-field="new_label" value="' + escapeHtml(rule.new_label) + '" placeholder="New label"' + (rule.change_label ? '' : ' disabled') + '>' +
                    '</div>' +
                    '<div class="col-md-4">' +
                        '<div class="form-check"><input class="form-check-input" type="checkbox" data-field="change_separator" id="rb-csep-' + index + '"' + (rule.change_separator ? ' checked' : '') + '>' +
                        '<label class="form-check-label small" for="rb-csep-' + index + '">Change Separator</label></div>' +
                        '<input type="text" class="form-control form-control-sm mt-1" maxlength="5" data-field="new_separator" value="' + escapeHtml(rule.new_separator) + '" placeholder="e.g. - or :"' + (rule.change_separator ? '' : ' disabled') + '>' +
                    '</div>' +
                    '<div class="col-md-4">' +
                        '<label class="form-label small mb-1">New Value <span class="text-danger">*</span></label>' +
                        '<input type="text" class="form-control form-control-sm" data-field="new_value" value="' + escapeHtml(rule.new_value) + '" placeholder="Required">' +
                    '</div>' +
                '</div>' +
            '</div>';
    }

    function renderRules() {
        rulesContainer.innerHTML = state.rules.map(ruleCardHtml).join('');
        applyBtn.disabled = true;
        state.lastPreview = null;
    }

    function addRule(overrides) {
        state.rules.push(makeEmptyRule(overrides));
        renderRules();
    }

    root.querySelector('[data-action-add-rule]').addEventListener('click', function () { addRule(); });

    rulesContainer.addEventListener('click', function (e) {
        var card = e.target.closest('[data-rule-index]');
        if (!card) return;
        var index = parseInt(card.getAttribute('data-rule-index'), 10);

        var actionBtn = e.target.closest('[data-rule-action]');
        if (actionBtn) {
            var action = actionBtn.getAttribute('data-rule-action');
            if (action === 'delete') {
                state.rules.splice(index, 1);
            } else if (action === 'duplicate') {
                state.rules.splice(index + 1, 0, JSON.parse(JSON.stringify(state.rules[index])));
            } else if (action === 'up' && index > 0) {
                var tmp = state.rules[index - 1];
                state.rules[index - 1] = state.rules[index];
                state.rules[index] = tmp;
            } else if (action === 'down' && index < state.rules.length - 1) {
                var tmp2 = state.rules[index + 1];
                state.rules[index + 1] = state.rules[index];
                state.rules[index] = tmp2;
            }
            renderRules();
            return;
        }

        var removeLabelBtn = e.target.closest('[data-remove-label]');
        if (removeLabelBtn) {
            var li = parseInt(removeLabelBtn.getAttribute('data-remove-label'), 10);
            state.rules[index].labels.splice(li, 1);
            renderRules();
        }
    });

    rulesContainer.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' || !e.target.matches('[data-new-label-input]')) return;
        e.preventDefault();
        var card = e.target.closest('[data-rule-index]');
        var index = parseInt(card.getAttribute('data-rule-index'), 10);
        var val = e.target.value.trim();
        if (val) {
            state.rules[index].labels.push(val);
            renderRules();
        }
    });

    function handleFieldUpdate(e) {
        var card = e.target.closest('[data-rule-index]');
        if (!card) return null;
        var field = e.target.getAttribute('data-field');
        if (!field) return null;
        var index = parseInt(card.getAttribute('data-rule-index'), 10);
        state.rules[index][field] = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
        applyBtn.disabled = true;
        state.lastPreview = null;
        return field;
    }
    rulesContainer.addEventListener('input', handleFieldUpdate);
    rulesContainer.addEventListener('change', function (e) {
        var field = handleFieldUpdate(e);
        if (field === 'match_type' || field === 'change_label' || field === 'change_separator') {
            renderRules();
        }
    });

    // ---- Scope ----
    function updateScopeSummary() {
        if (state.scope === 'batch') {
            scopeSummary.textContent = '';
            return;
        }
        var count = state.documentIds ? state.documentIds.split(',').filter(Boolean).length : 0;
        scopeSummary.textContent = count
            ? count + ' PDF(s) selected.'
            : 'No PDFs selected yet - use "Selected PDFs" from the Library’s bulk bar, or "Apply to entire batch" from a single PDF’s Label & Value Editor.';
    }
    root.querySelectorAll('input[name=scope]').forEach(function (radio) {
        radio.addEventListener('change', function () {
            state.scope = radio.value;
            updateScopeSummary();
        });
    });
    if (batchPicker) {
        batchPicker.addEventListener('change', function () { state.batchId = batchPicker.value; });
    }

    function buildScopePayload() {
        return { scope: state.scope, batch_id: state.batchId, document_ids: state.documentIds };
    }

    // ---- Preview ----
    function validRules() {
        return state.rules.filter(function (r) { return r.labels.length && r.new_value.trim(); });
    }

    function statCol(label, value) {
        return '<div class="col-4"><div class="fw-bold fs-5">' + value + '</div><div class="small text-muted-2">' + label + '</div></div>';
    }

    function renderPreview(data) {
        state.lastPreview = data;
        applyBtn.disabled = false;

        var html = '';
        if (data.conflicts && data.conflicts.length) {
            html += '<div class="conflict-banner"><i class="bi bi-exclamation-triangle me-1"></i>' +
                data.conflicts.length + ' field(s) matched more than one rule - the earliest-listed matching rule (highest priority) was used for each.</div>';
        }

        html += '<div class="surface-card mb-3"><div class="surface-card-header"><span class="fw-semibold">Replacement Preview</span></div>' +
            '<div class="surface-card-body"><div class="row text-center mb-2">' +
            statCol('PDFs scanned', data.total_pdfs) + statCol('PDFs affected', data.affected_pdfs) + statCol('Total matches', data.total_matches) +
            '</div>';
        data.rule_summaries.forEach(function (rs, i) {
            html += '<div class="d-flex justify-content-between border-top py-2"><span class="small">Rule ' + (i + 1) + '</span>' +
                '<span class="text-muted-2 small">' + rs.matched_pdfs + ' PDF(s), ' + rs.matched_fields + ' field(s)</span></div>';
        });
        html += '</div></div>';

        html += '<div class="surface-card"><div class="surface-card-header"><span class="fw-semibold">Per-PDF Preview</span></div><div class="surface-card-body p-2">';
        if (!data.documents.length) {
            html += '<div class="empty-state"><p class="mb-0">No PDFs in this scope.</p></div>';
        }
        data.documents.forEach(function (doc, di) {
            html += '<div class="preview-doc-card"><div class="preview-doc-header" data-toggle-doc="' + di + '">' +
                '<span class="fw-semibold small">' + escapeHtml(doc.filename) + '</span>' +
                (doc.status === 'affected'
                    ? '<span class="pill pill-success">' + doc.fields.length + ' change(s)</span>'
                    : '<span class="pill pill-neutral">Skipped</span>') +
                '</div><div class="preview-doc-body" data-doc-body="' + di + '" hidden>';
            if (doc.status === 'skipped') {
                html += '<div class="text-muted-2 small">' + escapeHtml(doc.skip_reason) + '</div>';
            } else {
                doc.fields.forEach(function (f) {
                    html += '<div class="preview-field-row">' +
                        '<span class="small fw-semibold" style="min-width:110px;">' + escapeHtml(f.label) + '</span>' +
                        '<span class="small text-muted-2">' + escapeHtml(f.before) + '</span>' +
                        '<span class="preview-arrow"><i class="bi bi-arrow-right"></i></span>' +
                        '<span class="small text-success fw-semibold">' + escapeHtml(f.after) + '</span>' +
                        (f.is_conflict ? ' <span class="pill pill-warning" style="font-size:0.65rem;">conflict</span>' : '') +
                        '</div>';
                });
            }
            html += '</div></div>';
        });
        html += '</div></div>';

        previewPanel.innerHTML = html;
        previewPanel.querySelectorAll('[data-toggle-doc]').forEach(function (header) {
            header.addEventListener('click', function () {
                var idx = header.getAttribute('data-toggle-doc');
                var body = previewPanel.querySelector('[data-doc-body="' + idx + '"]');
                body.hidden = !body.hidden;
            });
        });
    }

    root.querySelector('[data-action-preview]').addEventListener('click', function () {
        var rules = validRules();
        if (!rules.length) {
            window.alert('Add at least one rule with a label and a New Value.');
            return;
        }
        if (state.scope !== 'batch' && !state.documentIds) {
            window.alert('No PDFs are selected for this scope.');
            return;
        }
        if (state.scope === 'batch' && !state.batchId) {
            window.alert('Choose a batch first.');
            return;
        }
        var payload = buildScopePayload();
        payload.rules = rules;
        postJson(root.getAttribute('data-preview-url'), payload).then(renderPreview);
    });

    applyBtn.addEventListener('click', function () {
        if (!state.lastPreview) return;
        var msg = 'Apply ' + state.lastPreview.total_matches + ' change(s) across ' + state.lastPreview.affected_pdfs +
            ' PDF(s)? Each affected PDF gets a new version - originals are kept.';
        if (!window.confirm(msg)) return;
        var payload = buildScopePayload();
        payload.rules = validRules();
        postJson(root.getAttribute('data-apply-url'), payload).then(function (data) {
            window.alert('Updated ' + data.affected + ' PDF(s), ' + data.total_changes + ' field(s) changed. ' + data.skipped + ' PDF(s) skipped (no match).');
            window.location.href = '/pdf-editor/library/';
        });
    });

    // ---- Detected Labels discovery ----
    var discoveredBox = root.querySelector('[data-discovered-labels]');
    var discoveredSummary = root.querySelector('[data-discovered-summary]');
    var discoveredChips = root.querySelector('[data-discovered-chips]');
    root.querySelector('[data-action-discover-labels]').addEventListener('click', function () {
        if (state.scope !== 'batch' && !state.documentIds) {
            window.alert('No PDFs are selected for this scope.');
            return;
        }
        if (state.scope === 'batch' && !state.batchId) {
            window.alert('Choose a batch first.');
            return;
        }
        postJson(root.getAttribute('data-discover-url'), buildScopePayload()).then(function (data) {
            discoveredBox.hidden = false;
            discoveredSummary.textContent = 'Detected ' + data.labels.length + ' label(s) across ' + data.pdf_count + ' PDF(s). Click one to add a rule for it.';
            discoveredChips.innerHTML = '';
            data.labels.forEach(function (row) {
                var chip = document.createElement('span');
                chip.className = 'discovered-label-chip';
                chip.textContent = row.label + ' (' + row.pdf_count + ')';
                chip.addEventListener('click', function () { addRule({ labels: [row.label] }); });
                discoveredChips.appendChild(chip);
            });
        });
    });

    // ---- Rule set save/load ----
    var loadSelect = root.querySelector('[data-load-rule-set]');
    var ruleSetsUrl = root.getAttribute('data-rule-sets-url');
    var ruleSetDetailUrlBase = root.getAttribute('data-rule-set-detail-url-base');

    function loadRuleSetOptions() {
        fetch(ruleSetsUrl).then(function (r) { return r.json(); }).then(function (data) {
            loadSelect.innerHTML = '<option value="">Load Rule Set...</option>';
            (data.rule_sets || []).forEach(function (rs) {
                var opt = document.createElement('option');
                opt.value = rs.id;
                opt.textContent = rs.name;
                loadSelect.appendChild(opt);
            });
        });
    }

    loadSelect.addEventListener('change', function () {
        if (!loadSelect.value) return;
        var url = ruleSetDetailUrlBase.replace('/0/', '/' + loadSelect.value + '/');
        fetch(url).then(function (r) { return r.json(); }).then(function (data) {
            state.rules = (data.rules || []).map(normalizeLoadedRule);
            if (!state.rules.length) state.rules = [makeEmptyRule()];
            renderRules();
        });
    });

    root.querySelector('[data-action-save-rule-set]').addEventListener('click', function () {
        var name = root.querySelector('[data-rule-set-name]').value.trim();
        if (!name) {
            window.alert('Enter a rule set name first.');
            return;
        }
        var rules = validRules();
        if (!rules.length) {
            window.alert('Add at least one complete rule before saving.');
            return;
        }
        postJson(ruleSetsUrl, { name: name, rules: rules }).then(function () {
            window.alert('Rule set "' + name + '" saved.');
            loadRuleSetOptions();
        });
    });

    // ---- Initial state ----
    var initialRulesEl = document.getElementById('initial-rules-data');
    var initialRules = [];
    try {
        initialRules = initialRulesEl ? JSON.parse(initialRulesEl.textContent) : [];
    } catch (e) { initialRules = []; }

    var initialRadio = root.querySelector('input[name=scope][value="' + state.scope + '"]');
    if (initialRadio) {
        initialRadio.checked = true;
        initialRadio.dispatchEvent(new Event('change'));
    }
    if (state.batchId && batchPicker) {
        batchPicker.value = state.batchId;
    }

    state.rules = initialRules.length ? initialRules.map(normalizeLoadedRule) : [makeEmptyRule()];
    renderRules();
    updateScopeSummary();
    loadRuleSetOptions();
});
