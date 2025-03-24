/**
 * Base S3 Client
 * Handles core S3/MinIO operations and authentication
 */
class S3Client {
    constructor() {
        this.csrfToken = this.getCsrfToken();
    }

    getCsrfToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]').value;
    }

    async initializeMultipartUpload(fileName, folderName, fileType = 'application/octet-stream') {
        try {
            const response = await fetch('/storage/multipart/initialize/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                },
                body: JSON.stringify({
                    file_name: fileName,
                    file_type: fileType,
                    path_prefix: folderName
                })
            });

            if (!response.ok) {
                throw new Error('Failed to initialize multipart upload');
            }

            const data = await response.json();
            if (!data.success) {
                console.error('Failed to initialize multipart upload:', data.error);
                return { success: false, error: data.error };
            }

            return { success: true, uploadId: data.upload_id, s3Key: data.s3_key };
        } catch (error) {
            console.error('Error initializing multipart upload:', error);
            return { success: false, error: error.message };
        }
    }

    async getPartUploadUrls(s3Key, uploadId, partCount, expiration = 3600) {
        try {
            // Validate required parameters
            if (!s3Key || !uploadId || !partCount) {
                const error = new Error('Missing required parameters');
                error.details = {
                    s3Key: !s3Key,
                    uploadId: !uploadId,
                    partCount: !partCount
                };
                throw error;
            }

            console.log('Getting part upload URLs with:', {
                s3Key,
                uploadId,
                partCount,
                expiration
            });

            const requestBody = {
                s3_key: s3Key,
                upload_id: uploadId,
                part_count: partCount,
                expiration: expiration
            };

            console.log('Request body:', requestBody);

            const response = await fetch('/storage/multipart/get-part-urls/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                },
                body: JSON.stringify(requestBody)
            });

            if (!response.ok) {
                console.error('Failed to get part upload URLs:', {
                    status: response.status,
                    statusText: response.statusText
                });
                throw new Error(`Failed to get part upload URLs: ${response.status}`);
            }

            const data = await response.json();
            console.log('Part upload URLs response:', {
                success: data.success,
                urlsType: typeof data.presigned_urls,
                urlsIsArray: Array.isArray(data.presigned_urls),
                urlsLength: data.presigned_urls?.length,
                firstUrl: data.presigned_urls?.[0]
            });

            if (!data.success) {
                console.error('Failed to get part upload URLs:', data.error);
                return { success: false, error: data.error };
            }

            // Ensure we have an array of URLs
            if (!Array.isArray(data.presigned_urls)) {
                console.error('Invalid presigned URLs format:', data.presigned_urls);
                return { success: false, error: 'Invalid presigned URLs format' };
            }

            return { success: true, urls: data.presigned_urls };
        } catch (error) {
            console.error('Error getting part upload URLs:', error);
            return { 
                success: false, 
                error: error.message,
                details: error.details
            };
        }
    }

    async completeMultipartUpload(s3Key, uploadId, parts) {
        try {
            // Validate required parameters
            if (!s3Key || !uploadId || !parts || !Array.isArray(parts) || parts.length === 0) {
                const error = new Error('S3 key, upload ID, and parts are required');
                error.details = {
                    s3Key: !s3Key,
                    uploadId: !uploadId,
                    parts: !parts || !Array.isArray(parts) || parts.length === 0
                };
                throw error;
            }

            console.log('Completing multipart upload with:', {
                s3Key,
                uploadId,
                parts
            });

            const response = await fetch('/storage/multipart/complete/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                },
                body: JSON.stringify({
                    s3_key: s3Key,
                    upload_id: uploadId,
                    parts: parts
                })
            });

            if (!response.ok) {
                throw new Error('Failed to complete multipart upload');
            }

            const data = await response.json();
            if (!data.success) {
                console.error('Failed to complete multipart upload:', data.error);
                return { success: false, error: data.error };
            }

            return { success: true };
        } catch (error) {
            console.error('Error completing multipart upload:', error);
            return { success: false, error: error.message };
        }
    }

    async abortMultipartUpload(fileName, uploadId, folderName) {
        try {
            const response = await fetch('/storage/multipart/abort/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                },
                body: JSON.stringify({
                    file_name: fileName,
                    upload_id: uploadId,
                    path_prefix: folderName
                })
            });

            if (!response.ok) {
                throw new Error('Failed to abort multipart upload');
            }

            const data = await response.json();
            if (!data.success) {
                console.error('Failed to abort multipart upload:', data.error);
                return { success: false, error: data.error };
            }

            return { success: true };
        } catch (error) {
            console.error('Error aborting multipart upload:', error);
            return { success: false, error: error.message };
        }
    }
}

// Export for testing
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { S3Client };
} else {
    // Make globally available for browser
    window.S3Client = S3Client;
} 