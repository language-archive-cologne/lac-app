const { S3Client } = require('@src/s3/s3-client');
const { MultipartUploadHandler } = require('@src/s3/multipart-upload');

const mockFetch = jest.fn();
global.fetch = mockFetch;

const mockConsoleError = jest.spyOn(console, 'error').mockImplementation(() => {});

describe('S3Client', () => {
    let s3Client;

    beforeEach(() => {
        document.body.innerHTML = '<input type="hidden" name="csrfmiddlewaretoken" value="test-csrf-token">';
        s3Client = new S3Client();
        mockFetch.mockReset();
        mockConsoleError.mockClear();
    });

    afterAll(() => {
        mockConsoleError.mockRestore();
    });

    test('initializeMultipartUpload uses the current multipart endpoint', async () => {
        mockFetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve({
                success: true,
                upload_id: 'test-upload-id',
            }),
        });

        const result = await s3Client.initializeMultipartUpload('test.txt', 'test', 'text/plain');

        expect(result).toEqual({
            success: true,
            uploadId: 'test-upload-id',
            s3Key: 'test/test.txt',
        });
        expect(mockFetch).toHaveBeenCalledWith(
            '/storage/multipart/initialize/',
            expect.objectContaining({
                method: 'POST',
                headers: expect.objectContaining({
                    'Content-Type': 'application/json',
                    'X-CSRFToken': 'test-csrf-token',
                }),
                body: JSON.stringify({
                    file_name: 'test.txt',
                    file_type: 'text/plain',
                    path_prefix: 'test',
                }),
            }),
        );
    });

    test('initializeMultipartUpload returns an error object on network failure', async () => {
        mockFetch.mockRejectedValueOnce(new Error('Network error'));

        const result = await s3Client.initializeMultipartUpload('test.txt', 'test');

        expect(result).toEqual({
            success: false,
            error: 'Network error',
        });
    });

    test('getPartUploadUrls uses the current multipart part-url endpoint', async () => {
        mockFetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve({
                success: true,
                presigned_urls: [
                    { url: 'url1', part_number: 1 },
                    { url: 'url2', part_number: 2 },
                ],
            }),
        });

        const result = await s3Client.getPartUploadUrls('test-key', 'test-upload-id', 2);

        expect(result).toEqual({
            success: true,
            urls: [
                { url: 'url1', part_number: 1 },
                { url: 'url2', part_number: 2 },
            ],
        });
        expect(mockFetch).toHaveBeenCalledWith(
            '/storage/multipart/get-part-urls/',
            expect.objectContaining({
                method: 'POST',
                headers: expect.objectContaining({
                    'Content-Type': 'application/json',
                    'X-CSRFToken': 'test-csrf-token',
                }),
                body: JSON.stringify({
                    s3_key: 'test-key',
                    upload_id: 'test-upload-id',
                    part_count: 2,
                    expiration: 3600,
                }),
            }),
        );
    });

    test('completeMultipartUpload uses the current completion endpoint', async () => {
        mockFetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve({ success: true }),
        });

        const result = await s3Client.completeMultipartUpload('test-key', 'test-upload-id', [
            { part_number: 1, etag: 'etag1' },
            { part_number: 2, etag: 'etag2' },
        ]);

        expect(result).toEqual({ success: true });
        expect(mockFetch).toHaveBeenCalledWith(
            '/storage/multipart/complete/',
            expect.objectContaining({
                method: 'POST',
                headers: expect.objectContaining({
                    'Content-Type': 'application/json',
                    'X-CSRFToken': 'test-csrf-token',
                }),
                body: JSON.stringify({
                    s3_key: 'test-key',
                    upload_id: 'test-upload-id',
                    parts: [
                        { part_number: 1, etag: 'etag1' },
                        { part_number: 2, etag: 'etag2' },
                    ],
                }),
            }),
        );
    });

    test('abortMultipartUpload uses the current abort endpoint', async () => {
        mockFetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve({ success: true }),
        });

        const result = await s3Client.abortMultipartUpload('test.txt', 'test-upload-id', 'test');

        expect(result).toEqual({ success: true });
        expect(mockFetch).toHaveBeenCalledWith(
            '/storage/multipart/abort/',
            expect.objectContaining({
                method: 'POST',
                headers: expect.objectContaining({
                    'Content-Type': 'application/json',
                    'X-CSRFToken': 'test-csrf-token',
                }),
                body: JSON.stringify({
                    file_name: 'test.txt',
                    upload_id: 'test-upload-id',
                    path_prefix: 'test',
                }),
            }),
        );
    });
});

