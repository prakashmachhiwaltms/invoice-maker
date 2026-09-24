document.addEventListener('DOMContentLoaded', function () {
    var root = document.getElementById('label-editor-app');
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

    var state = {
        page: 1,
        pageCount: parseInt(root.getAttribute('data-page-count'), 10) || 1,
        zoom: 100,
        fields: [],
        blocks: [],
        selectedFieldId: null,
        mode: 'select', // 'select' | 'add-field'
        pendingManualSpan: null,
        pageWidthPt: 1, pageHeightPt: 1, imageWidth: 1, imageHeight: 1,
    };

    var batchId = root.getAttribute('data-batch-id');
    var pageDataUrlBase = root.getAttribute('data-page-data-url');
    function pageDataUrl(n) { return pageDataUrlBase.replace(/\/\d+\/$/, '/' + n + '/'); }
    function scaleX() { return state.imageWidth / state.pageWidthPt; }
    function scaleY() { return state.imageHeight / state.pageHeightPt; }

    var img = root.querySelector('[data-pdf-page-image]');
    var overlay = root.querySelector('[data-pdf-overlay]');
    var canvasWrap = root.querySelector('[data-canvas-wrap]');
    var pageCurrentEl = root.querySelector('[data-page-current]');
    var pageTotalEl = root.querySelector('[data-page-total]');
    var zoomLabel = root.querySelector('[data-canvas-zoom-label]');
    var versionLabel = root.querySelector('[data-version-label]');
    var undoBtn = root.querySelector('[data-action-undo]');
    var redoBtn = root.querySelector('[data-action-redo]');
    var fieldsTableEl = root.querySelector('[data-fields-table]');
    var summaryEl = document.querySelector('[data-detected-summary]');
    var addFieldHint = root.querySelector('[data-add-field-hint]');

    var panelEmpty = root.querySelector('[data-panel-empty]');
    var panelField = root.querySelector('[data-panel-field]');
    var panelAdd = root.querySelector('[data-panel-add]');

    function showPanel(name) {
        [panelEmpty, panelField, panelAdd].forEach(function (p) { if (p) p.hidden = true; });
        var map = { empty: panelEmpty, field: panelField, add: panelAdd };
        if (map[name]) map[name].hidden = false;
    }

    function callApi(url, body) {
        return fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
            body: JSON.stringify(body || {}),
        }).then(function (resp) {
            if (!resp.ok) {
                return resp.text().then(function (t) { throw new Error(t || ('Request failed: ' + resp.status)); });
            }
            return resp.json();
        }).catch(function (err) {
            window.alert(err.message || 'Something went wrong.');
            throw err;
        });
    }

    function applyZoom() {
        canvasWrap.style.transform = 'scale(' + (state.zoom / 100) + ')';
        if (zoomLabel) zoomLabel.textContent = state.zoom + '%';
    }
    root.querySelectorAll('[data-canvas-zoom]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var delta = parseInt(btn.getAttribute('data-canvas-zoom'), 10);
            state.zoom = Math.max(50, Math.min(200, state.zoom + delta));
            applyZoom();
        });
    });

    // ---- Page loading ----
    function onPageDataLoaded(data) {
        state.blocks = data.blocks || [];
        state.pageWidthPt = data.page_width_pt;
        state.pageHeightPt = data.page_height_pt;
        state.imageWidth = data.image_width;
        state.imageHeight = data.image_height;
        state.page = data.page;
        img.src = data.image_url;
        img.style.width = data.image_width + 'px';
        img.style.height = data.image_height + 'px';
        canvasWrap.style.width = data.image_width + 'px';
        canvasWrap.style.height = data.image_height + 'px';
        if (pageCurrentEl) pageCurrentEl.textContent = data.page;
        if (pageTotalEl) pageTotalEl.textContent = data.page_count;
        renderOverlay();
    }

    function loadPage(n) {
        return fetch(pageDataUrl(n)).then(function (r) { return r.json(); }).then(onPageDataLoaded);
    }

    root.querySelector('[data-page-prev]').addEventListener('click', function () {
        if (state.page > 1) loadPage(state.page - 1);
    });
    root.querySelector('[data-page-next]').addEventListener('click', function () {
        if (state.page < state.pageCount) loadPage(state.page + 1);
    });

    // ---- Fields loading ----
    function onFieldsLoaded(data) {
        state.fields = data.fields || [];
        if (summaryEl) {
            summaryEl.textContent = data.total + ' field' + (data.total === 1 ? '' : 's') + ' detected — ' +
                data.high_confidence + ' high confidence, ' + data.needs_review + ' need review';
        }
        if (versionLabel) versionLabel.textContent = 'Version ' + data.version_number;
        if (undoBtn) undoBtn.disabled = !data.can_undo;
        if (redoBtn) redoBtn.disabled = !data.can_redo;
        renderFieldsTable();
        renderOverlay();
    }

    function loadFields() {
        return fetch(root.getAttribute('data-fields-url')).then(function (r) { return r.json(); }).then(onFieldsLoaded);
    }

    function fieldUrl(kind, fieldId) {
        var base = root.getAttribute('data-field-' + kind + '-url');
        return base.replace('/0/' + kind + '/', '/' + fieldId + '/' + kind + '/');
    }

    // ---- Fields table (left panel) ----
    function renderFieldsTable() {
        fieldsTableEl.innerHTML = '';
        if (!state.fields.length) {
            fieldsTableEl.innerHTML = '<div class="text-muted-2 small p-3">No fields detected yet.</div>';
            return;
        }
        state.fields.forEach(function (f) {
            var row = document.createElement('div');
            row.className = 'pdf-field-row' + (f.id === state.selectedFieldId ? ' selected' : '');
            var confClass = f.confidence === 'HIGH' ? 'high' : 'review';
            var statusHtml = '';
            if (f.status === 'MANUAL') statusHtml = '<span class="status-pill manual">Manual</span>';
            else if (f.status === 'EDITED') statusHtml = '<span class="status-pill edited">Edited</span>';
            else if (f.status === 'CONFIRMED') statusHtml = '<span class="status-pill confirmed">Confirmed</span>';
            row.innerHTML =
                '<div class="field-label">' + escapeHtml(f.label) + '</div>' +
                '<div class="field-value">' + escapeHtml(f.value) + '</div>' +
                '<div class="field-meta">' +
                '<span class="confidence-pill ' + confClass + '">' + escapeHtml(f.confidence_display) + '</span>' +
                statusHtml +
                '<span class="text-muted-2" style="font-size:0.68rem;margin-left:auto;">p' + f.page + '</span>' +
                '</div>';
            row.addEventListener('click', function () { selectField(f.id, true); });
            fieldsTableEl.appendChild(row);
        });
    }

    // ---- Canvas overlay ----
    function renderOverlay() {
        overlay.innerHTML = '';
        if (state.mode === 'add-field') {
            state.blocks.forEach(function (span) {
                var box = document.createElement('div');
                box.className = 'pdf-span-box';
                box.style.left = (span.x * scaleX()) + 'px';
                box.style.top = (span.y * scaleY()) + 'px';
                box.style.width = (span.width * scaleX()) + 'px';
                box.style.height = (span.height * scaleY()) + 'px';
                box.title = span.text;
                box.addEventListener('click', function (e) {
                    e.stopPropagation();
                    onManualSpanClick(span);
                });
                overlay.appendChild(box);
            });
            return;
        }
        state.fields.filter(function (f) { return f.page === state.page; }).forEach(function (f) {
            var selected = f.id === state.selectedFieldId;
            if (f.label_bbox && f.label_bbox.width) {
                overlay.appendChild(makeFieldBox(f, f.label_bbox, 'pdf-label-box', selected));
            }
            if (f.value_bbox && f.value_bbox.width) {
                overlay.appendChild(makeFieldBox(f, f.value_bbox, 'pdf-value-box', selected));
            }
        });
    }

    function makeFieldBox(field, bbox, cls, selected) {
        var box = document.createElement('div');
        box.className = cls + (selected ? ' selected' : '');
        box.style.left = (bbox.x * scaleX()) + 'px';
        box.style.top = (bbox.y * scaleY()) + 'px';
        box.style.width = (bbox.width * scaleX()) + 'px';
        box.style.height = (bbox.height * scaleY()) + 'px';
        box.title = field.label + ': ' + field.value;
        box.addEventListener('click', function (e) {
            e.stopPropagation();
            selectField(field.id, false);
        });
        return box;
    }

    overlay.addEventListener('click', function () {
        if (state.mode === 'select') {
            state.selectedFieldId = null;
            showPanel('empty');
            renderFieldsTable();
            renderOverlay();
        }
    });

    // ---- Field selection + edit panel ----
    var customSepSelect = root.querySelector('[data-field-separator-select]');
    var customSepInput = root.querySelector('[data-field-separator-custom]');

    customSepSelect.addEventListener('change', function () {
        customSepInput.hidden = customSepSelect.value !== '__custom__';
        updateApplyToBatchLink();
    });

    function currentSeparatorValue() {
        return customSepSelect.value === '__custom__' ? customSepInput.value : customSepSelect.value;
    }

    function setSeparatorControls(sep) {
        var known = [':', '-', '–', '=', '|', '/', ''];
        if (known.indexOf(sep) >= 0) {
            customSepSelect.value = sep;
            customSepInput.hidden = true;
        } else {
            customSepSelect.value = '__custom__';
            customSepInput.hidden = false;
            customSepInput.value = sep;
        }
    }

    function findField(id) {
        for (var i = 0; i < state.fields.length; i++) {
            if (state.fields[i].id === id) return state.fields[i];
        }
        return null;
    }

    function selectField(fieldId, navigateFromTable) {
        var field = findField(fieldId);
        if (!field) return;
        state.selectedFieldId = fieldId;
        state.mode = 'select';
        addFieldHint.hidden = true;

        var goto = function () {
            showPanel('field');
            root.querySelector('[data-field-label]').value = field.label;
            root.querySelector('[data-field-value]').value = field.value;
            setSeparatorControls(field.separator);
            var badges = root.querySelector('[data-field-badges]');
            var confClass = field.confidence === 'HIGH' ? 'high' : 'review';
            badges.innerHTML = '<span class="confidence-pill ' + confClass + '">' + escapeHtml(field.confidence_display) + '</span>';
            root.querySelector('[data-field-original]').textContent =
                field.original_label + ' ' + field.original_separator + ' ' + field.original_value;
            updateApplyToBatchLink();
            renderFieldsTable();
            renderOverlay();
        };

        if (navigateFromTable && field.page !== state.page) {
            loadPage(field.page).then(goto);
        } else {
            goto();
        }
    }

    function updateApplyToBatchLink() {
        var link = root.querySelector('[data-apply-to-batch-link]');
        var field = findField(state.selectedFieldId);
        if (!field || !batchId) { link.style.display = 'none'; return; }
        link.style.display = '';
        var params = new URLSearchParams({
            scope: 'batch', batch: batchId, label: field.label,
            old_value: field.value, new_value: root.querySelector('[data-field-value]').value,
        });
        link.href = root.getAttribute('data-label-editor-home-url') + '?' + params.toString();
    }
    root.querySelector('[data-field-value]').addEventListener('input', updateApplyToBatchLink);

    root.querySelector('[data-action-apply-field]').addEventListener('click', function () {
        var field = findField(state.selectedFieldId);
        if (!field) return;
        var label = root.querySelector('[data-field-label]').value;
        var value = root.querySelector('[data-field-value]').value;
        var separator = currentSeparatorValue();
        callApi(fieldUrl('apply', field.id), { label: label, separator: separator, value: value }).then(function (data) {
            state.fields = data.fields || [];
            if (versionLabel) versionLabel.textContent = 'Version ' + data.version_number;
            if (undoBtn) undoBtn.disabled = !data.can_undo;
            if (redoBtn) redoBtn.disabled = !data.can_redo;
            renderFieldsTable();
            loadPage(state.page);
            var reselected = findField(field.id);
            if (reselected) selectField(reselected.id, false);
        });
    });

    root.querySelector('[data-action-confirm-field]').addEventListener('click', function () {
        var field = findField(state.selectedFieldId);
        if (!field) return;
        callApi(fieldUrl('confirm', field.id), {}).then(function () { loadFields(); });
    });

    root.querySelector('[data-action-reject-field]').addEventListener('click', function () {
        var field = findField(state.selectedFieldId);
        if (!field) return;
        if (!window.confirm('Reject this detected field? It will be hidden from the list (the PDF itself is not changed).')) return;
        callApi(fieldUrl('reject', field.id), {}).then(function () {
            state.selectedFieldId = null;
            showPanel('empty');
            loadFields();
        });
    });

    // ---- Add Custom Field ----
    var addFieldBtn = root.querySelector('[data-action-add-field]');
    addFieldBtn.addEventListener('click', function () {
        state.mode = state.mode === 'add-field' ? 'select' : 'add-field';
        addFieldBtn.classList.toggle('active', state.mode === 'add-field');
        addFieldHint.hidden = state.mode !== 'add-field';
        state.pendingManualSpan = null;
        state.selectedFieldId = null;
        if (state.mode === 'add-field') {
            showPanel('add');
            root.querySelector('[data-add-field-source]').textContent = 'Nothing selected yet.';
            root.querySelector('[data-add-field-label]').value = '';
            root.querySelector('[data-add-field-value]').value = '';
            root.querySelector('[data-action-save-manual-field]').disabled = true;
        } else {
            showPanel('empty');
        }
        renderOverlay();
    });

    function onManualSpanClick(span) {
        state.pendingManualSpan = span;
        root.querySelector('[data-add-field-source]').textContent = span.text;
        // Friendly prefill: split on the first common separator if present.
        var m = /^(.{1,50}?)\s*([:\-–=|/])\s*(.+)$/.exec(span.text.trim());
        if (m) {
            root.querySelector('[data-add-field-label]').value = m[1];
            root.querySelector('[data-add-field-separator]').value = m[2];
            root.querySelector('[data-add-field-value]').value = m[3];
        } else {
            root.querySelector('[data-add-field-value]').value = span.text.trim();
        }
        root.querySelector('[data-action-save-manual-field]').disabled = false;
    }

    root.querySelector('[data-action-save-manual-field]').addEventListener('click', function () {
        if (!state.pendingManualSpan) return;
        callApi(root.getAttribute('data-manual-create-url'), {
            page: state.page, span_id: state.pendingManualSpan.id,
            label: root.querySelector('[data-add-field-label]').value,
            separator: root.querySelector('[data-add-field-separator]').value,
            value: root.querySelector('[data-add-field-value]').value,
        }).then(function () {
            state.mode = 'select';
            addFieldBtn.classList.remove('active');
            addFieldHint.hidden = true;
            loadFields();
        });
    });

    // ---- Re-detect ----
    root.querySelector('[data-action-redetect]').addEventListener('click', function () {
        callApi(root.getAttribute('data-redetect-url'), {}).then(function () { loadFields(); });
    });

    // ---- Undo / Redo ----
    root.querySelector('[data-action-undo]').addEventListener('click', function () {
        callApi(root.getAttribute('data-undo-url'), { page: state.page }).then(function () {
            loadPage(state.page);
            loadFields();
        });
    });
    root.querySelector('[data-action-redo]').addEventListener('click', function () {
        callApi(root.getAttribute('data-redo-url'), { page: state.page }).then(function () {
            loadPage(state.page);
            loadFields();
        });
    });

    applyZoom();
    loadPage(1).then(loadFields);
});
