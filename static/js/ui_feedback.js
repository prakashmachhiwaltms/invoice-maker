/* Shared modern replacements for window.alert()/window.confirm(), built on
   the Bootstrap 5 bundle already loaded in base.html. Exposes
   window.UiFeedback = { showToast, showConfirm }. */
(function (global) {
    'use strict';

    var toastContainer = null;
    function ensureToastContainer() {
        if (toastContainer) return toastContainer;
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        toastContainer.style.zIndex = '1080';
        document.body.appendChild(toastContainer);
        return toastContainer;
    }

    var VARIANT_CLASSES = {
        success: 'text-bg-success',
        error: 'text-bg-danger',
        info: 'text-bg-primary',
        warning: 'text-bg-warning',
    };

    function showToast(message, options) {
        options = options || {};
        var variant = VARIANT_CLASSES[options.variant] ? options.variant : 'info';
        var container = ensureToastContainer();
        var el = document.createElement('div');
        el.className = 'toast align-items-center ' + VARIANT_CLASSES[variant] + ' border-0';
        el.setAttribute('role', 'alert');
        el.setAttribute('aria-live', 'assertive');
        el.setAttribute('aria-atomic', 'true');
        el.innerHTML =
            '<div class="d-flex">' +
                '<div class="toast-body"></div>' +
                '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>' +
            '</div>';
        el.querySelector('.toast-body').textContent = message;
        container.appendChild(el);
        var toast = new bootstrap.Toast(el, { delay: options.delay || 4500 });
        el.addEventListener('hidden.bs.toast', function () { el.remove(); });
        toast.show();
        return toast;
    }

    var confirmModalEl = null;
    var confirmModal = null;
    function ensureConfirmModal() {
        if (confirmModalEl) return;
        confirmModalEl = document.createElement('div');
        confirmModalEl.className = 'modal fade';
        confirmModalEl.tabIndex = -1;
        confirmModalEl.innerHTML =
            '<div class="modal-dialog modal-dialog-centered">' +
                '<div class="modal-content">' +
                    '<div class="modal-header">' +
                        '<h6 class="modal-title mb-0" data-confirm-title>Confirm</h6>' +
                        '<button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>' +
                    '</div>' +
                    '<div class="modal-body" data-confirm-body></div>' +
                    '<div class="modal-footer">' +
                        '<button type="button" class="btn btn-outline-soft" data-confirm-cancel data-bs-dismiss="modal">Cancel</button>' +
                        '<button type="button" class="btn btn-primary" data-confirm-ok>Confirm</button>' +
                    '</div>' +
                '</div>' +
            '</div>';
        document.body.appendChild(confirmModalEl);
        confirmModal = new bootstrap.Modal(confirmModalEl);
    }

    function showConfirm(message, options) {
        options = options || {};
        ensureConfirmModal();
        confirmModalEl.querySelector('[data-confirm-title]').textContent = options.title || 'Confirm';
        confirmModalEl.querySelector('[data-confirm-body]').textContent = message;
        var okBtn = confirmModalEl.querySelector('[data-confirm-ok]');
        okBtn.textContent = options.confirmText || 'Confirm';
        okBtn.className = 'btn ' + (options.danger ? 'btn-danger' : 'btn-primary');
        confirmModalEl.querySelector('[data-confirm-cancel]').textContent = options.cancelText || 'Cancel';

        return new Promise(function (resolve) {
            var settled = false;
            function onOk() {
                settled = true;
                resolve(true);
                confirmModal.hide();
            }
            function onHidden() {
                cleanup();
                if (!settled) resolve(false);
            }
            function cleanup() {
                okBtn.removeEventListener('click', onOk);
                confirmModalEl.removeEventListener('hidden.bs.modal', onHidden);
            }
            okBtn.addEventListener('click', onOk);
            confirmModalEl.addEventListener('hidden.bs.modal', onHidden);
            confirmModal.show();
        });
    }

    global.UiFeedback = { showToast: showToast, showConfirm: showConfirm };
})(window);
