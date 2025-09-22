/**
 * Multipart Upload Handler for Lacos
 * Handles large file uploads using S3 multipart upload with HTMX integration
 */

class MultipartUploadHandler {
    constructor(file, options = {}) {
        this.file = file;
        this.uploadId = null;
        this.s3Key = null;
        this.completedParts = [];
        this.chunkSize = options.chunkSize || this.calculateOptimalChunkSize(file.size);
        this.onProgress = options.onProgress || (() => {});
        this.onComplete = options.onComplete || (() => {});
        this.onError = options.onError || (() => {});
        this.folderName = options.folderName || '';

        console.log(`Initializing multipart upload for ${file.name} (${this.formatSize(file.size)})`);
    }

    calculateOptimalChunkSize(fileSize) {
        const MB = 1024 * 1024;
        const GB = 1024 * MB;

        if (fileSize <= 500 * MB) return 25 * MB;  // 100-500MB: 25MB chunks
        if (fileSize <= 1 * GB) return 50 * MB;     // 500MB-1GB: 50MB chunks
        if (fileSize <= 5 * GB) return 100 * MB;    // 1-5GB: 100MB chunks
        if (fileSize <= 50 * GB) return 250 * MB;   // 5-50GB: 250MB chunks

        // >50GB: Dynamic calculation
        const targetParts = 750;
        return Math.ceil(fileSize / targetParts);
    }

    formatSize(bytes) {
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        let size = bytes;
        let unitIndex = 0;

        while (size >= 1024 && unitIndex < units.length - 1) {
            size /= 1024;
            unitIndex++;
        }

        return unitIndex === 0 ? `${size} ${units[unitIndex]}` : `${size.toFixed(2)} ${units[unitIndex]}`;
    }

    async upload(uploadConfig) {
        try {
            // uploadConfig contains upload_id, s3_key, and parts_info
            this.uploadId = uploadConfig.upload_id;
            this.s3Key = uploadConfig.s3_key;
            const partsInfo = uploadConfig.parts_info;

            console.log(`Starting multipart upload with ${partsInfo.part_count} parts`);

            // Upload all parts
            const parts = await this.uploadParts(partsInfo);

            // Complete the upload
            await this.completeUpload(parts);

            // Notify completion
            this.onComplete({
                s3_key: this.s3Key,
                file_name: this.file.name,
                file_size: this.file.size
            });

        } catch (error) {
            console.error('Multipart upload failed:', error);
            this.onError(error);
        }
    }

    async uploadParts(partsInfo) {
        const partCount = partsInfo.part_count;
        const chunkSize = partsInfo.chunk_size;
        const completedParts = [];

        // Get presigned URLs for all parts
        const urlsResponse = await fetch('/storage/multipart/get-part-urls/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCsrfToken()
            },
            body: JSON.stringify({
                s3_key: this.s3Key,
                upload_id: this.uploadId,
                part_count: partCount
            })
        });

        if (!urlsResponse.ok) {
            throw new Error(`Failed to get part URLs: ${urlsResponse.status}`);
        }

        const urlsData = await urlsResponse.json();
        const presignedUrls = urlsData.presigned_urls;

        console.log(`Got presigned URLs for ${presignedUrls.length} parts`);

        // Upload parts in parallel batches (3 at a time)
        const batchSize = 3;
        for (let i = 0; i < partCount; i += batchSize) {
            const batch = [];

            for (let j = i; j < Math.min(i + batchSize, partCount); j++) {
                const start = j * chunkSize;
                const end = Math.min(start + chunkSize, this.file.size);
                const chunk = this.file.slice(start, end);

                batch.push(this.uploadPart(chunk, j + 1, presignedUrls[j].url));
            }

            const results = await Promise.all(batch);
            completedParts.push(...results);

            // Update progress
            const progress = (completedParts.length / partCount) * 100;
            this.onProgress({
                percent: progress,
                loaded: completedParts.length,
                total: partCount
            });
        }

        return completedParts;
    }

    async uploadPart(chunk, partNumber, presignedUrl) {
        console.log(`Uploading part ${partNumber} (${this.formatSize(chunk.size)})`);

        const response = await fetch(presignedUrl, {
            method: 'PUT',
            body: chunk,
            headers: {
                'Content-Type': this.file.type || 'application/octet-stream'
            }
        });

        if (!response.ok) {
            throw new Error(`Failed to upload part ${partNumber}: ${response.status}`);
        }

        const etag = response.headers.get('ETag');

        return {
            part_number: partNumber,
            etag: etag ? etag.replace(/"/g, '') : ''
        };
    }

    async completeUpload(parts) {
        console.log('Completing multipart upload...');

        const response = await fetch('/storage/multipart/complete/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCsrfToken()
            },
            body: JSON.stringify({
                s3_key: this.s3Key,
                upload_id: this.uploadId,
                parts: parts
            })
        });

        if (!response.ok) {
            throw new Error(`Failed to complete multipart upload: ${response.status}`);
        }

        const result = await response.json();
        console.log('Multipart upload completed successfully:', result);

        return result;
    }

    getCsrfToken() {
        // Try multiple methods to get CSRF token
        const token = document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
                     document.querySelector('meta[name="csrf-token"]')?.content ||
                     this.getCookie('csrftoken');
        return token || '';
    }

    getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let cookie of cookies) {
                cookie = cookie.trim();
                if (cookie.startsWith(name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
}

// Integration with existing upload system
async function handleLargeFileUpload(file, folderName) {
    const FILE_SIZE_THRESHOLD = 100 * 1024 * 1024; // 100MB

    // Check if file needs multipart upload
    if (file.size <= FILE_SIZE_THRESHOLD) {
        console.log('File is small enough for single upload');
        return false; // Let normal upload handle it
    }

    console.log(`File size ${file.size} exceeds threshold, using multipart upload`);

    // Create multipart handler
    const handler = new MultipartUploadHandler(file, {
        folderName: folderName,
        onProgress: (progress) => {
            updateUploadProgress(progress.percent);
            console.log(`Upload progress: ${progress.percent.toFixed(1)}%`);
        },
        onComplete: (result) => {
            console.log('Upload complete:', result);
            // Trigger HTMX event for UI update
            htmx.trigger(document.body, 'upload:complete', result);
        },
        onError: (error) => {
            console.error('Upload failed:', error);
            // Trigger HTMX event for error handling
            htmx.trigger(document.body, 'upload:error', {error: error.message});
        }
    });

    // Get upload configuration from server
    const configResponse = await fetch('/storage/presigned-urls/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': handler.getCsrfToken()
        },
        body: JSON.stringify({
            folder_name: folderName,
            files_metadata: JSON.stringify([{
                file_name: file.name,
                file_type: file.type,
                file_size: file.size
            }])
        })
    });

    if (!configResponse.ok) {
        throw new Error('Failed to get upload configuration');
    }

    const config = await configResponse.json();

    // Check if server returned multipart config
    if (config.presigned_posts && config.presigned_posts[0].upload_type === 'multipart') {
        // Start multipart upload
        await handler.upload(config.presigned_posts[0]);
        return true; // Handled by multipart
    }

    return false; // Fall back to normal upload
}

// Helper function to update progress bar
function updateUploadProgress(percent) {
    const progressBar = document.getElementById('upload-progress');
    const progressText = document.getElementById('upload-progress-text');

    if (progressBar) {
        progressBar.value = percent;
    }

    if (progressText) {
        progressText.textContent = `${Math.round(percent)}%`;
    }
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { MultipartUploadHandler, handleLargeFileUpload };
}