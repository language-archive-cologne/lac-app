/**
 * Multipart Upload Client
 * 
 * This module provides functionality for handling S3 multipart uploads directly from the browser.
 * It supports uploading large files by splitting them into parts and uploading them in parallel.
 * 
 * Usage:
 * 1. Create a new instance of MultipartUploadClient
 * 2. Call uploadFile() with the file to upload
 * 3. Monitor progress through the onProgress callback
 * 4. Handle completion through the onComplete callback
 */

class MultipartUploadClient {
    /**
     * Constructor for MultipartUploadClient
     * 
     * @param {Object} options - Configuration options
     * @param {string} options.csrfToken - The CSRF token for Django requests
     * @param {string} options.pathPrefix - The S3 path prefix for the upload (e.g., folder name)
     * @param {number} options.partSize - Size of each part in bytes (default: 5MB)
     * @param {number} options.maxConcurrentUploads - Maximum number of concurrent uploads (default: 3)
     * @param {Function} options.onProgress - Callback for progress updates
     * @param {Function} options.onComplete - Callback for upload completion
     * @param {Function} options.onError - Callback for errors
     */
    constructor(options) {
        this.csrfToken = options.csrfToken;
        this.pathPrefix = options.pathPrefix || '';
        this.partSize = options.partSize || 5 * 1024 * 1024; // Default to 5MB
        this.maxConcurrentUploads = options.maxConcurrentUploads || 3;
        this.onProgress = options.onProgress || function() {};
        this.onComplete = options.onComplete || function() {};
        this.onError = options.onError || function() {};
        
        // Internal state
        this.activeUploads = 0;
        this.aborted = false;
    }
    
    /**
     * Upload a file using multipart upload
     * 
     * @param {File} file - The file to upload
     */
    async uploadFile(file) {
        try {
            if (!file) {
                throw new Error('No file provided');
            }
            
            console.log(`Starting multipart upload for ${file.name} (${this.formatSize(file.size)})`);
            
            // Step 1: Initialize the multipart upload
            const initResult = await this.initializeMultipartUpload(file);
            
            if (!initResult.success) {
                throw new Error(`Failed to initialize multipart upload: ${initResult.error}`);
            }
            
            const { s3_key, upload_id } = initResult;
            
            // Step 2: Split the file into parts
            const parts = this.splitFileIntoParts(file);
            console.log(`Split file into ${parts.length} parts`);
            
            // Step 3: Get presigned URLs for each part
            const urlsResult = await this.getPartUploadUrls(s3_key, upload_id, parts.length);
            
            if (!urlsResult.success) {
                throw new Error(`Failed to get part upload URLs: ${urlsResult.error}`);
            }
            
            // Step 4: Upload parts in parallel
            const uploadedParts = await this.uploadParts(file, parts, urlsResult.presigned_urls);
            
            if (this.aborted) {
                console.log('Upload was aborted, cleaning up...');
                await this.abortMultipartUpload(s3_key, upload_id);
                return;
            }
            
            // Step 5: Complete the multipart upload
            const completeResult = await this.completeMultipartUpload(s3_key, upload_id, uploadedParts);
            
            if (!completeResult.success) {
                throw new Error(`Failed to complete multipart upload: ${completeResult.error}`);
            }
            
            console.log(`Multipart upload completed for ${file.name}`);
            this.onComplete({
                success: true,
                fileName: file.name,
                s3Key: s3_key,
                size: file.size,
                formattedSize: this.formatSize(file.size),
                result: completeResult
            });
            
        } catch (error) {
            console.error('Multipart upload failed:', error);
            this.onError({
                success: false,
                error: error.message,
                fileName: file ? file.name : 'unknown'
            });
        }
    }
    
