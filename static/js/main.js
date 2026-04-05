/* ==========================================================================
   FCN Manager - Core JavaScript v2.0
   Toast, Loading, Search, Theme, Confirmations
   ========================================================================== */

const FCN = {
    // --- Toast Notifications ---
    toast(message, type = 'info', duration = 3000) {
        let container = document.querySelector('.toast-container-fcn');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container-fcn';
            document.body.appendChild(container);
        }
        const icons = { success: '\u2713', error: '\u2717', warning: '\u26A0', info: '\u2139' };
        const toast = document.createElement('div');
        toast.className = `toast-fcn ${type}`;
        toast.innerHTML = `<span>${icons[type] || ''}</span> ${message}`;
        container.appendChild(toast);
        setTimeout(() => {
            toast.style.animation = 'toastSlideOut 0.3s ease-in forwards';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    },

    // --- Loading Overlay ---
    _overlay: null,
    showLoading() {
        if (!this._overlay) {
            this._overlay = document.createElement('div');
            this._overlay.className = 'loading-overlay';
            this._overlay.innerHTML = '<div class="loading-spinner"></div>';
            document.body.appendChild(this._overlay);
        }
        requestAnimationFrame(() => this._overlay.classList.add('active'));
    },
    hideLoading() {
        if (this._overlay) {
            this._overlay.classList.remove('active');
        }
    },

    // --- Theme Toggle (3 modes: light → dim → dark) ---
    _themes: ['light', 'dim', 'dark'],
    _themeLabels: { light: '\u2600', dim: '\u25D0', dark: '\u263E' },
    _themeNames: { light: '明亮', dim: '柔和', dark: '深色' },
    initTheme() {
        document.documentElement.setAttribute('data-theme', 'dim');
    },
    toggleTheme() {
        const current = document.documentElement.getAttribute('data-theme') || 'light';
        const idx = this._themes.indexOf(current);
        const next = this._themes[(idx + 1) % this._themes.length];
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('fcn-theme', next);
        this.updateThemeIcon(next);
        this.toast(`${this._themeNames[next]}模式`, 'info', 1500);
    },
    updateThemeIcon(theme) {
        const btn = document.querySelector('.theme-toggle');
        if (btn) btn.textContent = this._themeLabels[theme] || '\u2600';
    },

    // --- Search / Filter ---
    initSearch(inputSelector, itemSelector, textSelector) {
        const input = document.querySelector(inputSelector);
        if (!input) return;
        input.addEventListener('input', () => {
            const q = input.value.toLowerCase().trim();
            document.querySelectorAll(itemSelector).forEach(item => {
                const texts = item.querySelectorAll(textSelector);
                let match = !q;
                texts.forEach(el => {
                    if (el.textContent.toLowerCase().includes(q)) match = true;
                });
                item.style.display = match ? '' : 'none';
            });
            // Update count if exists
            const counter = document.querySelector('.search-count');
            if (counter) {
                const visible = document.querySelectorAll(`${itemSelector}:not([style*="display: none"])`).length;
                counter.textContent = visible;
            }
        });
    },

    // --- KO Toggle (shared) ---
    initKOToggle() {
        document.querySelectorAll('.ko-toggle').forEach(btn => {
            btn.addEventListener('click', async () => {
                const pid = btn.dataset.pid, uid = btn.dataset.uid;
                btn.disabled = true;
                try {
                    const res = await fetch(`/products/${pid}/toggle_ko/${uid}`, { method: 'POST' });
                    const data = await res.json();
                    if (data.ko_hit) {
                        btn.innerHTML = '\u2713';
                        btn.className = 'btn btn-sm ko-toggle active btn-danger';
                        FCN.toast('已標記 KO', 'success');
                    } else {
                        btn.innerHTML = '\u2717';
                        btn.className = 'btn btn-sm ko-toggle btn-outline-secondary';
                        FCN.toast('已取消 KO', 'info');
                    }
                } catch (e) {
                    FCN.toast('操作失敗，請重試', 'error');
                }
                btn.disabled = false;
            });
        });
    },

    // --- Confirm Dialog (replace native confirm) ---
    confirm(message) {
        return new Promise(resolve => {
            const backdrop = document.createElement('div');
            backdrop.style.cssText = 'position:fixed;inset:0;background:rgba(15,23,42,0.5);backdrop-filter:blur(4px);z-index:9999;display:flex;align-items:center;justify-content:center;animation:fadeIn 0.2s ease-out;';
            const dialog = document.createElement('div');
            dialog.style.cssText = 'background:var(--fcn-surface);border-radius:var(--fcn-radius-lg);padding:2rem;max-width:380px;width:90%;box-shadow:var(--fcn-shadow-lg);text-align:center;';
            dialog.innerHTML = `
                <p style="font-size:0.95rem;font-weight:500;margin-bottom:1.5rem;color:var(--fcn-text);">${message}</p>
                <div style="display:flex;gap:0.75rem;justify-content:center;">
                    <button class="btn btn-sm btn-outline-secondary" style="min-width:80px;" id="_fcn_cancel">取消</button>
                    <button class="btn btn-sm btn-primary" style="min-width:80px;" id="_fcn_ok">確認</button>
                </div>`;
            backdrop.appendChild(dialog);
            document.body.appendChild(backdrop);
            dialog.querySelector('#_fcn_ok').focus();
            dialog.querySelector('#_fcn_ok').onclick = () => { backdrop.remove(); resolve(true); };
            dialog.querySelector('#_fcn_cancel').onclick = () => { backdrop.remove(); resolve(false); };
            backdrop.addEventListener('click', e => { if (e.target === backdrop) { backdrop.remove(); resolve(false); } });
        });
    },

    // --- Loading on link/form ---
    initLoadingLinks() {
        // Add loading on slow navigations
        document.querySelectorAll('a[href="/fetch_prices"]').forEach(a => {
            a.addEventListener('click', (e) => {
                e.preventDefault();
                FCN.showLoading();
                FCN.toast('正在更新收盤價...', 'info', 10000);
                window.location.href = a.href;
            });
        });
        // Form submissions with confirm
        document.querySelectorAll('form[data-confirm]').forEach(form => {
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                const ok = await FCN.confirm(form.dataset.confirm);
                if (ok) {
                    FCN.showLoading();
                    form.submit();
                }
            });
        });
    },

    // --- Flash messages to toast ---
    convertFlashToToast() {
        document.querySelectorAll('.alert-dismissible').forEach(alert => {
            const type = alert.classList.contains('alert-success') ? 'success'
                       : alert.classList.contains('alert-danger') ? 'error'
                       : alert.classList.contains('alert-warning') ? 'warning' : 'info';
            FCN.toast(alert.textContent.trim(), type, 4000);
            alert.remove();
        });
    },

    // --- Init All ---
    init() {
        this.initTheme();
        this.initKOToggle();
        this.initLoadingLinks();
        // Convert flash messages after a short delay to let page render
        setTimeout(() => this.convertFlashToToast(), 100);
    }
};

// Auto-init on DOM ready
document.addEventListener('DOMContentLoaded', () => FCN.init());
