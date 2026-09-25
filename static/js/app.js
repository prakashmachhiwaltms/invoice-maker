document.addEventListener('DOMContentLoaded', function () {
    // ---- Sidebar toggle (mobile) ----
    var toggleBtns = document.querySelectorAll('[data-sidebar-toggle]');
    var sidebar = document.querySelector('.sidebar');
    var backdrop = document.querySelector('.sidebar-backdrop');
    toggleBtns.forEach(function (btn) {
        btn.addEventListener('click', function () {
            sidebar && sidebar.classList.toggle('open');
            backdrop && backdrop.classList.toggle('show');
        });
    });
    backdrop && backdrop.addEventListener('click', function () {
        sidebar.classList.remove('open');
        backdrop.classList.remove('show');
    });

    // ---- Auto-dismiss toasts ----
    document.querySelectorAll('.toast').forEach(function (el) {
        try {
            var toast = new bootstrap.Toast(el, { delay: 5000 });
            toast.show();
        } catch (e) { /* bootstrap not loaded yet */ }
    });

    // ---- Drag & drop upload zone ----
    var dropzone = document.querySelector('[data-dropzone]');
    if (dropzone) {
        var input = dropzone.querySelector('input[type=file]');
        var fileInfo = document.querySelector('[data-file-info]');
        var submitBtn = document.querySelector('[data-upload-submit]');

        function showFile(file) {
            if (!file) return;
            if (fileInfo) {
                fileInfo.hidden = false;
                fileInfo.querySelector('[data-file-name]').textContent = file.name;
                fileInfo.querySelector('[data-file-size]').textContent = (file.size / 1024).toFixed(1) + ' KB';
            }
            if (submitBtn) submitBtn.disabled = false;
        }

        dropzone.addEventListener('click', function (e) {
            if (e.target.tagName !== 'INPUT') input.click();
        });

        ['dragenter', 'dragover'].forEach(function (evt) {
            dropzone.addEventListener(evt, function (e) {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.add('dragover');
            });
        });
        ['dragleave', 'drop'].forEach(function (evt) {
            dropzone.addEventListener(evt, function (e) {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.remove('dragover');
            });
        });
        dropzone.addEventListener('drop', function (e) {
            var files = e.dataTransfer.files;
            if (files && files.length) {
                input.files = files;
                showFile(files[0]);
            }
        });
        input.addEventListener('change', function () {
            if (input.files && input.files.length) showFile(input.files[0]);
        });
    }

    // ---- Upload form: show progress / disable button on submit ----
    var uploadForm = document.querySelector('[data-upload-form]');
    if (uploadForm) {
        uploadForm.addEventListener('submit', function () {
            var btn = uploadForm.querySelector('[data-upload-submit]');
            var progress = document.querySelector('[data-upload-progress]');
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Processing...';
            }
            if (progress) progress.hidden = false;
        });
    }

    // ---- Generic confirm-submit forms (delete etc.) ----
    document.querySelectorAll('[data-confirm]').forEach(function (form) {
        form.addEventListener('submit', function (e) {
            var msg = form.getAttribute('data-confirm');
            if (!window.confirm(msg)) {
                e.preventDefault();
            }
        });
    });

    // ---- Select-all checkboxes for bulk actions ----
    var selectAll = document.querySelector('[data-select-all]');
    var rowChecks = document.querySelectorAll('[data-row-check]');
    var bulkBar = document.querySelector('[data-bulk-bar]');
    var bulkCount = document.querySelector('[data-bulk-count]');

    function syncBulkBar() {
        var checked = document.querySelectorAll('[data-row-check]:checked');
        if (bulkBar) bulkBar.hidden = checked.length === 0;
        if (bulkCount) bulkCount.textContent = checked.length;
        document.querySelectorAll('[data-bulk-ids-input]').forEach(function (input) {
            input.value = Array.prototype.map.call(checked, function (c) { return c.value; }).join(',');
        });
    }

    if (selectAll) {
        selectAll.addEventListener('change', function () {
            rowChecks.forEach(function (c) { c.checked = selectAll.checked; });
            syncBulkBar();
        });
    }
    rowChecks.forEach(function (c) {
        c.addEventListener('change', syncBulkBar);
    });

    document.querySelectorAll('[data-bulk-action]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var checked = document.querySelectorAll('[data-row-check]:checked');
            var ids = Array.prototype.map.call(checked, function (c) { return c.value; }).join(',');
            var url = btn.getAttribute('data-bulk-action');
            if (!ids) return;
            window.location.href = url + (url.indexOf('?') > -1 ? '&' : '?') + 'invoice_ids=' + ids;
        });
    });

    // ---- Invoice preview zoom ----
    var previewFrame = document.querySelector('[data-preview-frame]');
    var zoomLabel = document.querySelector('[data-zoom-label]');
    var zoom = 100;
    document.querySelectorAll('[data-zoom]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var delta = parseInt(btn.getAttribute('data-zoom'), 10);
            zoom = Math.max(40, Math.min(150, zoom + delta));
            if (previewFrame) previewFrame.style.transform = 'scale(' + (zoom / 100) + ')';
            if (zoomLabel) zoomLabel.textContent = zoom + '%';
        });
    });
});