    /**
     * Initialize a multipart upload with the server
     * 
     * @param {File} file - The file to upload
     * @returns {Promise<Object>} - The initialization result
     */
    async initializeMultipartUpload(file) {
        const data = {
            file_name: file.name,
            file_type: file.type || 'application/octet-stream',
            path_prefix: this.pathPrefix
        };
        
        const response = await fetch('/storage/multipart/initialize/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.csrfToken
            },
            body: JSON.stringify(data)
        });
        
        return await response.json();
    }
    
    /**
     * Get presigned URLs for uploading parts
     * 
     * @param {string} s3Key - The S3 key for the file
     * @param {string} uploadId - The multipart upload ID
     * @param {number} partCount - Number of parts to get URLs for
     * @returns {Promise<Object>} - The presigned URLs result
     */
    async getPartUploadUrls(s3Key, uploadId, partCount) {
        const data = {
            s3_key: s3Key,
            upload_id: uploadId,
            part_count: partCount
        };
        
        const response = await fetch('/storage/multipart/get-part-urls/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.csrfToken
            },
            body: JSON.stringify(data)
        });
        
        return await response.json();
    }
    
    /**
     * Split a file into parts for multipart upload
     * 
     * @param {File} file - The file to split
     * @returns {Array<Object>} - Array of part objects with start and end positions
     */
    splitFileIntoParts(file) {
        const parts = [];
        let start = 0;
        
        while (start < file.size) {
            const end = Math.min(start + this.partSize, file.size);
            parts.push({
                start,
                end,
                partNumber: parts.length + 1
            });
            start = end;
        }
        
        return parts;
    }
    
    /**
     * Upload parts to S3 using presigned URLs
     * 
     * @param {File} file - The file being uploaded
     * @param {Array<Object>} parts - The parts to upload
     * @param {Array<Object>} presignedUrls - The presigned URLs for each part
     * @returns {Promise<Array<Object>>} - Array of uploaded parts with ETags
     */
    async uploadParts(file, parts, presignedUrls) {
        const uploadQueue = [...parts];
        const uploadedParts = [];
        const workers = [];
        let totalUploaded = 0;
        
        // Create a promise that resolves when all parts are uploaded
        const allPartsPromise = new Promise((resolve, reject) => {
            // Function to process the upload queue
            const processQueue = async () => {
                if (this.aborted) {
                    return;
                }
                
                if (uploadQueue.length === 0) {
                    // If there are still active uploads, wait for them to complete
                    if (this.activeUploads === 0) {
                        resolve(uploadedParts);
                    }
                    return;
                }
                
                if (this.activeUploads < this.maxConcurrentUploads) {
                    const part = uploadQueue.shift();
                    this.activeUploads++;
                    
                    // Find the matching presigned URL
                    const presignedUrl = presignedUrls.find(url => url.part_number === part.partNumber);
                    
                    if (!presignedUrl) {
                        reject(new Error(`No presigned URL found for part ${part.partNumber}`));
                        return;
                    }
                    
                    try {
                        // Upload the part
                        const result = await this.uploadPart(file, part, presignedUrl.url);
                        uploadedParts.push({
                            part_number: part.partNumber,
                            etag: result.etag
                        });
                        
                        // Update progress
                        totalUploaded += (part.end - part.start);
                        const progress = Math.round((totalUploaded / file.size) * 100);
                        this.onProgress({
                            fileName: file.name,
                            loaded: totalUploaded,
                            total: file.size,
                            percent: progress
                        });
                        
                    } catch (error) {
                        reject(error);
                        return;
                    } finally {
                        this.activeUploads--;
                        // Process the next item in the queue
                        processQueue();
                    }
                }
                
                // Schedule the next check
                if (uploadQueue.length > 0) {
                    setTimeout(processQueue, 100);
                }
            };
            
            // Start the queue processing with multiple workers
            for (let i = 0; i < this.maxConcurrentUploads; i++) {
                workers.push(processQueue());
            }
        });
        
        return allPartsPromise;
    }
    
    /**
     * Upload a single part to S3
     * 
     * @param {File} file - The file being uploaded
     * @param {Object} part - The part to upload
     * @param {string} presignedUrl - The presigned URL for this part
     * @returns {Promise<Object>} - Upload result with ETag
     */
    async uploadPart(file, part, presignedUrl) {
        // Extract the part data from the file
        const blob = file.slice(part.start, part.end);
        
        // Upload the part using the presigned URL
        const response = await fetch(presignedUrl, {
            method: 'PUT',
            body: blob
        });
        
        if (!response.ok) {
            throw new Error(`Failed to upload part ${part.partNumber}: ${response.statusText}`);
        }
        
        // Get the ETag from the response headers
        const etag = response.headers.get('ETag');
        
        if (!etag) {
            throw new Error(`No ETag returned for part ${part.partNumber}`);
        }
        
        return {
            partNumber: part.partNumber,
            etag: etag
        };
    }
    
    /**
     * Complete a multipart upload
     * 
     * @param {string} s3Key - The S3 key for the file
     * @param {string} uploadId - The multipart upload ID
     * @param {Array<Object>} parts - The uploaded parts with ETags
     * @returns {Promise<Object>} - The completion result
     */
    async completeMultipartUpload(s3Key, uploadId, parts) {
        const data = {
            s3_key: s3Key,
            upload_id: uploadId,
            parts: parts
        };
        
        const response = await fetch('/storage/multipart/complete/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.csrfToken
            },
            body: JSON.stringify(data)
        });
        
        return await response.json();
    }
    
    /**
     * Abort a multipart upload
     * 
     * @param {string} s3Key - The S3 key for the file
     * @param {string} uploadId - The multipart upload ID
     * @returns {Promise<Object>} - The abort result
     */
    async abortMultipartUpload(s3Key, uploadId) {
        const data = {
            s3_key: s3Key,
            upload_id: uploadId
        };
        
        const response = await fetch('/storage/multipart/abort/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.csrfToken
            },
            body: JSON.stringify(data)
        });
        
        return await response.json();
    }
    
    /**
     * Abort the current upload
     */
    abort() {
        this.aborted = true;
    }
    
    /**
     * Format a file size in bytes to a human-readable string
     * 
     * @param {number} bytes - The size in bytes
     * @returns {string} - Formatted size string
     */
    formatSize(bytes) {
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        let size = bytes;
        let unitIndex = 0;
        
        while (size >= 1024 && unitIndex < units.length - 1) {
            size /= 1024;
            unitIndex++;
        }
        
        return unitIndex === 0
            ? `${size} ${units[unitIndex]}`
            : `${size.toFixed(2)} ${units[unitIndex]}`;
    }
}

/**
 * Example usage:
 * 
 * const uploadClient = new MultipartUploadClient({
 *     csrfToken: document.querySelector('[name=csrfmiddlewaretoken]').value,
 *     pathPrefix: 'uploads/user123',
 *     onProgress: (progress) => {
 *         console.log(`Upload progress: ${progress.percent}%`);
 *     },
 *     onComplete: (result) => {
 *         console.log('Upload complete:', result);
 *     },
 *     onError: (error) => {
 *         console.error('Upload error:', error);
 *     }
 * });
 * 
 * // Upload a file
 * uploadClient.uploadFile(fileInput.files[0]);
 */ 