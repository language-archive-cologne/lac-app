/**
 * Protected Download Handler
 *
 * Handles file downloads protected by ALTCHA proof-of-work verification.
 * Supports single file and batch downloads.
 */

class ProtectedDownloadHandler {
    constructor(options = {}) {
        this.challengeUrl = options.challengeUrl || '/storage/altcha/challenge/';
        this.downloadUrl = options.downloadUrl || '/storage/download/';
        this.bundleDownloadUrl = options.bundleDownloadUrl || '/storage/download/bundle/';
        this.onProgress = options.onProgress || (() => {});
        this.onError = options.onError || console.error;
    }

    /**
     * Initialize ALTCHA widget and wait for solution.
     * @returns {Promise<string>} Base64-encoded solution payload
     */
    async getAltchaSolution(widgetElement) {
        return new Promise((resolve, reject) => {
            // Listen for the verified event
            const handleVerified = (event) => {
                widgetElement.removeEventListener('verified', handleVerified);
                widgetElement.removeEventListener('error', handleError);
                resolve(event.detail.payload);
            };

            const handleError = (event) => {
                widgetElement.removeEventListener('verified', handleVerified);
                widgetElement.removeEventListener('error', handleError);
                reject(new Error(event.detail?.message || 'ALTCHA verification failed'));
            };

            widgetElement.addEventListener('verified', handleVerified);
            widgetElement.addEventListener('error', handleError);
        });
    }

    /**
     * Download a single file with ALTCHA protection.
     * @param {Object} resource - Resource info {bucket, key, filename}
     * @param {HTMLElement} widgetElement - The altcha-widget element
     * @param {Object} options - Additional options
     */
    async downloadFile(resource, widgetElement, options = {}) {
        try {
            this.onProgress('Verifying...', 0);

            // Get ALTCHA solution
            const altchaSolution = await this.getAltchaSolution(widgetElement);

            this.onProgress('Generating download link...', 50);

            // Request presigned URL
            const response = await fetch(this.downloadUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    altcha: altchaSolution,
                    bucket: resource.bucket,
                    key: resource.key,
                    filename: resource.filename,
                }),
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || error.error || 'Download failed');
            }

            const result = await response.json();

            this.onProgress('Starting download...', 100);

            if (options.showCurlCommand) {
                return result;
            }

            // Trigger browser download
            if (options.newWindow) {
                window.open(result.url, '_blank');
            } else {
                const link = document.createElement('a');
                link.href = result.url;
                link.download = result.filename;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            }

            return result;

        } catch (error) {
            this.onError(error);
            throw error;
        }
    }

    /**
     * Download multiple files with ALTCHA protection.
     * @param {Array<Object>} resources - Array of {bucket, key, filename}
     * @param {HTMLElement} widgetElement - The altcha-widget element
     * @param {Object} options - Additional options
     */
    async downloadBundle(resources, widgetElement, options = {}) {
        try {
            this.onProgress('Verifying...', 0);

            // Get ALTCHA solution
            const altchaSolution = await this.getAltchaSolution(widgetElement);

            this.onProgress('Generating download links...', 50);

            // Request presigned URLs for all resources
            const response = await fetch(this.bundleDownloadUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    altcha: altchaSolution,
                    resources: resources,
                }),
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || error.error || 'Bundle download failed');
            }

            const result = await response.json();

            this.onProgress('Downloads ready', 100);

            return result;

        } catch (error) {
            this.onError(error);
            throw error;
        }
    }

    /**
     * Copy curl command to clipboard.
     * @param {string} curlCommand - The curl command to copy
     */
    async copyCurlCommand(curlCommand) {
        try {
            await navigator.clipboard.writeText(curlCommand);
            return true;
        } catch (error) {
            // Fallback for older browsers
            const textarea = document.createElement('textarea');
            textarea.value = curlCommand;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            const success = document.execCommand('copy');
            document.body.removeChild(textarea);
            return success;
        }
    }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ProtectedDownloadHandler;
}

// Also attach to window for non-module usage
window.ProtectedDownloadHandler = ProtectedDownloadHandler;
