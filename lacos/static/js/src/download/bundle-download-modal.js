/**
 * BundleDownloadModal handles the multi-file download flow with ALTCHA verification.
 *
 * This module provides a modal interface for downloading multiple files from a bundle
 * with proof-of-work verification via ALTCHA. After verification, it generates
 * download scripts (Bash, PowerShell) and provides curl commands for individual files.
 */

export class BundleDownloadModal {
    /**
     * @param {HTMLDialogElement} modalElement - The modal dialog element
     * @param {Object} options - Configuration
     * @param {string} options.challengeUrl - URL for ALTCHA challenges
     * @param {string} options.scriptsUrl - URL for script generation endpoint
     */
    constructor(modalElement, options) {
        this.modal = modalElement;
        this.challengeUrl = options.challengeUrl;
        this.scriptsUrl = options.scriptsUrl;

        // State
        this.bundleId = null;
        this.resourceIds = [];
        this.bundleName = '';
        this.scriptsData = null;

        // Cache DOM elements
        this._cacheElements();

        // Bind event handlers
        this._bindEvents();
    }

    /**
     * Cache DOM element references for performance.
     * @private
     */
    _cacheElements() {
        this.elements = {
            title: this.modal.querySelector('#bundle-download-title'),
            summary: this.modal.querySelector('#bundle-download-summary'),
            fileCount: this.modal.querySelector('#bundle-download-count'),
            bundleName: this.modal.querySelector('#bundle-download-name'),
            altchaContainer: this.modal.querySelector('#bundle-altcha-container'),
            altchaWidget: this.modal.querySelector('#bundle-altcha-widget'),
            loading: this.modal.querySelector('#bundle-download-loading'),
            loadingMessage: this.modal.querySelector('#bundle-loading-message'),
            error: this.modal.querySelector('#bundle-download-error'),
            errorMessage: this.modal.querySelector('#bundle-error-message'),
            scriptOptions: this.modal.querySelector('#bundle-script-options'),
            expiresAt: this.modal.querySelector('#bundle-expires-at'),
            btnBash: this.modal.querySelector('#btn-download-bash'),
            btnPowershell: this.modal.querySelector('#btn-download-powershell'),
            btnManifest: this.modal.querySelector('#btn-download-manifest'),
            btnCopyCurl: this.modal.querySelector('#btn-copy-curl'),
            fileCommands: this.modal.querySelector('#bundle-file-commands'),
        };
    }

    /**
     * Bind event handlers.
     * @private
     */
    _bindEvents() {
        // ALTCHA verification
        this.elements.altchaWidget.addEventListener('verified', (e) => this._onAltchaVerified(e));
        this.elements.altchaWidget.addEventListener('error', (e) => this._onAltchaError(e));

        // Download buttons
        this.elements.btnBash.addEventListener('click', () => this.downloadScript('bash'));
        this.elements.btnPowershell.addEventListener('click', () => this.downloadScript('powershell'));
        this.elements.btnManifest.addEventListener('click', () => this.downloadManifest());
        this.elements.btnCopyCurl.addEventListener('click', () => this.copyAllCurlCommands());

        // Reset on close
        this.modal.addEventListener('close', () => this._reset());
    }

    /**
     * Open the modal for downloading selected resources.
     * @param {string} bundleId - UUID of the bundle
     * @param {string[]} resourceIds - Array of resource IDs to download
     * @param {string} bundleName - Display name of the bundle
     */
    open(bundleId, resourceIds, bundleName) {
        this._reset();

        this.bundleId = bundleId;
        this.resourceIds = resourceIds;
        this.bundleName = bundleName;

        // Update summary
        this.elements.fileCount.textContent = resourceIds.length;
        this.elements.bundleName.textContent = bundleName;

        this.modal.showModal();
    }

    /**
     * Close the modal.
     */
    close() {
        this.modal.close();
    }

    /**
     * Reset modal state for reuse.
     * @private
     */
    _reset() {
        this.bundleId = null;
        this.resourceIds = [];
        this.bundleName = '';
        this.scriptsData = null;

        // Reset visibility
        this.elements.altchaContainer.classList.remove('hidden');
        this.elements.loading.classList.add('hidden');
        this.elements.error.classList.add('hidden');
        this.elements.scriptOptions.classList.add('hidden');

        // Clear file commands
        this.elements.fileCommands.innerHTML = '';

        // Reset ALTCHA widget
        if (this.elements.altchaWidget.reset) {
            this.elements.altchaWidget.reset();
        }
    }

    /**
     * Show loading state with message.
     * @param {string} message - Loading message to display
     * @private
     */
    _showLoading(message) {
        this.elements.altchaContainer.classList.add('hidden');
        this.elements.error.classList.add('hidden');
        this.elements.scriptOptions.classList.add('hidden');
        this.elements.loading.classList.remove('hidden');
        this.elements.loadingMessage.textContent = message;
    }

    /**
     * Show error state with message.
     * @param {string} message - Error message to display
     * @private
     */
    _showError(message) {
        this.elements.loading.classList.add('hidden');
        this.elements.scriptOptions.classList.add('hidden');
        this.elements.error.classList.remove('hidden');
        this.elements.errorMessage.textContent = message;
    }

