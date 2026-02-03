/**
 * SingleFileDownloadModal handles single file downloads with ALTCHA verification.
 */

export class SingleFileDownloadModal {
    /**
     * @param {HTMLDialogElement} modalElement - The modal dialog element
     * @param {Object} options - Configuration
     * @param {string} options.challengeUrl - URL for ALTCHA challenges
     * @param {string} options.downloadUrl - URL for protected download endpoint
     */
    constructor(modalElement, options) {
        this.modal = modalElement;
        this.challengeUrl = options.challengeUrl;
        this.downloadUrl = options.downloadUrl;

        // State
        this.currentFile = null;

        this._cacheElements();
        this._bindEvents();
    }

    _cacheElements() {
        this.elements = {
            filename: this.modal.querySelector('#single-download-filename'),
            altchaContainer: this.modal.querySelector('#single-altcha-container'),
            altchaWidget: this.modal.querySelector('#single-altcha-widget'),
            loading: this.modal.querySelector('#single-download-loading'),
            error: this.modal.querySelector('#single-download-error'),
            errorMessage: this.modal.querySelector('#single-error-message'),
            success: this.modal.querySelector('#single-download-success'),
            downloadLink: this.modal.querySelector('#single-download-link'),
            curlCommand: this.modal.querySelector('#single-curl-command'),
            copyBtn: this.modal.querySelector('#single-copy-curl'),
        };
    }

    _bindEvents() {
        this.elements.altchaWidget.addEventListener('verified', (e) => this._onVerified(e));
        this.elements.altchaWidget.addEventListener('error', (e) => this._onError(e));
        this.elements.copyBtn?.addEventListener('click', () => this._copyCurl());
        this.modal.addEventListener('close', () => this._reset());
    }

    /**
     * Open modal for a single file download.
     * @param {Object} file - File info
     * @param {string} file.bucket - S3 bucket
     * @param {string} file.key - S3 key
     * @param {string} file.filename - Display filename
     */
    open(file) {
        this._reset();
        this.currentFile = file;
        this.elements.filename.textContent = file.filename;
        this.modal.showModal();
    }

    close() {
        this.modal.close();
    }

    _reset() {
        this.currentFile = null;
        this.elements.altchaContainer.classList.remove('hidden');
        this.elements.loading.classList.add('hidden');
        this.elements.error.classList.add('hidden');
        this.elements.success.classList.add('hidden');
        if (this.elements.altchaWidget.reset) {
            this.elements.altchaWidget.reset();
        }
    }

    _showLoading() {
        this.elements.altchaContainer.classList.add('hidden');
        this.elements.error.classList.add('hidden');
        this.elements.success.classList.add('hidden');
        this.elements.loading.classList.remove('hidden');
    }

    _showError(message) {
        this.elements.loading.classList.add('hidden');
        this.elements.success.classList.add('hidden');
        this.elements.error.classList.remove('hidden');
        this.elements.errorMessage.textContent = message;
    }

    _showSuccess(url, filename) {
        this.elements.loading.classList.add('hidden');
        this.elements.altchaContainer.classList.add('hidden');
        this.elements.error.classList.add('hidden');
        this.elements.success.classList.remove('hidden');

        this.elements.downloadLink.href = url;
        this.elements.downloadLink.download = filename;

        const curlCmd = `curl -L -o "${filename}" "${url}"`;
        this.elements.curlCommand.textContent = curlCmd;
        this.elements.curlCommand.dataset.curl = curlCmd;
    }

    async _onVerified(event) {
        const payload = event.detail.payload;
        this._showLoading();

        try {
            const response = await fetch(this.downloadUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    altcha: payload,
                    bucket: this.currentFile.bucket,
                    key: this.currentFile.key,
                    filename: this.currentFile.filename,
                }),
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || error.error || 'Download failed');
            }

            const data = await response.json();
            this._showSuccess(data.url, data.filename);

        } catch (error) {
            this._showError(error.message);
        }
    }

    _onError(event) {
        this._showError(event.detail?.message || 'Verification failed');
    }

    async _copyCurl() {
        const curl = this.elements.curlCommand.dataset.curl;
        if (!curl) return;

        try {
            await navigator.clipboard.writeText(curl);
            this.elements.copyBtn.textContent = 'Copied!';
            this.elements.copyBtn.classList.add('btn-success');
            setTimeout(() => {
                this.elements.copyBtn.textContent = 'Copy';
                this.elements.copyBtn.classList.remove('btn-success');
            }, 2000);
        } catch (e) {
            console.error('Copy failed:', e);
        }
    }
}
