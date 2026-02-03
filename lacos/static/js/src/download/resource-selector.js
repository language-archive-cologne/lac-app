/**
 * ResourceSelector manages checkbox selection for bundle resources.
 *
 * Expected HTML structure:
 * <div id="resource-list">
 *   <input type="checkbox" class="resource-select-all" />
 *   <div class="resource-item" data-resource-id="uuid1" data-size="1234" data-filename="file.wav">
 *     <input type="checkbox" class="resource-checkbox" />
 *     ...
 *   </div>
 * </div>
 * <button id="download-selected" disabled>Download Selected (0)</button>
 */

/**
 * Format bytes into human-readable string.
 * @param {number} bytes - Number of bytes
 * @returns {string} Formatted size string (e.g., "1.5 MB")
 */
function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

/**
 * ResourceSelector class for managing checkbox selection of bundle resources.
 */
export class ResourceSelector {
    /**
     * Create a ResourceSelector instance.
     * @param {HTMLElement} container - Container element with resource items
     * @param {Object} options - Configuration options
     * @param {string} options.downloadButtonSelector - Selector for download button
     * @param {string} options.selectAllSelector - Selector for select all checkbox
     * @param {string} options.itemSelector - Selector for resource items
     * @param {string} options.checkboxSelector - Selector for checkboxes within items
     */
    constructor(container, options = {}) {
        this.container = container;
        this.options = {
            downloadButtonSelector: options.downloadButtonSelector || '#download-selected',
            selectAllSelector: options.selectAllSelector || '.resource-select-all',
            itemSelector: options.itemSelector || '.resource-item',
            checkboxSelector: options.checkboxSelector || '.resource-checkbox',
        };

        /** @type {Set<string>} */
        this.selectedIds = new Set();

        /** @type {Array<function(string[], number): void>} */
        this.callbacks = [];

        /** @type {HTMLButtonElement|null} */
        this.downloadButton = document.querySelector(this.options.downloadButtonSelector);

        /** @type {HTMLInputElement|null} */
        // Look for select-all checkbox - first try container's data attribute, then inside container, then globally
        const selectAllId = this.container.dataset.selectAllId;
        if (selectAllId) {
            this.selectAllCheckbox = document.getElementById(selectAllId);
        } else {
            this.selectAllCheckbox = this.container.querySelector(this.options.selectAllSelector)
                || document.querySelector(this.options.selectAllSelector);
        }

        /** @type {HTMLElement|null} */
        this.selectAllLabel = this.selectAllCheckbox?.closest('label')?.querySelector('.select-all-label');

        /** @type {NodeListOf<HTMLElement>} */
        this.resourceItems = this.container.querySelectorAll(this.options.itemSelector);

        this._init();
    }

    /**
     * Initialize the selector by attaching event listeners.
     * @private
     */
    _init() {
        // Attach event listeners to individual checkboxes
        this.resourceItems.forEach((item) => {
            const checkbox = item.querySelector(this.options.checkboxSelector);
            if (checkbox) {
                checkbox.addEventListener('change', (event) => this._handleCheckboxChange(event, item));
            }
        });

        // Attach event listener to select all checkbox
        if (this.selectAllCheckbox) {
            this.selectAllCheckbox.addEventListener('change', (event) => this._handleSelectAllChange(event));
        }

        // Initial UI update
        this._updateUI();
    }

    /**
     * Handle individual checkbox change event.
     * @param {Event} event - Change event
     * @param {HTMLElement} item - Resource item element
     * @private
     */
    _handleCheckboxChange(event, item) {
        const resourceId = item.dataset.resourceId;
        const checkbox = event.target;

        if (checkbox.checked) {
            this.selectedIds.add(resourceId);
        } else {
            this.selectedIds.delete(resourceId);
        }

        this._updateUI();
        this._notifyCallbacks();
    }

    /**
     * Handle select all checkbox change event.
     * @param {Event} event - Change event
     * @private
     */
    _handleSelectAllChange(event) {
        const isChecked = event.target.checked;

        if (isChecked) {
            this.selectAll();
        } else {
            this.deselectAll();
        }
    }

    /**
     * Select all resources.
     */
    selectAll() {
        this.resourceItems.forEach((item) => {
            const resourceId = item.dataset.resourceId;
            const checkbox = item.querySelector(this.options.checkboxSelector);

            if (resourceId) {
                this.selectedIds.add(resourceId);
            }
            if (checkbox) {
                checkbox.checked = true;
            }
        });

        this._updateUI();
        this._notifyCallbacks();
    }

