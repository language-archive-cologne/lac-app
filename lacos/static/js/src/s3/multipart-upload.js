/**
 * Multipart Upload Handler
 * Manages the multipart upload process for large files
 */
class MultipartUploadHandler {
    constructor(s3Client) {
        if (!s3Client) {
            throw new Error('S3Client is required');
        }
        this.s3Client = s3Client;
        this.activeUploads = new Map();
    }

    async startUpload(file, folderName) {
        try {
            // Initialize multipart upload
            const initResult = await this.s3Client.initializeMultipartUpload(file.name, folderName);
            if (!initResult.success) {
                console.error('Failed to initialize multipart upload:', initResult.error);
                return { success: false, error: initResult.error };
            }

            console.log('Multipart upload initialized:', {
                fileName: file.name,
                uploadId: initResult.uploadId,
                s3Key: initResult.s3Key
            });

            // Calculate number of parts based on file size
            const partSize = 5 * 1024 * 1024; // 5MB per part
            const partCount = Math.ceil(file.size / partSize);

            console.log('Calculated parts:', {
                fileSize: file.size,
                partSize: partSize,
                partCount: partCount
            });

            // Get presigned URLs for parts
            const urlsResult = await this.s3Client.getPartUploadUrls(
                initResult.s3Key,
                initResult.uploadId,
                partCount
            );
            if (!urlsResult.success) {
                console.error('Failed to get presigned URLs:', urlsResult.error);
                return { success: false, error: urlsResult.error };
            }

            console.log('Got presigned URLs:', {
                urlsCount: urlsResult.urls.length,
                firstUrl: urlsResult.urls[0] // Log first URL for debugging
            });

            // Store upload info
            this.activeUploads.set(file.name, {
                uploadId: initResult.uploadId,
                s3Key: initResult.s3Key,
                presignedUrls: urlsResult.urls,
                parts: [],
                folderName: folderName,
                partSize: partSize
            });

            return { success: true };
        } catch (error) {
            console.error('Error starting upload:', error);
            return { success: false, error: error.message };
        }
    }

    async uploadPart(file, partNumber) {
        try {
            const upload = this.activeUploads.get(file.name);
            if (!upload) {
                console.error('No active upload found for file:', file.name);
                return { success: false, error: 'No active upload found' };
            }

            const presignedUrlData = upload.presignedUrls[partNumber - 1];
            if (!presignedUrlData) {
                console.error('No presigned URL available for part:', partNumber);
                return { success: false, error: 'No presigned URL available' };
            }

            // Handle the presigned URL object format
            if (typeof presignedUrlData === 'object' && presignedUrlData.url) {
                console.log('Using presigned URL from object:', presignedUrlData);
            } else if (typeof presignedUrlData === 'string') {
                console.log('Using presigned URL string:', presignedUrlData);
            } else {
                console.error('Invalid presigned URL format:', presignedUrlData);
                return { success: false, error: 'Invalid presigned URL format' };
            }

            const presignedUrl = typeof presignedUrlData === 'object' ? presignedUrlData.url : presignedUrlData;

            console.log('Uploading part:', {
                partNumber,
                presignedUrl,
                fileSize: file.size,
                partSize: upload.partSize
            });

            const start = (partNumber - 1) * upload.partSize;
            const end = Math.min(start + upload.partSize, file.size);
            const chunk = file.slice(start, end);

            console.log('Chunk details:', {
                start,
                end,
                chunkSize: chunk.size
            });

            const response = await fetch(presignedUrl, {
                method: 'PUT',
                body: chunk,
                headers: {
                    'Content-Type': file.type
                }
            });

            if (!response.ok) {
                console.error('Upload part failed:', {
                    status: response.status,
                    statusText: response.statusText,
                    url: presignedUrl
                });
                throw new Error(`Failed to upload part ${partNumber}: ${response.statusText}`);
            }

            const etag = response.headers.get('ETag');
            upload.parts.push({ part_number: partNumber, etag: etag });

            console.log('Part uploaded successfully:', {
                partNumber,
                etag
            });

            return { success: true, etag };
        } catch (error) {
            console.error('Error uploading part:', error);
            return { success: false, error: error.message };
        }
    }

    async completeUpload(fileName) {
        try {
            const upload = this.activeUploads.get(fileName);
            if (!upload) {
                console.error('No active upload found for file:', fileName);
                return { success: false, error: 'No active upload found' };
            }

            console.log('Completing upload with:', {
                s3Key: upload.s3Key,
                uploadId: upload.uploadId,
                parts: upload.parts
            });

            const result = await this.s3Client.completeMultipartUpload(
                upload.s3Key,
                upload.uploadId,
                upload.parts
            );

            if (!result.success) {
                console.error('Failed to complete multipart upload:', result.error);
                return { success: false, error: result.error };
            }

            // Clean up the upload from active uploads
            this.activeUploads.delete(fileName);

            return { success: true };
        } catch (error) {
            console.error('Error completing upload:', error);
            return { success: false, error: error.message };
        }
    }

    async abortUpload(fileName) {
        try {
            const upload = this.activeUploads.get(fileName);
            if (!upload) {
                console.error('No active upload found for file:', fileName);
                return { success: false, error: 'No active upload found' };
            }

            const result = await this.s3Client.abortMultipartUpload(
                upload.s3Key,
                upload.uploadId
            );

            if (!result.success) {
                console.error('Failed to abort multipart upload:', result.error);
                return { success: false, error: result.error };
            }

            // Clean up
            this.activeUploads.delete(fileName);
            return { success: true };
        } catch (error) {
            console.error('Error aborting upload:', error);
            return { success: false, error: error.message };
        }
    }
}

// Export for testing
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { MultipartUploadHandler };
} else {
    // Make globally available for browser
    window.MultipartUploadHandler = MultipartUploadHandler;
} 