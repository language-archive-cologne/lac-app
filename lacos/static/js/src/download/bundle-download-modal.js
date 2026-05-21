/**
 * BundleDownloadModal handles the multi-file download flow with ALTCHA verification.
 *
 * This module provides a modal interface for downloading multiple files from a bundle
 * with proof-of-work verification via ALTCHA. Users can download one package
 * file or generate scripts (Bash, PowerShell) and curl commands.
 */

import { formatBytes } from './resource-selector.js';

export class BundleDownloadModal {
    /**
     * @param {HTMLDialogElement} modalElement - The modal dialog element
     * @param {Object} options - Configuration
     * @param {string} options.challengeUrl - URL for ALTCHA challenges
     * @param {string} options.scriptsUrl - URL for script generation endpoint
     * @param {string} options.packageUrl - URL for package generation endpoint
     */
    constructor(modalElement, options) {
        this.modal = modalElement;
        this.challengeUrl = options.challengeUrl;
        this.scriptsUrl = options.scriptsUrl;
        this.packageUrl = options.packageUrl;
        this.packageMaxBytes = this._normalizeSize(
            options.packageMaxBytes ?? modalElement.dataset.packageMaxBytes,
        );

        // State
        this.bundleId = null;
        this.collectionId = null;
        this.bundles = null;  // For multi-bundle mode: [{bundle_id, resource_ids}]
        this.resourceIds = [];
        this.bundleName = '';
        this.totalSizeBytes = 0;
        this.scriptsData = null;
        this.selectedMethod = 'package';
        this.selectedScriptTab = 'powershell';
        this.isPackageAvailable = true;

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
            totalSize: this.modal.querySelector('#bundle-download-total-size'),
            bundleName: this.modal.querySelector('#bundle-download-name'),
            methods: this.modal.querySelector('#bundle-download-methods'),
            methodTabs: this.modal.querySelectorAll('[data-download-tab]'),
            methodPanels: this.modal.querySelectorAll('[data-download-panel]'),
            altchaContainer: this.modal.querySelector('#bundle-altcha-container'),
            altchaText: this.modal.querySelector('#bundle-altcha-text'),
            altchaWidget: this.modal.querySelector('#bundle-altcha-widget'),
            loading: this.modal.querySelector('#bundle-download-loading'),
            loadingMessage: this.modal.querySelector('#bundle-loading-message'),
            error: this.modal.querySelector('#bundle-download-error'),
            errorMessage: this.modal.querySelector('#bundle-error-message'),
            btnStartPackage: this.modal.querySelector('#btn-start-package'),
            btnPackageLimitUseScripts: this.modal.querySelector('#btn-package-limit-use-scripts'),
            packageDisabledNote: this.modal.querySelector('#bundle-package-disabled-note'),
            packageResult: this.modal.querySelector('#bundle-package-result'),
            packageMessage: this.modal.querySelector('#bundle-package-message'),
            btnPackageUseScripts: this.modal.querySelector('#btn-package-use-scripts'),
            btnStartScripts: this.modal.querySelector('#btn-start-scripts'),
            scriptOptions: this.modal.querySelector('#bundle-script-options'),
            scriptTabs: this.modal.querySelectorAll('[data-script-tab]'),
            scriptPanels: this.modal.querySelectorAll('[data-script-panel]'),
            skippedWarning: this.modal.querySelector('#bundle-skipped-warning'),
            skippedMessage: this.modal.querySelector('#bundle-skipped-message'),
            skippedReasons: this.modal.querySelector('#bundle-skipped-reasons'),
            expiresAt: this.modal.querySelector('#bundle-expires-at'),
            btnBash: this.modal.querySelector('#btn-download-bash'),
            btnPowershell: this.modal.querySelector('#btn-download-powershell'),
            btnCopyBashCommand: this.modal.querySelector('#btn-copy-bash-command'),
            btnCopyPowershellCommand: this.modal.querySelector('#btn-copy-powershell-command'),
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
        this.elements.btnStartPackage?.addEventListener('click', () => this._promptVerification('package'));
        this.elements.btnStartScripts?.addEventListener('click', () => this._promptVerification('scripts'));
        this.elements.btnBash.addEventListener('click', () => this.downloadScript('bash'));
        this.elements.btnPowershell.addEventListener('click', () => this.downloadScript('powershell'));
        this.elements.btnCopyBashCommand?.addEventListener('click', () => this.copyScriptRunCommand('bash'));
        this.elements.btnCopyPowershellCommand?.addEventListener('click', () => this.copyScriptRunCommand('powershell'));
        this.elements.btnManifest.addEventListener('click', () => this.downloadManifest());
        this.elements.btnCopyCurl.addEventListener('click', () => this.copyAllCurlCommands());
        this.elements.btnPackageUseScripts?.addEventListener('click', () => {
            this._reset({ method: 'scripts', preserveSelection: true });
        });
        this.elements.btnPackageLimitUseScripts?.addEventListener('click', () => {
            this._setSelectedMethod('scripts');
            this.elements.btnStartScripts?.focus();
        });

        this.elements.methodTabs.forEach((tab) => {
            tab.addEventListener('click', () => {
                this._setSelectedMethod(tab.dataset.downloadTab);
            });
        });

        this.elements.scriptTabs.forEach((tab) => {
            tab.addEventListener('click', () => {
                this._setScriptTab(tab.dataset.scriptTab);
            });
        });

        // Reset on close
        this.modal.addEventListener('close', () => this._reset());
    }