    /**
     * Deselect all resources.
     */
    deselectAll() {
        this.selectedIds.clear();

        this.resourceItems.forEach((item) => {
            const checkbox = item.querySelector(this.options.checkboxSelector);
            if (checkbox) {
                checkbox.checked = false;
            }
        });

        this._updateUI();
        this._notifyCallbacks();
    }

    /**
     * Toggle selection of a specific resource.
     * @param {string} resourceId - Resource ID to toggle
     */
    toggleResource(resourceId) {
        if (this.selectedIds.has(resourceId)) {
            this.selectedIds.delete(resourceId);
        } else {
            this.selectedIds.add(resourceId);
        }

        // Update the corresponding checkbox
        this.resourceItems.forEach((item) => {
            if (item.dataset.resourceId === resourceId) {
                const checkbox = item.querySelector(this.options.checkboxSelector);
                if (checkbox) {
                    checkbox.checked = this.selectedIds.has(resourceId);
                }
            }
        });

        this._updateUI();
        this._notifyCallbacks();
    }

    /**
     * Get array of selected resource IDs.
     * @returns {string[]} Array of selected resource IDs
     */
    getSelectedIds() {
        return Array.from(this.selectedIds);
    }

    /**
     * Get detailed information about selected resources.
     * @returns {Array<{id: string, filename: string, size: number}>} Selected resources info
     */
    getSelectedResources() {
        const resources = [];

        this.resourceItems.forEach((item) => {
            const resourceId = item.dataset.resourceId;
            if (this.selectedIds.has(resourceId)) {
                resources.push({
                    id: resourceId,
                    filename: item.dataset.filename || '',
                    size: parseInt(item.dataset.size, 10) || 0,
                });
            }
        });

        return resources;
    }

    /**
     * Get count of selected resources.
     * @returns {number} Number of selected resources
     */
    getSelectionCount() {
        return this.selectedIds.size;
    }

    /**
     * Get total size of selected resources in bytes.
     * @returns {number} Total size in bytes
     */
    getTotalSize() {
        let totalSize = 0;

        this.resourceItems.forEach((item) => {
            if (this.selectedIds.has(item.dataset.resourceId)) {
                totalSize += parseInt(item.dataset.size, 10) || 0;
            }
        });

        return totalSize;
    }

    /**
     * Register a callback for selection changes.
     * @param {function(string[], number): void} callback - Callback function receiving (selectedIds, totalSize)
     */
    onSelectionChange(callback) {
        if (typeof callback === 'function') {
            this.callbacks.push(callback);
        }
    }

    /**
     * Notify all registered callbacks of selection change.
     * @private
     */
    _notifyCallbacks() {
        const selectedIds = this.getSelectedIds();
        const totalSize = this.getTotalSize();

        this.callbacks.forEach((callback) => {
            callback(selectedIds, totalSize);
        });
    }

    /**
     * Update UI elements (button state, select all checkbox).
     * @private
     */
    _updateUI() {
        const count = this.getSelectionCount();
        const totalSize = this.getTotalSize();
        const totalItems = this.resourceItems.length;

        // Update download button
        if (this.downloadButton) {
            this.downloadButton.disabled = count === 0;

            // Find or create text span, preserve any icon
            let textSpan = this.downloadButton.querySelector('.btn-text');
            if (!textSpan) {
                // First time: wrap existing text in a span
                const svg = this.downloadButton.querySelector('svg');
                textSpan = document.createElement('span');
                textSpan.className = 'btn-text';
                if (svg) {
                    this.downloadButton.innerHTML = '';
                    this.downloadButton.appendChild(svg);
                    this.downloadButton.appendChild(textSpan);
                } else {
                    this.downloadButton.appendChild(textSpan);
                }
            }

            if (count === 0) {
                textSpan.textContent = 'Download Selected';
            } else {
                const sizeText = formatBytes(totalSize);
                textSpan.textContent = `Download Selected (${count}) - ${sizeText}`;
            }
        }

        // Update select all checkbox state
        if (this.selectAllCheckbox) {
            if (count === 0) {
                this.selectAllCheckbox.checked = false;
                this.selectAllCheckbox.indeterminate = false;
            } else if (count === totalItems) {
                this.selectAllCheckbox.checked = true;
                this.selectAllCheckbox.indeterminate = false;
            } else {
                this.selectAllCheckbox.checked = false;
                this.selectAllCheckbox.indeterminate = true;
            }

            // Update label text
            if (this.selectAllLabel) {
                this.selectAllLabel.textContent = count === totalItems ? 'Deselect All' : 'Select All';
            }
        }
    }
}

// Export formatBytes for external use if needed
export { formatBytes };
