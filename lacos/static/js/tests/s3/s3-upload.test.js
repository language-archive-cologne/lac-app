// Import the classes we're testing
const { S3Client } = require('@src/s3/s3-client');
const { MultipartUploadHandler } = require('@src/s3/multipart-upload');

// Mock fetch
const mockFetch = jest.fn();
global.fetch = mockFetch;

// Mock console.error to suppress expected error messages
const mockConsoleError = jest.spyOn(console, 'error').mockImplementation(() => {});

describe('S3Client', () => {
    let s3Client;

    beforeEach(() => {
        s3Client = new S3Client();
        mockFetch.mockClear();
        mockConsoleError.mockClear();
    });

    afterEach(() => {
        mockConsoleError.mockRestore();
    });

    test('initializeMultipartUpload', async () => {
        const mockResponse = {
            success: true,
            upload_id: 'test-upload-id',
            s3_key: 'test-key'
        };
        mockFetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve(mockResponse)
        });

        const result = await s3Client.initializeMultipartUpload('test.txt', 'text/plain', 'test/');
        expect(result).toEqual(mockResponse);
        expect(mockFetch).toHaveBeenCalledWith(
            '/storage/initialize-multipart-upload/',
            expect.objectContaining({
                method: 'POST',
                headers: expect.objectContaining({
                    'Content-Type': 'application/json',
                    'X-CSRFToken': expect.any(String)
                }),
                body: expect.any(String)
            })
        );
    });

    test('initializeMultipartUpload handles network error', async () => {
        mockFetch.mockRejectedValueOnce(new Error('Network error'));
        
        await expect(s3Client.initializeMultipartUpload('test.txt', 'text/plain', 'test/'))
            .rejects
            .toThrow('Network error');
    });

    test('initializeMultipartUpload handles server error', async () => {
        mockFetch.mockResolvedValueOnce({
            ok: false,
            status: 500,
            statusText: 'Internal Server Error'
        });

        await expect(s3Client.initializeMultipartUpload('test.txt', 'text/plain', 'test/'))
            .rejects
            .toThrow('Failed to initialize multipart upload');
    });

    test('getPartUploadUrls', async () => {
        const mockResponse = {
            success: true,
            presigned_urls: [
                { url: 'url1', part_number: 1 },
                { url: 'url2', part_number: 2 }
            ]
        };
        mockFetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve(mockResponse)
        });

        const result = await s3Client.getPartUploadUrls('test-key', 'test-upload-id', 2);
        expect(result).toEqual(mockResponse);
        expect(mockFetch).toHaveBeenCalledWith(
            '/storage/get-part-upload-urls/',
            expect.objectContaining({
                method: 'POST',
                headers: expect.objectContaining({
                    'Content-Type': 'application/json',
                    'X-CSRFToken': expect.any(String)
                }),
                body: expect.any(String)
            })
        );
    });

    test('getPartUploadUrls handles invalid response', async () => {
        mockFetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve({ success: false })
        });

        await expect(s3Client.getPartUploadUrls('test-key', 'test-upload-id', 2))
            .rejects
            .toThrow('Failed to get part upload URLs');
    });

    test('completeMultipartUpload', async () => {
        const mockResponse = {
            success: true,
            message: 'Upload completed successfully'
        };
        mockFetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve(mockResponse)
        });

        const result = await s3Client.completeMultipartUpload('test-key', 'test-upload-id', [
            { ETag: 'etag1', PartNumber: 1 },
            { ETag: 'etag2', PartNumber: 2 }
        ]);

        expect(result).toEqual(mockResponse);
        expect(mockFetch).toHaveBeenCalledWith(
            '/storage/complete-multipart-upload/',
            expect.objectContaining({
                method: 'POST',
                headers: expect.objectContaining({
                    'Content-Type': 'application/json',
                    'X-CSRFToken': expect.any(String)
                }),
                body: expect.any(String)
            })
        );
    });

    test('abortMultipartUpload', async () => {
        const mockResponse = {
            success: true,
            message: 'Upload aborted successfully'
        };
        mockFetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve(mockResponse)
        });

        const result = await s3Client.abortMultipartUpload('test-key', 'test-upload-id');
        expect(result).toEqual(mockResponse);
        expect(mockFetch).toHaveBeenCalledWith(
            '/storage/abort-multipart-upload/',
            expect.objectContaining({
                method: 'POST',
                headers: expect.objectContaining({
                    'Content-Type': 'application/json',
                    'X-CSRFToken': expect.any(String)
                }),
                body: expect.any(String)
            })
        );
    });
});

