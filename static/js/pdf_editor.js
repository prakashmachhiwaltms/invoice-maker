document.addEventListener('DOMContentLoaded', function () {
    function escapeHtml(str) {
        return String(str).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    // -----------------------------------------------------------------
    // Upload page: multi-file dropzone
    // -----------------------------------------------------------------
    var pdfDropzone = document.querySelector('[data-pdf-dropzone]');
    if (pdfDropzone) {
        var pdfInput = pdfDropzone.querySelector('input[type=file]');
        var pdfFileList = document.querySelector('[data-pdf-file-list]');
        var pdfSubmitBtn = document.querySelector('[data-pdf-upload-submit]');
        var pdfDt = new DataTransfer();

        var renderPdfFileList = function () {
            if (!pdfFileList) return;
            pdfFileList.innerHTML = '';
            Array.prototype.forEach.call(pdfInput.files, function (f, i) {
                var chip = document.createElement('div');
                chip.className = 'pdf-file-chip';
                chip.innerHTML = '<i class="bi bi-file-earmark-pdf"></i><span>' + escapeHtml(f.name) +
                    '</span><span class="text-muted-2 small">' + (f.size / 1024).toFixed(1) + ' KB</span>' +
                    '<button type="button" class="pdf-file-remove" data-remove="' + i + '"><i class="bi bi-x-lg"></i></button>';
                pdfFileList.appendChild(chip);
            });
            pdfFileList.querySelectorAll('[data-remove]').forEach(function (btn) {
                btn.addEventListener('click', function (e) {
                    e.stopPropagation();
                    removePdfFileAt(parseInt(btn.getAttribute('data-remove'), 10));
                });
            });
            if (pdfSubmitBtn) pdfSubmitBtn.disabled = pdfInput.files.length === 0;
        };

        var addPdfFiles = function (fileList) {
            Array.prototype.forEach.call(fileList, function (f) { pdfDt.items.add(f); });
            pdfInput.files = pdfDt.files;
            renderPdfFileList();
        };

        var removePdfFileAt = function (index) {
            var newDt = new DataTransfer();
            Array.prototype.forEach.call(pdfInput.files, function (f, i) {
                if (i !== index) newDt.items.add(f);
            });
            pdfDt = newDt;
            pdfInput.files = pdfDt.files;
            renderPdfFileList();
        };

        pdfDropzone.addEventListener('click', function (e) {
            if (e.target.tagName !== 'INPUT' && !e.target.closest('.pdf-file-remove')) pdfInput.click();
        });
        ['dragenter', 'dragover'].forEach(function (evt) {
            pdfDropzone.addEventListener(evt, function (e) {
                e.preventDefault(); e.stopPropagation();
                pdfDropzone.classList.add('dragover');
            });
        });
        ['dragleave', 'drop'].forEach(function (evt) {
            pdfDropzone.addEventListener(evt, function (e) {
                e.preventDefault(); e.stopPropagation();
                pdfDropzone.classList.remove('dragover');
            });
        });
        pdfDropzone.addEventListener('drop', function (e) {
            if (e.dataTransfer.files && e.dataTransfer.files.length) addPdfFiles(e.dataTransfer.files);
        });
        pdfInput.addEventListener('change', function () { addPdfFiles(pdfInput.files); });

        var pdfUploadForm = document.querySelector('[data-pdf-upload-form]');
        if (pdfUploadForm) {
            pdfUploadForm.addEventListener('submit', function () {
                if (pdfSubmitBtn) {
                    pdfSubmitBtn.disabled = true;
                    pdfSubmitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Uploading...';
                }
            });
        }
    }

    // -----------------------------------------------------------------
    // Library page: "Find & Replace Selected" bulk action
    // -----------------------------------------------------------------
    document.querySelectorAll('[data-pdf-bulk-action]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var idsInput = document.querySelector('[data-bulk-ids-input]');
            var ids = idsInput ? idsInput.value : '';
            if (!ids) return;
            var url = btn.getAttribute('data-pdf-bulk-action');
            window.location.href = url + (url.indexOf('?') > -1 ? '&' : '?') + 'document_ids=' + encodeURIComponent(ids);
        });
    });

    // -----------------------------------------------------------------
    // Find & Replace page: batch picker + scope visibility
    // -----------------------------------------------------------------
    var batchPicker = document.querySelector('[data-batch-picker]');
    if (batchPicker) {
        var batchIdHidden = document.getElementById('id_batch_id');
        batchPicker.addEventListener('change', function () {
            if (batchIdHidden) batchIdHidden.value = batchPicker.value;
        });
    }
    var scopeRadios = document.querySelectorAll('input[name=scope]');
    if (scopeRadios.length) {
        var batchPickerWrap = document.querySelector('[data-scope-batch-picker]');
        var syncScopeVisibility = function () {
            var checked = document.querySelector('input[name=scope]:checked');
            if (batchPickerWrap) batchPickerWrap.hidden = !(checked && checked.value === 'batch');
        };
        scopeRadios.forEach(function (r) { r.addEventListener('change', syncScopeVisibility); });
        syncScopeVisibility();
    }

    // -----------------------------------------------------------------
    // Editor page
    // -----------------------------------------------------------------
    var root = document.getElementById('pdf-editor-app');
    if (!root) return;

    function getCookie(name) {
        var m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
        return m ? decodeURIComponent(m.pop()) : '';
    }
    var csrftoken = getCookie('csrftoken');

    var state = {
        page: 1,
        pageCount: parseInt(root.getAttribute('data-page-count'), 10) || 1,
        zoom: 100,
        selectedSpan: null,
        tool: 'select',
        blocks: [],
        pageWidthPt: 1,
        pageHeightPt: 1,
        imageWidth: 1,
        imageHeight: 1,
    };

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
    var versionLabel = document.querySelector('[data-version-label]');
    var undoBtn = root.querySelector('[data-action-undo]');
    var redoBtn = root.querySelector('[data-action-redo]');

    var panelEmpty = root.querySelector('[data-panel-empty]');
    var panelSelect = root.querySelector('[data-panel-select]');
    var panelAdd = root.querySelector('[data-panel-add]');
    var panelFind = root.querySelector('[data-panel-find]');

    function showPanel(name) {
        [panelEmpty, panelSelect, panelAdd, panelFind].forEach(function (p) { if (p) p.hidden = true; });
        var map = { empty: panelEmpty, select: panelSelect, add: panelAdd, find: panelFind };
        if (map[name]) map[name].hidden = false;
    }

    var addPending = null; // {x, y} in PDF-point space, set by clicking empty canvas while tool === 'add'

    function clearAddPosition() {
        addPending = null;
        var posEl = root.querySelector('[data-add-position]');
        var addBtn = root.querySelector('[data-action-apply-add]');
        if (posEl) posEl.textContent = 'Click the page to set position.';
        if (addBtn) addBtn.disabled = true;
    }

    function setActiveTool(tool) {
        state.tool = tool;
        state.selectedSpan = null;
        root.querySelectorAll('[data-tool]').forEach(function (b) {
            b.classList.toggle('active', b.getAttribute('data-tool') === tool);
        });
        clearAddPosition();
        showPanel(tool === 'select' ? 'empty' : (tool === 'add' ? 'add' : (tool === 'find' ? 'find' : 'empty')));
        renderOverlay();
    }

    root.querySelectorAll('[data-tool]').forEach(function (btn) {
        btn.addEventListener('click', function () { setActiveTool(btn.getAttribute('data-tool')); });
    });

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

    // ---- Dragging a selected span box to move it ----
    var activeDrag = null;

    function attachDrag(box, span) {
        box.addEventListener('mousedown', function (e) {
            if (state.tool !== 'select' || !state.selectedSpan || state.selectedSpan.id !== span.id) return;
            activeDrag = {
                box: box, span: span, startX: e.clientX, startY: e.clientY,
                origLeft: parseFloat(box.style.left), origTop: parseFloat(box.style.top),
            };
            box.classList.add('dragging');
            e.preventDefault();
        });
    }

    document.addEventListener('mousemove', function (e) {
        if (!activeDrag) return;
        var scale = state.zoom / 100;
        var dx = (e.clientX - activeDrag.startX) / scale;
        var dy = (e.clientY - activeDrag.startY) / scale;
        activeDrag.box.style.left = (activeDrag.origLeft + dx) + 'px';
        activeDrag.box.style.top = (activeDrag.origTop + dy) + 'px';
    });

    document.addEventListener('mouseup', function () {
        if (!activeDrag) return;
        var drag = activeDrag;
        activeDrag = null;
        drag.box.classList.remove('dragging');
        var newX = parseFloat(drag.box.style.left) / scaleX();
        var newY = parseFloat(drag.box.style.top) / scaleY();
        var xInput = root.querySelector('[data-prop-x]');
        var yInput = root.querySelector('[data-prop-y]');
        if (xInput) xInput.value = newX.toFixed(1);
        if (yInput) yInput.value = newY.toFixed(1);
        callApi(root.getAttribute('data-move-url'), {
            page: state.page, span_id: drag.span.id, x: newX, y: newY,
        }).then(onPageDataLoaded);
    });

    function renderOverlay() {
        overlay.innerHTML = '';
        state.blocks.forEach(function (span) {
            var box = document.createElement('div');
            box.className = 'pdf-span-box';
            if (state.selectedSpan && state.selectedSpan.id === span.id) box.classList.add('selected');
            box.style.left = (span.x * scaleX()) + 'px';
            box.style.top = (span.y * scaleY()) + 'px';
            box.style.width = (span.width * scaleX()) + 'px';
            box.style.height = (span.height * scaleY()) + 'px';
            box.title = span.text;
            box.addEventListener('click', function (e) {
                e.stopPropagation();
                onSpanClick(span);
            });
            attachDrag(box, span);
            overlay.appendChild(box);
        });
    }

    function onSpanClick(span) {
        if (state.tool === 'hide') {
            if (window.confirm('Hide/delete "' + span.text + '" from the PDF?')) {
                callApi(root.getAttribute('data-hide-url'), { page: state.page, span_id: span.id }).then(onPageDataLoaded);
            }
            return;
        }
        if (state.tool !== 'select') return;
        state.selectedSpan = span;
        showPanel('select');
        root.querySelector('[data-selected-text-display]').textContent = span.text;
        root.querySelector('[data-replace-input]').value = span.text;
        root.querySelector('[data-prop-font]').textContent = span.mapped_font + (span.bold ? ' bold' : '') + (span.italic ? ' italic' : '');
        root.querySelector('[data-prop-size]').textContent = span.font_size;
        root.querySelector('[data-prop-x]').value = span.x;
        root.querySelector('[data-prop-y]').value = span.y;
        renderOverlay();
    }

    overlay.addEventListener('click', function (e) {
        if (state.tool === 'add') {
            var rect = canvasWrap.getBoundingClientRect();
            var scale = state.zoom / 100;
            var localX = (e.clientX - rect.left) / scale;
            var localY = (e.clientY - rect.top) / scale;
            addPending = { x: localX / scaleX(), y: localY / scaleY() };
            var posEl = root.querySelector('[data-add-position]');
            var addBtn = root.querySelector('[data-action-apply-add]');
            if (posEl) posEl.textContent = 'Position set at (' + addPending.x.toFixed(1) + ', ' + addPending.y.toFixed(1) + ').';
            if (addBtn) addBtn.disabled = false;
            return;
        }
        if (state.tool === 'select') {
            state.selectedSpan = null;
            showPanel('empty');
            renderOverlay();
        }
    });

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

    function onPageDataLoaded(data) {
        state.blocks = data.blocks || [];
        state.pageWidthPt = data.page_width_pt;
        state.pageHeightPt = data.page_height_pt;
        state.imageWidth = data.image_width;
        state.imageHeight = data.image_height;
        state.selectedSpan = null;
        state.page = data.page;
        img.src = data.image_url;
        img.style.width = data.image_width + 'px';
        img.style.height = data.image_height + 'px';
        canvasWrap.style.width = data.image_width + 'px';
        canvasWrap.style.height = data.image_height + 'px';
        if (pageCurrentEl) pageCurrentEl.textContent = data.page;
        if (pageTotalEl) pageTotalEl.textContent = data.page_count;
        if (versionLabel) versionLabel.textContent = data.version_number;
        if (undoBtn) undoBtn.disabled = !data.can_undo;
        if (redoBtn) redoBtn.disabled = !data.can_redo;
        showPanel('empty');
        clearAddPosition();
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

    root.querySelector('[data-action-apply-replace]').addEventListener('click', function () {
        if (!state.selectedSpan) return;
        var newText = root.querySelector('[data-replace-input]').value;
        callApi(root.getAttribute('data-replace-url'), {
            page: state.page, span_id: state.selectedSpan.id, new_text: newText,
        }).then(onPageDataLoaded);
    });

    root.querySelector('[data-action-hide]').addEventListener('click', function () {
        if (!state.selectedSpan) return;
        if (!window.confirm('Hide/delete this text from the PDF?')) return;
        callApi(root.getAttribute('data-hide-url'), {
            page: state.page, span_id: state.selectedSpan.id,
        }).then(onPageDataLoaded);
    });

    root.querySelector('[data-action-apply-move]').addEventListener('click', function () {
        if (!state.selectedSpan) return;
        var x = parseFloat(root.querySelector('[data-prop-x]').value);
        var y = parseFloat(root.querySelector('[data-prop-y]').value);
        if (isNaN(x) || isNaN(y)) return;
        callApi(root.getAttribute('data-move-url'), {
            page: state.page, span_id: state.selectedSpan.id, x: x, y: y,
        }).then(onPageDataLoaded);
    });

    root.querySelector('[data-action-apply-add]').addEventListener('click', function () {
        if (!addPending) return;
        var textInput = root.querySelector('[data-add-text-input]');
        var text = textInput.value.trim();
        if (!text) return;
        callApi(root.getAttribute('data-add-text-url'), {
            page: state.page, x: addPending.x, y: addPending.y, text: text,
            font_size: parseFloat(root.querySelector('[data-add-size]').value) || 11,
            bold: root.querySelector('[data-add-bold]').checked,
            italic: root.querySelector('[data-add-italic]').checked,
        }).then(function (data) {
            onPageDataLoaded(data);
            textInput.value = '';
        });
    });

    root.querySelector('[data-action-undo]').addEventListener('click', function () {
        callApi(root.getAttribute('data-undo-url'), { page: state.page }).then(onPageDataLoaded);
    });
    root.querySelector('[data-action-redo]').addEventListener('click', function () {
        callApi(root.getAttribute('data-redo-url'), { page: state.page }).then(onPageDataLoaded);
    });

    function highlightMatch(m) {
        setTimeout(function () {
            var box = document.createElement('div');
            box.className = 'pdf-span-box match-highlight';
            box.style.left = (m.x * scaleX()) + 'px';
            box.style.top = (m.y * scaleY()) + 'px';
            box.style.width = (m.width * scaleX()) + 'px';
            box.style.height = (m.height * scaleY()) + 'px';
            overlay.appendChild(box);
            box.scrollIntoView({ behavior: 'smooth', block: 'center' });
            setTimeout(function () { box.remove(); }, 2500);
        }, 50);
    }

    function goToMatch(m) {
        if (state.page !== m.page) {
            loadPage(m.page).then(function () { highlightMatch(m); });
        } else {
            highlightMatch(m);
        }
    }

    root.querySelector('[data-action-find]').addEventListener('click', function () {
        var q = root.querySelector('[data-find-input]').value.trim();
        if (!q) return;
        var url = root.getAttribute('data-search-url') + '?q=' + encodeURIComponent(q);
        fetch(url).then(function (r) { return r.json(); }).then(function (data) {
            var summary = root.querySelector('[data-search-summary]');
            var results = root.querySelector('[data-search-results]');
            summary.textContent = data.count + ' match(es) found';
            results.innerHTML = '';
            data.matches.forEach(function (m) {
                var item = document.createElement('div');
                item.className = 'pdf-search-result-item';
                item.textContent = 'Page ' + m.page + ' — ' + m.text;
                item.addEventListener('click', function () { goToMatch(m); });
                results.appendChild(item);
            });
        });
    });

    root.querySelector('[data-action-replace-all]').addEventListener('click', function () {
        var find = root.querySelector('[data-find-input]').value.trim();
        var replace = root.querySelector('[data-replace-all-input]').value;
        if (!find) return;
        if (!window.confirm('Replace every occurrence of "' + find + '" in this PDF?')) return;
        callApi(root.getAttribute('data-replace-all-url'), {
            page: state.page, find_text: find, replace_text: replace,
        }).then(function (data) {
            onPageDataLoaded(data);
            window.alert(data.replaced_count + ' replacement(s) made.');
        });
    });

    applyZoom();
    loadPage(1);
});