    /**
     * Show script download options after successful verification.
     * @param {Object} data - Response data from scripts endpoint
     * @private
     */
    _showScriptOptions(data) {
        this.elements.loading.classList.add('hidden');
        this.elements.error.classList.add('hidden');
        this.elements.altchaContainer.classList.add('hidden');
        this.elements.scriptOptions.classList.remove('hidden');

        // Format and display expiration time
        const expiresAt = new Date(data.expires_at);
        this.elements.expiresAt.textContent = expiresAt.toLocaleString();

        // Populate individual file commands
        this._populateFileCommands(data.files);
    }

    /**
     * Populate the individual file commands section.
     * @param {Array} files - Array of file objects with curl_command
     * @private
     */
    _populateFileCommands(files) {
        this.elements.fileCommands.innerHTML = '';

        files.forEach((file) => {
            const div = document.createElement('div');
            div.className = 'flex items-start gap-2 p-2 bg-base-100 rounded';

            div.innerHTML = `
                <div class="flex-1 min-w-0">
                    <p class="text-sm font-medium truncate">${this._escapeHtml(file.filename)}</p>
                    <code class="text-xs break-all block mt-1 text-base-content/70">${this._escapeHtml(file.curl_command)}</code>
                </div>
                <button type="button" class="btn btn-ghost btn-xs flex-shrink-0" data-curl="${this._escapeAttr(file.curl_command)}">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                </button>
            `;

            // Add click handler for individual copy button
            const copyBtn = div.querySelector('button');
            copyBtn.addEventListener('click', async () => {
                const curl = copyBtn.dataset.curl;
                await this._copyToClipboard(curl, copyBtn);
            });

            this.elements.fileCommands.appendChild(div);
        });
    }

    /**
     * Handle ALTCHA verification success.
     * @param {CustomEvent} event - Verified event from ALTCHA widget
     * @private
     */
    async _onAltchaVerified(event) {
        const payload = event.detail.payload;
        await this._fetchScripts(payload);
    }

    /**
     * Handle ALTCHA verification error.
     * @param {CustomEvent} event - Error event from ALTCHA widget
     * @private
     */
    _onAltchaError(event) {
        this._showError(event.detail?.message || 'Verification failed. Please try again.');
    }

    /**
     * Fetch download scripts from the API.
     * @param {string} altchaPayload - Base64-encoded ALTCHA solution
     * @private
     */
    async _fetchScripts(altchaPayload) {
        this._showLoading('Generating download scripts...');

        try {
            const response = await fetch(this.scriptsUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    altcha: altchaPayload,
                    bundle_id: this.bundleId,
                    resource_ids: this.resourceIds,
                }),
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || error.error || 'Failed to generate download scripts');
            }

            this.scriptsData = await response.json();
            this._showScriptOptions(this.scriptsData);

        } catch (error) {
            this._showError(error.message);
        }
    }

    /**
     * Download a script file.
     * @param {'bash' | 'powershell'} type - Script type to download
     */
    downloadScript(type) {
        if (!this.scriptsData) return;

        const script = type === 'bash' ? this.scriptsData.bash_script : this.scriptsData.powershell_script;
        const filename = type === 'bash' ? 'download.sh' : 'download.ps1';
        const mimeType = type === 'bash' ? 'application/x-sh' : 'application/x-powershell';

        this._downloadBlob(script, filename, mimeType);
    }

    /**
     * Download the manifest JSON file.
     */
    downloadManifest() {
        if (!this.scriptsData) return;

        const manifest = JSON.stringify(this.scriptsData.manifest, null, 2);
        this._downloadBlob(manifest, 'manifest.json', 'application/json');
    }

    /**
     * Copy all curl commands to clipboard.
     */
    async copyAllCurlCommands() {
        if (!this.scriptsData?.files) return;

        const commands = this.scriptsData.files
            .map(file => file.curl_command)
            .join('\n\n');

        await this._copyToClipboard(commands, this.elements.btnCopyCurl);
    }

    /**
     * Create and trigger a blob download.
     * @param {string} content - File content
     * @param {string} filename - Download filename
     * @param {string} mimeType - MIME type for the blob
     * @private
     */
    _downloadBlob(content, filename, mimeType) {
        const blob = new Blob([content], { type: mimeType });
        const url = URL.createObjectURL(blob);

        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        URL.revokeObjectURL(url);
    }

    /**
     * Copy text to clipboard with visual feedback.
     * @param {string} text - Text to copy
     * @param {HTMLElement} button - Button element for feedback
     * @private
     */
    async _copyToClipboard(text, button) {
        try {
            await navigator.clipboard.writeText(text);
            this._showCopyFeedback(button, true);
        } catch (error) {
            // Fallback for older browsers
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            const success = document.execCommand('copy');
            document.body.removeChild(textarea);
            this._showCopyFeedback(button, success);
        }
    }

    /**
     * Show visual feedback after copy action.
     * @param {HTMLElement} button - Button element
     * @param {boolean} success - Whether copy was successful
     * @private
     */
    _showCopyFeedback(button, success) {
        const originalHTML = button.innerHTML;
        const originalClass = button.className;

        if (success) {
            button.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                </svg>
                Copied!
            `;
            button.classList.add('btn-success');
        } else {
            button.innerHTML = 'Failed';
            button.classList.add('btn-error');
        }

        setTimeout(() => {
            button.innerHTML = originalHTML;
            button.className = originalClass;
        }, 2000);
    }

    /**
     * Escape HTML entities for safe insertion.
     * @param {string} text - Text to escape
     * @returns {string} Escaped text
     * @private
     */
    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Escape text for use in HTML attributes.
     * @param {string} text - Text to escape
     * @returns {string} Escaped text
     * @private
     */
    _escapeAttr(text) {
        return text.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }
}