describe('MultipartUploadHandler', () => {
    let handler;
    let mockS3Client;

    beforeEach(() => {
        mockS3Client = {
            initializeMultipartUpload: jest.fn(),
            getPartUploadUrls: jest.fn(),
            completeMultipartUpload: jest.fn(),
            abortMultipartUpload: jest.fn()
        };
        handler = new MultipartUploadHandler(mockS3Client);
        mockConsoleError.mockClear();
    });

    afterEach(() => {
        mockConsoleError.mockRestore();
    });

    test('startUpload', async () => {
        const mockFile = new File(['test'], 'test.txt', { type: 'text/plain' });
        const mockInitResponse = {
            success: true,
            upload_id: 'test-upload-id',
            s3_key: 'test-key'
        };
        const mockUrlsResponse = {
            success: true,
            presigned_urls: [
                { url: 'url1', part_number: 1 },
                { url: 'url2', part_number: 2 }
            ]
        };

        mockS3Client.initializeMultipartUpload.mockResolvedValueOnce(mockInitResponse);
        mockS3Client.getPartUploadUrls.mockResolvedValueOnce(mockUrlsResponse);

        const result = await handler.startUpload(mockFile, 'test/');
        expect(result.success).toBe(true);
        expect(result.uploadId).toBe('test-upload-id');
        expect(result.s3Key).toBe('test-key');
    });

    test('startUpload handles initialization failure', async () => {
        const mockFile = new File(['test'], 'test.txt', { type: 'text/plain' });
        mockS3Client.initializeMultipartUpload.mockRejectedValueOnce(new Error('Init failed'));

        const result = await handler.startUpload(mockFile, 'test/');
        expect(result.success).toBe(false);
        expect(result.error).toBe('Init failed');
    });

    test('startUpload handles URL retrieval failure', async () => {
        const mockFile = new File(['test'], 'test.txt', { type: 'text/plain' });
        const mockInitResponse = {
            success: true,
            upload_id: 'test-upload-id',
            s3_key: 'test-key'
        };

        mockS3Client.initializeMultipartUpload.mockResolvedValueOnce(mockInitResponse);
        mockS3Client.getPartUploadUrls.mockRejectedValueOnce(new Error('URL retrieval failed'));

        const result = await handler.startUpload(mockFile, 'test/');
        expect(result.success).toBe(false);
        expect(result.error).toBe('URL retrieval failed');
    });

    test('uploadPart', async () => {
        const mockFile = new File(['test'], 'test.txt', { type: 'text/plain' });
        mockFetch.mockResolvedValueOnce({
            ok: true,
            headers: new Headers({ 'ETag': 'test-etag' })
        });

        // First set up an active upload
        const mockInitResponse = {
            success: true,
            upload_id: 'test-upload-id',
            s3_key: 'test-key'
        };
        const mockUrlsResponse = {
            success: true,
            presigned_urls: [
                { url: 'url1', part_number: 1 }
            ]
        };

        mockS3Client.initializeMultipartUpload.mockResolvedValueOnce(mockInitResponse);
        mockS3Client.getPartUploadUrls.mockResolvedValueOnce(mockUrlsResponse);

        await handler.startUpload(mockFile, 'test/');

        const result = await handler.uploadPart('test.txt', 1);
        expect(result.success).toBe(true);
        expect(result.etag).toBe('test-etag');
    });

    test('uploadPart handles upload failure', async () => {
        const mockFile = new File(['test'], 'test.txt', { type: 'text/plain' });
        mockFetch.mockRejectedValueOnce(new Error('Upload failed'));

        // First set up an active upload
        const mockInitResponse = {
            success: true,
            upload_id: 'test-upload-id',
            s3_key: 'test-key'
        };
        const mockUrlsResponse = {
            success: true,
            presigned_urls: [
                { url: 'url1', part_number: 1 }
            ]
        };

        mockS3Client.initializeMultipartUpload.mockResolvedValueOnce(mockInitResponse);
        mockS3Client.getPartUploadUrls.mockResolvedValueOnce(mockUrlsResponse);

        await handler.startUpload(mockFile, 'test/');

        const result = await handler.uploadPart('test.txt', 1);
        expect(result.success).toBe(false);
        expect(result.error).toBe('Upload failed');
    });

    test('completeUpload', async () => {
        const mockFile = new File(['test'], 'test.txt', { type: 'text/plain' });
        
        // Mock fetch for part upload
        mockFetch.mockImplementation((url) => {
            if (url === 'url1') {
                return Promise.resolve({
                    ok: true,
                    headers: new Headers({ 'ETag': 'test-etag' })
                });
            }
            return Promise.resolve({
                ok: true,
                json: () => Promise.resolve({ success: true })
            });
        });

        // Set up an active upload
        const mockInitResponse = {
            success: true,
            upload_id: 'test-upload-id',
            s3_key: 'test-key'
        };
        const mockUrlsResponse = {
            success: true,
            presigned_urls: [
                { url: 'url1', part_number: 1 }
            ]
        };

        mockS3Client.initializeMultipartUpload.mockResolvedValueOnce(mockInitResponse);
        mockS3Client.getPartUploadUrls.mockResolvedValueOnce(mockUrlsResponse);
        mockS3Client.completeMultipartUpload.mockResolvedValueOnce({ success: true });

        await handler.startUpload(mockFile, 'test/');
        await handler.uploadPart('test.txt', 1);

        const result = await handler.completeUpload('test.txt');
        expect(result.success).toBe(true);
    });

    test('completeUpload handles completion failure', async () => {
        const mockFile = new File(['test'], 'test.txt', { type: 'text/plain' });
        
        // Mock fetch for part upload
        mockFetch.mockImplementation((url) => {
            if (url === 'url1') {
                return Promise.resolve({
                    ok: true,
                    headers: new Headers({ 'ETag': 'test-etag' })
                });
            }
            return Promise.resolve({
                ok: true,
                json: () => Promise.resolve({ success: true })
            });
        });

        // Set up an active upload
        const mockInitResponse = {
            success: true,
            upload_id: 'test-upload-id',
            s3_key: 'test-key'
        };
        const mockUrlsResponse = {
            success: true,
            presigned_urls: [
                { url: 'url1', part_number: 1 }
            ]
        };

        mockS3Client.initializeMultipartUpload.mockResolvedValueOnce(mockInitResponse);
        mockS3Client.getPartUploadUrls.mockResolvedValueOnce(mockUrlsResponse);
        mockS3Client.completeMultipartUpload.mockRejectedValueOnce(new Error('Completion failed'));

        await handler.startUpload(mockFile, 'test/');
        await handler.uploadPart('test.txt', 1);

        const result = await handler.completeUpload('test.txt');
        expect(result.success).toBe(false);
        expect(result.error).toBe('Completion failed');
    });

    test('abortUpload', async () => {
        const mockFile = new File(['test'], 'test.txt', { type: 'text/plain' });
        
        // Set up an active upload
        const mockInitResponse = {
            success: true,
            upload_id: 'test-upload-id',
            s3_key: 'test-key'
        };
        const mockUrlsResponse = {
            success: true,
            presigned_urls: [
                { url: 'url1', part_number: 1 }
            ]
        };

        mockS3Client.initializeMultipartUpload.mockResolvedValueOnce(mockInitResponse);
        mockS3Client.getPartUploadUrls.mockResolvedValueOnce(mockUrlsResponse);
        mockS3Client.abortMultipartUpload.mockResolvedValueOnce({ success: true });

        await handler.startUpload(mockFile, 'test/');

        const result = await handler.abortUpload('test.txt');
        expect(result.success).toBe(true);
    });

    test('abortUpload handles abort failure', async () => {
        const mockFile = new File(['test'], 'test.txt', { type: 'text/plain' });
        
        // Set up an active upload
        const mockInitResponse = {
            success: true,
            upload_id: 'test-upload-id',
            s3_key: 'test-key'
        };
        const mockUrlsResponse = {
            success: true,
            presigned_urls: [
                { url: 'url1', part_number: 1 }
            ]
        };

        mockS3Client.initializeMultipartUpload.mockResolvedValueOnce(mockInitResponse);
        mockS3Client.getPartUploadUrls.mockResolvedValueOnce(mockUrlsResponse);
        mockS3Client.abortMultipartUpload.mockRejectedValueOnce(new Error('Abort failed'));

        await handler.startUpload(mockFile, 'test/');

        const result = await handler.abortUpload('test.txt');
        expect(result.success).toBe(false);
        expect(result.error).toBe('Abort failed');
    });

    test('handles concurrent uploads correctly', async () => {
        const mockFile1 = new File(['test1'], 'test1.txt', { type: 'text/plain' });
        const mockFile2 = new File(['test2'], 'test2.txt', { type: 'text/plain' });

        // Set up responses for first file
        const mockInitResponse1 = {
            success: true,
            upload_id: 'test-upload-id-1',
            s3_key: 'test-key-1'
        };
        const mockUrlsResponse1 = {
            success: true,
            presigned_urls: [{ url: 'url1', part_number: 1 }]
        };

        // Set up responses for second file
        const mockInitResponse2 = {
            success: true,
            upload_id: 'test-upload-id-2',
            s3_key: 'test-key-2'
        };
        const mockUrlsResponse2 = {
            success: true,
            presigned_urls: [{ url: 'url2', part_number: 1 }]
        };

        mockS3Client.initializeMultipartUpload
            .mockResolvedValueOnce(mockInitResponse1)
            .mockResolvedValueOnce(mockInitResponse2);
        mockS3Client.getPartUploadUrls
            .mockResolvedValueOnce(mockUrlsResponse1)
            .mockResolvedValueOnce(mockUrlsResponse2);

        // Start both uploads
        const result1 = await handler.startUpload(mockFile1, 'test/');
        const result2 = await handler.startUpload(mockFile2, 'test/');

        expect(result1.success).toBe(true);
        expect(result2.success).toBe(true);
        expect(result1.uploadId).not.toBe(result2.uploadId);
    });
}); 