    /**
     * Open the modal for downloading selected resources.
     * @param {string} entityId - UUID of the bundle or collection
     * @param {string[]} resourceIds - Array of resource IDs to download
     * @param {string} entityName - Display name of the bundle/collection
     * @param {Object} options - Optional configuration
     * @param {boolean} options.isCollection - If true, treat entityId as collection_id
     * @param {number} options.totalSizeBytes - Total size of selected resources
     */
    open(entityId, resourceIds, entityName, options = {}) {
        this._reset();

        if (options.isCollection) {
            this.collectionId = entityId;
            this.bundleId = null;
        } else {
            this.bundleId = entityId;
            this.collectionId = null;
        }
        this.resourceIds = resourceIds;
        this.bundleName = entityName;
        this.totalSizeBytes = this._normalizeSize(options.totalSizeBytes);

        this._updateSummary(resourceIds.length, this.totalSizeBytes, entityName);
        this._syncPackageAvailability();

        this.modal.showModal();
    }

    /**
     * Open the modal for downloading resources from multiple bundles.
     * @param {Array<{bundleId: string, resourceIds: string[]}>} bundlesData - Array of bundle/resource mappings
     * @param {string} entityName - Display name for the download
     * @param {number} totalCount - Total number of files
     * @param {Object} options - Optional configuration
     * @param {number} options.totalSizeBytes - Total size of selected resources
     */
    openMultiBundles(bundlesData, entityName, totalCount, options = {}) {
        this._reset();

        this.bundles = bundlesData.map(b => ({
            bundle_id: b.bundleId,
            resource_ids: b.resourceIds,
        }));
        this.bundleId = null;
        this.collectionId = null;
        this.bundleName = entityName;
        this.totalSizeBytes = this._normalizeSize(options.totalSizeBytes);

        this._updateSummary(totalCount, this.totalSizeBytes, entityName);
        this._syncPackageAvailability();

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
    _reset(options = {}) {
        const nextMethod = options.method || 'package';
        if (!options.preserveSelection) {
            this.bundleId = null;
            this.collectionId = null;
            this.bundles = null;
            this.resourceIds = [];
            this.bundleName = '';
            this.totalSizeBytes = 0;
        }
        this.scriptsData = null;

        // Reset visibility
        this.elements.methods.classList.remove('hidden');
        this.elements.altchaContainer.classList.remove('hidden');
        this.elements.loading.classList.add('hidden');
        this.elements.error.classList.add('hidden');
        this.elements.packageResult.classList.add('hidden');
        this.elements.scriptOptions.classList.add('hidden');
        this.elements.skippedWarning.classList.add('hidden');

        // Clear file commands
        this.elements.fileCommands.innerHTML = '';

        // Reset ALTCHA widget
        if (this.elements.altchaWidget.reset) {
            this.elements.altchaWidget.reset();
        }

        this._syncPackageAvailability();
        this._setSelectedMethod(nextMethod);
        this._setScriptTab('powershell');
    }

    /**
     * Show loading state with message.
     * @param {string} message - Loading message to display
     * @private
     */
    _showLoading(message) {
        this.elements.methods.classList.add('hidden');
        this.elements.altchaContainer.classList.add('hidden');
        this.elements.error.classList.add('hidden');
        this.elements.packageResult.classList.add('hidden');
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
        this.elements.methods.classList.remove('hidden');
        this.elements.altchaContainer.classList.remove('hidden');
        this.elements.packageResult.classList.add('hidden');
        this.elements.scriptOptions.classList.add('hidden');
        this.elements.error.classList.remove('hidden');
        this.elements.errorMessage.textContent = message;
        if (this.elements.altchaWidget.reset) {
            this.elements.altchaWidget.reset();
        }
    }

    /**
     * Mark a download tab as selected.
     * @param {'package' | 'scripts'} method - Selected method
     * @private
     */
    _setSelectedMethod(method) {
        const requestedMethod = method === 'scripts' ? 'scripts' : 'package';
        this.selectedMethod = requestedMethod === 'package' && !this.isPackageAvailable
            ? 'scripts'
            : requestedMethod;

        this.elements.methodTabs.forEach((tab) => {
            const isSelected = tab.dataset.downloadTab === this.selectedMethod;
            const isDisabled = tab.dataset.downloadTab === 'package' && !this.isPackageAvailable;
            tab.classList.toggle('tab-active', isSelected);
            tab.classList.toggle('border-primary', isSelected);
            tab.classList.toggle('bg-primary', isSelected);
            tab.classList.toggle('text-primary-content', isSelected);
            tab.classList.toggle('border-base-300', !isSelected);
            tab.classList.toggle('bg-base-100', !isSelected);
            tab.classList.toggle('text-base-content', !isSelected);
            tab.classList.toggle('opacity-60', isDisabled);
            tab.classList.toggle('cursor-not-allowed', isDisabled);
            tab.disabled = isDisabled;
            tab.setAttribute('aria-selected', String(isSelected));
            tab.setAttribute('aria-disabled', String(isDisabled));
        });

        this.elements.methodPanels.forEach((panel) => {
            panel.classList.toggle('hidden', panel.dataset.downloadPanel !== this.selectedMethod);
        });

        if (this.elements.altchaText) {
            const textKey = this.selectedMethod === 'scripts' ? 'scriptsText' : 'packageText';
            this.elements.altchaText.textContent = this.selectedMethod === 'scripts'
                ? this.elements.altchaText.dataset[textKey] || 'Complete verification to generate scripts:'
                : this.elements.altchaText.dataset[textKey] || 'Complete verification to start the package download:';
        }
    }

    /**
     * Enable or disable package downloads for the current selection size.
     * @private
     */
    _syncPackageAvailability() {
        this.isPackageAvailable = !this.packageMaxBytes || this.totalSizeBytes <= this.packageMaxBytes;
        if (this.elements.btnStartPackage) {
            this.elements.btnStartPackage.disabled = !this.isPackageAvailable;
        }
        this.elements.btnPackageLimitUseScripts?.classList.toggle('hidden', this.isPackageAvailable);
        this.elements.packageDisabledNote?.classList.toggle('hidden', this.isPackageAvailable);

        if (!this.isPackageAvailable && this.selectedMethod === 'package') {
            this._setSelectedMethod('scripts');
        }
    }

    /**
     * Mark a script output tab as selected.
     * @param {'powershell' | 'bash' | 'manifest' | 'commands'} tabName - Selected script tab
     * @private
     */
    _setScriptTab(tabName) {
        const validTabs = new Set(['powershell', 'bash', 'manifest', 'commands']);
        this.selectedScriptTab = validTabs.has(tabName) ? tabName : 'powershell';

        this.elements.scriptTabs.forEach((tab) => {
            const isSelected = tab.dataset.scriptTab === this.selectedScriptTab;
            tab.classList.toggle('tab-active', isSelected);
            tab.setAttribute('aria-selected', String(isSelected));
        });

        this.elements.scriptPanels.forEach((panel) => {
            panel.classList.toggle('hidden', panel.dataset.scriptPanel !== this.selectedScriptTab);
        });
    }

    /**
     * Move attention to verification for the requested download method.
     * @param {'package' | 'scripts'} method - Requested method
     * @private
     */
    _promptVerification(method) {
        this._setSelectedMethod(method);
        this.elements.error.classList.add('hidden');

        try {
            this.elements.altchaWidget.verify?.();
        } catch (error) {
            // The widget can still be completed manually if programmatic verify is unavailable.
        }
        this.elements.altchaWidget.focus?.();
    }

    /**
     * Show package download result.
     * @param {string} filename - Downloaded package filename
     * @param {number} skippedCount - Number of skipped files
     * @private
     */
    _showPackageResult(filename, skippedCount = 0) {
        this.elements.loading.classList.add('hidden');
        this.elements.error.classList.add('hidden');
        this.elements.methods.classList.add('hidden');
        this.elements.altchaContainer.classList.add('hidden');
        this.elements.scriptOptions.classList.add('hidden');
        this.elements.packageResult.classList.remove('hidden');
        this.elements.packageMessage.textContent = skippedCount > 0
            ? `Package download started: ${filename}. ${skippedCount} file${skippedCount > 1 ? 's' : ''} could not be included; see manifest.json.`
            : `Package download started: ${filename}`;
    }

    /**
     * Show script download options after successful verification.
     * @param {Object} data - Response data from scripts endpoint
     * @private
     */
    _showScriptOptions(data) {
        this.elements.loading.classList.add('hidden');
        this.elements.error.classList.add('hidden');
        this.elements.methods.classList.add('hidden');
        this.elements.altchaContainer.classList.add('hidden');
        this.elements.packageResult.classList.add('hidden');
        this.elements.scriptOptions.classList.remove('hidden');

        // Update file count to match actual resolved count from backend
        if (data.file_count !== undefined) {
            const totalSize = data.total_size !== undefined
                ? this._normalizeSize(data.total_size)
                : this.totalSizeBytes;
            this._updateSummary(data.file_count, totalSize, this.bundleName);
        }

        // Show warning if some files were skipped
        if (data.errors && data.errors.length > 0) {
            this._showSkippedWarning(data.errors);
        } else {
            this.elements.skippedWarning.classList.add('hidden');
        }

        // Format and display expiration time
        const expiresAt = new Date(data.expires_at);
        this.elements.expiresAt.textContent = expiresAt.toLocaleString();

        // Populate individual file commands from manifest
        const files = data.scripts?.manifest?.files || [];
        this._populateFileCommands(files);
        this._setScriptTab(this.selectedScriptTab);
    }

    /**
     * Show warning about skipped files.
     * @param {Array} errors - Array of error objects from backend
     * @private
     */
    _showSkippedWarning(errors) {
        const skippedCount = errors.length;
        this.elements.skippedMessage.textContent =
            `${skippedCount} file${skippedCount > 1 ? 's' : ''} could not be included`;

        // Group errors by error type for cleaner display
        // Backend sends {resource_id, error, message}
        const reasonCounts = {};
        errors.forEach(err => {
            const reason = err.error || err.message || 'unknown error';
            reasonCounts[reason] = (reasonCounts[reason] || 0) + 1;
        });

        // Build reason list
        this.elements.skippedReasons.innerHTML = '';
        Object.entries(reasonCounts).forEach(([reason, count]) => {
            const li = document.createElement('li');
            li.textContent = count > 1 ? `${reason} (${count} files)` : reason;
            this.elements.skippedReasons.appendChild(li);
        });

        this.elements.skippedWarning.classList.remove('hidden');
    }

    /**
     * Update selected-file count, total size, and entity name in the summary.
     * @param {number} fileCount - Selected or resolved file count
     * @param {number} totalSizeBytes - Total size in bytes
     * @param {string} entityName - Display name
     * @private
     */
    _updateSummary(fileCount, totalSizeBytes, entityName) {
        this.totalSizeBytes = this._normalizeSize(totalSizeBytes);
        this.elements.fileCount.textContent = fileCount;
        if (this.elements.totalSize) {
            this.elements.totalSize.textContent = formatBytes(this.totalSizeBytes);
        }
        this.elements.bundleName.textContent = entityName;
    }

    /**
     * Coerce an unknown size input to a safe non-negative byte count.
     * @param {unknown} value - Candidate byte count
     * @returns {number} Non-negative byte count
     * @private
     */
    _normalizeSize(value) {
        const size = Number(value);
        return Number.isFinite(size) && size > 0 ? size : 0;
    }

    /**
     * Populate the individual file commands section.
     * @param {Array} files - Array of file objects from manifest
     * @private
     */
    _populateFileCommands(files) {
        this.elements.fileCommands.innerHTML = '';

        files.forEach((file) => {
            const curlCommand = `curl -L -o "${file.filename}" "${file.url}"`;
            const div = document.createElement('div');
            div.className = 'flex items-start gap-2 p-2 bg-base-100 rounded';

            div.innerHTML = `
                <div class="flex-1 min-w-0">
                    <p class="text-sm font-medium truncate">${this._escapeHtml(file.filename)}</p>
                    <code class="text-xs break-all block mt-1 text-base-content/70">${this._escapeHtml(curlCommand)}</code>
                </div>
                <button type="button" class="btn btn-ghost btn-xs flex-shrink-0" data-curl="${this._escapeAttr(curlCommand)}">
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
        if (this.selectedMethod === 'scripts') {
            await this._fetchScripts(payload);
        } else {
            await this._fetchPackage(payload);
        }
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
            const payload = this._buildRequestPayload(altchaPayload);

            const response = await fetch(this.scriptsUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this._getCsrfToken(),
                },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                const error = await this._readErrorResponse(response);
                throw new Error(error);
            }

            this.scriptsData = await response.json();
            this._showScriptOptions(this.scriptsData);

        } catch (error) {
            this._showError(error.message);
        }
    }

    /**
     * Fetch and download the package file from the API.
     * @param {string} altchaPayload - Base64-encoded ALTCHA solution
     * @private
     */
    async _fetchPackage(altchaPayload) {
        this._showLoading('Preparing download package...');

        try {
            const payload = this._buildRequestPayload(altchaPayload);

            const response = await fetch(this.packageUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this._getCsrfToken(),
                },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                const error = await this._readErrorResponse(response);
                throw new Error(error);
            }

            const blob = await response.blob();
            const filename = this._filenameFromResponse(response, 'download.tar');
            const skippedCount = Number.parseInt(response.headers.get('x-download-skipped-count') || '0', 10);
            this._downloadBlob(blob, filename, 'application/x-tar');
            this._showPackageResult(filename, Number.isNaN(skippedCount) ? 0 : skippedCount);
        } catch (error) {
            this._showError(error.message);
        }
    }

    /**
     * Build request body shared by package and script endpoints.
     * @param {string} altchaPayload - Base64-encoded ALTCHA solution
     * @returns {Object} Request payload
     * @private
     */
    _buildRequestPayload(altchaPayload) {
        const payload = {
            altcha: altchaPayload,
        };

        if (this.bundles) {
            payload.bundles = this.bundles;
            payload.entity_name = this.bundleName;
        } else if (this.collectionId) {
            payload.collection_id = this.collectionId;
            payload.resource_ids = this.resourceIds;
        } else {
            payload.bundle_id = this.bundleId;
            payload.resource_ids = this.resourceIds;
        }

        return payload;
    }

    /**
     * Download a script file.
     * @param {'bash' | 'powershell'} type - Script type to download
     */
    downloadScript(type) {
        if (!this.scriptsData?.scripts) return;

        const script = this.scriptsData.scripts[type];
        if (!script) return;

        const filename = type === 'bash' ? 'download.sh' : 'download.ps1';
        const mimeType = type === 'bash' ? 'application/x-sh' : 'application/x-powershell';

        this._downloadBlob(script, filename, mimeType);
    }

    /**
     * Download the manifest JSON file.
     */
    downloadManifest() {
        if (!this.scriptsData?.scripts?.manifest) return;

        const manifest = JSON.stringify(this.scriptsData.scripts.manifest, null, 2);
        this._downloadBlob(manifest, 'manifest.json', 'application/json');
    }

    /**
     * Copy all curl commands to clipboard.
     */
    async copyAllCurlCommands() {
        // Extract curl commands from manifest files
        const manifest = this.scriptsData?.scripts?.manifest;
        if (!manifest?.files) return;

        const commands = manifest.files
            .map(file => `curl -L -o "${file.filename}" "${file.url}"`)
            .join('\n\n');

        await this._copyToClipboard(commands, this.elements.btnCopyCurl);
    }

    /**
     * Copy the local command used after downloading a script.
     * @param {'bash' | 'powershell'} type - Script type
     */
    async copyScriptRunCommand(type) {
        const command = type === 'bash' ? 'bash download.sh' : '.\\download.ps1';
        const button = type === 'bash'
            ? this.elements.btnCopyBashCommand
            : this.elements.btnCopyPowershellCommand;

        if (!button) return;

        await this._copyToClipboard(command, button);
    }

    /**
     * Create and trigger a blob download.
     * @param {string | Blob} content - File content
     * @param {string} filename - Download filename
     * @param {string} mimeType - MIME type for the blob
     * @private
     */
    _downloadBlob(content, filename, mimeType) {
        const blob = content instanceof Blob
            ? content
            : new Blob([content], { type: mimeType });
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
     * Read an API error response as JSON or text.
     * @param {Response} response - Failed fetch response
     * @returns {Promise<string>} Error message
     * @private
     */
    async _readErrorResponse(response) {
        const contentType = response.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
            const error = await response.json();
            return error.detail || error.error || 'Download failed';
        }
        const text = await response.text();
        return text || 'Download failed';
    }

    /**
     * Extract filename from Content-Disposition.
     * @param {Response} response - Fetch response
     * @param {string} fallback - Fallback filename
     * @returns {string} Filename
     * @private
     */
    _filenameFromResponse(response, fallback) {
        const disposition = response.headers.get('content-disposition') || '';
        const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i);
        if (encoded) {
            try {
                return decodeURIComponent(encoded[1]);
            } catch (error) {
                return fallback;
            }
        }

        const plain = disposition.match(/filename="?([^";]+)"?/i);
        return plain ? plain[1] : fallback;
    }

    /**
     * Get the CSRF token rendered into the page.
     * @returns {string} CSRF token
     * @private
     */
    _getCsrfToken() {
        return this.modal.querySelector('[name=csrfmiddlewaretoken]')?.value
            || document.querySelector('[name=csrfmiddlewaretoken]')?.value
            || document.querySelector('meta[name="csrf-token"]')?.content
            || this._getCookie('csrftoken')
            || this._getCookie('__Secure-csrftoken')
            || '';
    }

    /**
     * Read a cookie value when it is not HttpOnly.
     * @param {string} name - Cookie name
     * @returns {string} Cookie value
     * @private
     */
    _getCookie(name) {
        if (!document.cookie) return '';
        const cookies = document.cookie.split(';');
        for (const rawCookie of cookies) {
            const cookie = rawCookie.trim();
            if (cookie.startsWith(`${name}=`)) {
                return decodeURIComponent(cookie.substring(name.length + 1));
            }
        }
        return '';
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