describe('MultipartUploadHandler', () => {
    let handler;
    let mockS3Client;

    beforeEach(() => {
        mockFetch.mockReset();
        mockConsoleError.mockClear();
        mockS3Client = {
            initializeMultipartUpload: jest.fn(),
            getPartUploadUrls: jest.fn(),
            completeMultipartUpload: jest.fn(),
            abortMultipartUpload: jest.fn(),
        };
        handler = new MultipartUploadHandler(mockS3Client);
    });

    afterAll(() => {
        mockConsoleError.mockRestore();
    });

    test('startUpload stores the current multipart state', async () => {
        const mockFile = new File(['test'], 'test.txt', { type: 'text/plain' });

        mockS3Client.initializeMultipartUpload.mockResolvedValueOnce({
            success: true,
            uploadId: 'test-upload-id',
            s3Key: 'test/test.txt',
        });
        mockS3Client.getPartUploadUrls.mockResolvedValueOnce({
            success: true,
            urls: [{ url: 'url1', part_number: 1 }],
        });

        const result = await handler.startUpload(mockFile, 'test');

        expect(result).toEqual({ success: true });
        expect(mockS3Client.initializeMultipartUpload).toHaveBeenCalledWith('test.txt', 'test');
        expect(handler.activeUploads.get('test.txt')).toEqual(
            expect.objectContaining({
                uploadId: 'test-upload-id',
                s3Key: 'test/test.txt',
                presignedUrls: [{ url: 'url1', part_number: 1 }],
            }),
        );
    });

    test('startUpload trims the selected folder from webkitRelativePath', async () => {
        const mockFile = new File(['test'], 'test.txt', { type: 'text/plain' });
        mockFile.webkitRelativePath = 'folder/sub/test.txt';

        mockS3Client.initializeMultipartUpload.mockResolvedValueOnce({
            success: true,
            uploadId: 'test-upload-id',
            s3Key: 'folder/sub/test.txt',
        });
        mockS3Client.getPartUploadUrls.mockResolvedValueOnce({
            success: true,
            urls: [{ url: 'url1', part_number: 1 }],
        });

        await handler.startUpload(mockFile, 'folder');

        expect(mockS3Client.initializeMultipartUpload).toHaveBeenCalledWith('sub/test.txt', 'folder');
    });

    test('startUpload returns an error when multipart initialization fails', async () => {
        const mockFile = new File(['test'], 'test.txt', { type: 'text/plain' });
        mockS3Client.initializeMultipartUpload.mockResolvedValueOnce({
            success: false,
            error: 'Init failed',
        });

        const result = await handler.startUpload(mockFile, 'test');

        expect(result).toEqual({
            success: false,
            error: 'Init failed',
        });
    });

    test('uploadPart uploads the requested chunk and stores its etag', async () => {
        const mockFile = new File(['test'], 'test.txt', { type: 'text/plain' });
        mockFetch.mockResolvedValueOnce({
            ok: true,
            headers: new Headers({ ETag: 'test-etag' }),
        });
        mockS3Client.initializeMultipartUpload.mockResolvedValueOnce({
            success: true,
            uploadId: 'test-upload-id',
            s3Key: 'test/test.txt',
        });
        mockS3Client.getPartUploadUrls.mockResolvedValueOnce({
            success: true,
            urls: [{ url: 'url1', part_number: 1 }],
        });

        await handler.startUpload(mockFile, 'test');
        const result = await handler.uploadPart(mockFile, 1);

        expect(result).toEqual({
            success: true,
            etag: 'test-etag',
        });
        expect(mockFetch).toHaveBeenCalledWith(
            'url1',
            expect.objectContaining({
                method: 'PUT',
                headers: { 'Content-Type': 'text/plain' },
            }),
        );
        expect(handler.activeUploads.get('test.txt').parts).toEqual([
            { part_number: 1, etag: 'test-etag' },
        ]);
    });

    test('completeUpload delegates to the current client contract', async () => {
        const mockFile = new File(['test'], 'test.txt', { type: 'text/plain' });
        mockFetch.mockResolvedValueOnce({
            ok: true,
            headers: new Headers({ ETag: 'test-etag' }),
        });
        mockS3Client.initializeMultipartUpload.mockResolvedValueOnce({
            success: true,
            uploadId: 'test-upload-id',
            s3Key: 'test/test.txt',
        });
        mockS3Client.getPartUploadUrls.mockResolvedValueOnce({
            success: true,
            urls: [{ url: 'url1', part_number: 1 }],
        });
        mockS3Client.completeMultipartUpload.mockResolvedValueOnce({ success: true });

        await handler.startUpload(mockFile, 'test');
        await handler.uploadPart(mockFile, 1);
        const result = await handler.completeUpload('test.txt');

        expect(result).toEqual({ success: true });
        expect(mockS3Client.completeMultipartUpload).toHaveBeenCalledWith(
            'test/test.txt',
            'test-upload-id',
            [{ part_number: 1, etag: 'test-etag' }],
        );
        expect(handler.activeUploads.has('test.txt')).toBe(false);
    });

    test('abortUpload delegates to the current client contract', async () => {
        const mockFile = new File(['test'], 'test.txt', { type: 'text/plain' });
        mockS3Client.initializeMultipartUpload.mockResolvedValueOnce({
            success: true,
            uploadId: 'test-upload-id',
            s3Key: 'test/test.txt',
        });
        mockS3Client.getPartUploadUrls.mockResolvedValueOnce({
            success: true,
            urls: [{ url: 'url1', part_number: 1 }],
        });
        mockS3Client.abortMultipartUpload.mockResolvedValueOnce({ success: true });

        await handler.startUpload(mockFile, 'test');
        const result = await handler.abortUpload('test.txt');

        expect(result).toEqual({ success: true });
        expect(mockS3Client.abortMultipartUpload).toHaveBeenCalledWith(
            'test/test.txt',
            'test-upload-id',
        );
        expect(handler.activeUploads.has('test.txt')).toBe(false);
    });
});
