/**
 * Tests for folder-scanner.js
 */

import { scanFolder } from '@src/folder-scanner.js';

describe('Folder Scanner', () => {
    // Mock the DOM
    beforeEach(() => {
        // Create a mock folder name input
        const folderNameInput = document.createElement('input');
        folderNameInput.id = 'folder_name';
        folderNameInput.value = 'test_folder';
        document.body.appendChild(folderNameInput);

        // Create a mock CSRF token input
        const csrfInput = document.createElement('input');
        csrfInput.name = 'csrfmiddlewaretoken';
        csrfInput.value = 'test-csrf-token';
        document.body.appendChild(csrfInput);

        // Mock window functions
        window.updateUploadProgress = jest.fn();
        window.updateFolderInfo = jest.fn();
        window.showSuccessMessage = jest.fn();
        window.showErrorMessage = jest.fn();
        window.S3FolderUpload = {
            uploadFiles: jest.fn().mockResolvedValue({
                successful: 1,
                total: 1,
                failed: 0,
                processed_files: ['test.txt']
            })
        };
    });

    afterEach(() => {
        // Clean up the DOM
        document.body.innerHTML = '';
        jest.clearAllMocks();
    });

    // Mock the File System Access API
    const mockFileHandle = {
        kind: 'file',
        name: 'test.txt',
        getFile: jest.fn().mockResolvedValue({
            size: 100,
            type: 'text/plain'
        })
    };

    const mockDirHandle = {
        kind: 'directory',
        name: 'test_folder',
        values: jest.fn().mockImplementation(function* () {
            yield mockFileHandle;
            yield {
                kind: 'directory',
                name: 'subfolder',
                values: jest.fn().mockImplementation(function* () {
                    yield {
                        kind: 'file',
                        name: 'nested.txt',
                        getFile: jest.fn().mockResolvedValue({
                            size: 200,
                            type: 'text/plain'
                        })
                    };
                })
            };
        })
    };

    // Mock the showDirectoryPicker API
    global.showDirectoryPicker = jest.fn().mockResolvedValue(mockDirHandle);

    // Mock the fetch API
    global.fetch = jest.fn();

    test('should correctly traverse a nested folder structure', async () => {
        // Mock the folder structure
        const mockStructure = {
            name: 'test_folder',
            kind: 'directory',
            values: () => {
                return [
                    {
                        name: 'test.txt',
                        kind: 'file',
                        getFile: async () => new File([''], 'test.txt')
                    },
                    {
                        name: 'subfolder',
                        kind: 'directory',
                        values: () => {
                            return [
                                {
                                    name: 'nested.txt',
                                    kind: 'file',
                                    getFile: async () => new File([''], 'nested.txt')
                                }
                            ];
                        }
                    }
                ];
            }
        };

        // Mock showDirectoryPicker
        window.showDirectoryPicker = jest.fn().mockResolvedValue(mockStructure);

        // Mock fetch for presigned URLs
        global.fetch = jest.fn().mockResolvedValue({
            json: () => Promise.resolve({
                success: true,
                presigned_posts: [
                    { file_name: 'test.txt' },
                    { file_name: 'subfolder/nested.txt' }
                ]
            })
        });

        // Mock S3FolderUpload
        window.S3FolderUpload = {
            uploadFiles: jest.fn().mockResolvedValue({
                successful: 2,
                total: 2,
                failed: 0,
                processed_files: ['test.txt', 'subfolder/nested.txt']
            })
        };

        // Mock notifyUploadComplete
        global.notifyUploadComplete = jest.fn().mockResolvedValue({ success: true });

        // Run the scan
        await scanFolder();

        // Get the request body from the fetch call
        const requestBody = JSON.parse(global.fetch.mock.calls[0][1].body);
        
        // Verify folder structure
        expect(requestBody.files_metadata).toHaveLength(2);
        
        // Verify root level file
        expect(requestBody.files_metadata[0]).toEqual({
            file_name: 'test.txt',
            file_type: 'text/plain',
            path: '',
            size: 0
        });
        
        // Verify nested file
        expect(requestBody.files_metadata[1]).toEqual({
            file_name: 'subfolder/nested.txt',
            file_type: 'text/plain',
            path: 'subfolder',
            size: 0
        });
    });

    test('should handle complex folder structure with multiple levels', async () => {
        // Mock the complex structure
        const mockStructure = {
            name: 'root',
            kind: 'directory',
            values: () => {
                return [
                    {
                        name: 'root.txt',
                        kind: 'file',
                        getFile: async () => new File([''], 'root.txt')
                    },
                    {
                        name: 'level1',
                        kind: 'directory',
                        values: () => {
                            return [
                                {
                                    name: 'level1.txt',
                                    kind: 'file',
                                    getFile: async () => new File([''], 'level1.txt')
                                },
                                {
                                    name: 'level2',
                                    kind: 'directory',
                                    values: () => {
                                        return [
                                            {
                                                name: 'level2.txt',
                                                kind: 'file',
                                                getFile: async () => new File([''], 'level2.txt')
                                            }
                                        ];
                                    }
                                }
                            ];
                        }
                    }
                ];
            }
        };

        // Mock showDirectoryPicker
        window.showDirectoryPicker = jest.fn().mockResolvedValue(mockStructure);

        // Mock fetch for presigned URLs
        global.fetch = jest.fn().mockResolvedValue({
            json: () => Promise.resolve({
                success: true,
                presigned_posts: [
                    { file_name: 'root.txt' },
                    { file_name: 'level1/level1.txt' },
                    { file_name: 'level1/level2/level2.txt' }
                ]
            })
        });

        // Mock S3FolderUpload
        window.S3FolderUpload = {
            uploadFiles: jest.fn().mockResolvedValue({
                successful: 3,
                total: 3,
                failed: 0,
                processed_files: ['root.txt', 'level1/level1.txt', 'level1/level2/level2.txt']
            })
        };

        // Mock notifyUploadComplete
        global.notifyUploadComplete = jest.fn().mockResolvedValue({ success: true });

        // Run the scan
        await scanFolder();

        // Get the request body from the fetch call
        const requestBody = JSON.parse(global.fetch.mock.calls[0][1].body);
        
        // Verify the complex structure was handled correctly
        expect(requestBody.files_metadata).toHaveLength(3);
        
        // Verify root level file
        expect(requestBody.files_metadata[0]).toEqual({
            file_name: 'root.txt',
            file_type: 'text/plain',
            path: '',
            size: 0
        });
        
        // Verify first level file
        expect(requestBody.files_metadata[1]).toEqual({
            file_name: 'level1/level1.txt',
            file_type: 'text/plain',
            path: 'level1',
            size: 0
        });
        
        // Verify second level file
        expect(requestBody.files_metadata[2]).toEqual({
            file_name: 'level1/level2/level2.txt',
            file_type: 'text/plain',
            path: 'level1/level2',
            size: 0
        });
    });

    test('should handle empty folders correctly', async () => {
        // Create an empty folder structure
        const emptyHandle = {
            kind: 'directory',
            name: 'empty_folder',
            values: jest.fn().mockImplementation(function* () {
                // No files or folders
            })
        };

        // Mock showDirectoryPicker to return our empty structure
        global.showDirectoryPicker.mockResolvedValueOnce(emptyHandle);

        // Call scanFolder
        await scanFolder();

        // Verify error handling
        expect(global.fetch).not.toHaveBeenCalled();
    });

    test('should handle file type detection correctly', async () => {
        // Mock the folder structure
        const mockStructure = {
            name: 'test_folder',
            kind: 'directory',
            values: () => {
                return [
                    {
                        name: 'test.xml',
                        kind: 'file',
                        getFile: async () => new File([''], 'test.xml')
                    }
                ];
            }
        };

        // Mock showDirectoryPicker
        window.showDirectoryPicker = jest.fn().mockResolvedValue(mockStructure);

        // Mock fetch for presigned URLs
        global.fetch = jest.fn().mockResolvedValue({
            json: () => Promise.resolve({
                success: true,
                presigned_posts: [{ file_name: 'test.xml' }]
            })
        });

        // Mock S3FolderUpload
        window.S3FolderUpload = {
            uploadFiles: jest.fn().mockResolvedValue({
                successful: 1,
                total: 1,
                failed: 0,
                processed_files: ['test.xml']
            })
        };

        // Mock notifyUploadComplete
        global.notifyUploadComplete = jest.fn().mockResolvedValue({ success: true });

        // Run the scan
        await scanFolder();

        // Get the request body from the fetch call
        const requestBody = JSON.parse(global.fetch.mock.calls[0][1].body);
        
        // Verify content type was correctly determined from extension
        expect(requestBody.files_metadata[0].file_type).toBe('application/xml');
    });

    test('should handle API errors gracefully', async () => {
        // Mock API error
        global.fetch.mockRejectedValueOnce(new Error('API Error'));

        // Call scanFolder
        await scanFolder();

        // Verify error handling
        expect(global.fetch).toHaveBeenCalled();
        expect(window.showErrorMessage).toHaveBeenCalledWith({
            message: 'API Error'
        });
    });

    test('should handle deeply nested OCFL-like folders correctly', async () => {
        // Mock the OCFL-like structure
        const mockStructure = {
            name: 'zaghawa',
            kind: 'directory',
            values: () => {
                return [
                    {
                        name: 'zag_eoi_20141009_1',
                        kind: 'directory',
                        values: () => {
                            return [
                                {
                                    name: 'v1',
                                    kind: 'directory',
                                    values: () => {
                                        return [
                                            {
                                                name: 'content',
                                                kind: 'directory',
                                                values: () => {
                                                    return [
                                                        {
                                                            name: 'data',
                                                            kind: 'directory',
                                                            values: () => {
                                                                return [
                                                                    {
                                                                        name: 'ZAG_EOI_20141009_1.eaf',
                                                                        kind: 'file',
                                                                        getFile: async () => new File([''], 'ZAG_EOI_20141009_1.eaf')
                                                                    },
                                                                    {
                                                                        name: 'ZAG_EOI_20141009_1.wav',
                                                                        kind: 'file',
                                                                        getFile: async () => new File([''], 'ZAG_EOI_20141009_1.wav')
                                                                    }
                                                                ];
                                                            }
                                                        },
                                                        {
                                                            name: 'zag_eoi_20141009_1.xml',
                                                            kind: 'file',
                                                            getFile: async () => new File([''], 'zag_eoi_20141009_1.xml')
                                                        }
                                                    ];
                                                }
                                            }
                                        ];
                                    }
                                },
                                {
                                    name: '0=ocfl_object_1.0',
                                    kind: 'file',
                                    getFile: async () => new File([''], '0=ocfl_object_1.0')
                                },
                                {
                                    name: 'acl.json',
                                    kind: 'file',
                                    getFile: async () => new File([''], 'acl.json')
                                }
                            ];
                        }
                    }
                ];
            }
        };

        // Mock showDirectoryPicker
        window.showDirectoryPicker = jest.fn().mockResolvedValue(mockStructure);

        // Mock fetch for presigned URLs
        global.fetch = jest.fn().mockResolvedValue({
            json: () => Promise.resolve({
                success: true,
                presigned_posts: [
                    { file_name: 'zag_eoi_20141009_1/v1/content/data/ZAG_EOI_20141009_1.eaf' },
                    { file_name: 'zag_eoi_20141009_1/v1/content/data/ZAG_EOI_20141009_1.wav' },
                    { file_name: 'zag_eoi_20141009_1/v1/content/zag_eoi_20141009_1.xml' },
                    { file_name: 'zag_eoi_20141009_1/0=ocfl_object_1.0' },
                    { file_name: 'zag_eoi_20141009_1/acl.json' }
                ]
            })
        });

        // Mock S3FolderUpload
        window.S3FolderUpload = {
            uploadFiles: jest.fn().mockResolvedValue({
                successful: 5,
                total: 5,
                failed: 0,
                processed_files: [
                    { file_name: 'zag_eoi_20141009_1/v1/content/data/ZAG_EOI_20141009_1.eaf' },
                    { file_name: 'zag_eoi_20141009_1/v1/content/data/ZAG_EOI_20141009_1.wav' },
                    { file_name: 'zag_eoi_20141009_1/v1/content/zag_eoi_20141009_1.xml' },
                    { file_name: 'zag_eoi_20141009_1/0=ocfl_object_1.0' },
                    { file_name: 'zag_eoi_20141009_1/acl.json' }
                ]
            })
        };

        // Mock notifyUploadComplete
        global.notifyUploadComplete = jest.fn().mockResolvedValue({ success: true });

        // Run the scan
        await scanFolder();

        // Get the request body from the fetch call
        const requestBody = JSON.parse(global.fetch.mock.calls[0][1].body);
        
        // Expected paths
        const expectedPaths = [
            'zag_eoi_20141009_1/v1/content/data/ZAG_EOI_20141009_1.eaf',
            'zag_eoi_20141009_1/v1/content/data/ZAG_EOI_20141009_1.wav',
            'zag_eoi_20141009_1/v1/content/zag_eoi_20141009_1.xml',
            'zag_eoi_20141009_1/0=ocfl_object_1.0',
            'zag_eoi_20141009_1/acl.json'
        ];

        // Verify we have the correct number of files
        expect(requestBody.files_metadata).toHaveLength(expectedPaths.length);

        // Verify each file's path and metadata
        expectedPaths.forEach(expected => {
            const file = requestBody.files_metadata.find(f => f.file_name === expected);
            expect(file).toBeDefined();
            expect(file.file_name).toBe(expected);
        });
    });

    test('should handle OCFL-like folder structure without path duplication', async () => {
        // Mock the OCFL-like structure
        const mockOcflStructure = {
            name: 'zaghawa',
            kind: 'directory',
            values: () => {
                return [
                    {
                        name: 'zag_eoi_20141009_1',
                        kind: 'directory',
                        values: () => {
                            return [
                                {
                                    name: 'v1',
                                    kind: 'directory',
                                    values: () => {
                                        return [
                                            {
                                                name: 'content',
                                                kind: 'directory',
                                                values: () => {
                                                    return [
                                                        {
                                                            name: 'data',
                                                            kind: 'directory',
                                                            values: () => {
                                                                return [
                                                                    {
                                                                        name: 'ZAG_EOI_20141009_1.eaf',
                                                                        kind: 'file',
                                                                        getFile: async () => new File([''], 'ZAG_EOI_20141009_1.eaf')
                                                                    },
                                                                    {
                                                                        name: 'ZAG_EOI_20141009_1.wav',
                                                                        kind: 'file',
                                                                        getFile: async () => new File([''], 'ZAG_EOI_20141009_1.wav')
                                                                    }
                                                                ];
                                                            }
                                                        },
                                                        {
                                                            name: 'zag_eoi_20141009_1.xml',
                                                            kind: 'file',
                                                            getFile: async () => new File([''], 'zag_eoi_20141009_1.xml')
                                                        }
                                                    ];
                                                }
                                            }
                                        ];
                                    }
                                },
                                {
                                    name: '0=ocfl_object_1.0',
                                    kind: 'file',
                                    getFile: async () => new File([''], '0=ocfl_object_1.0')
                                },
                                {
                                    name: 'acl.json',
                                    kind: 'file',
                                    getFile: async () => new File([''], 'acl.json')
                                }
                            ];
                        }
                    }
                ];
            }
        };

        // Mock showDirectoryPicker
        window.showDirectoryPicker = jest.fn().mockResolvedValue(mockOcflStructure);

        // Mock fetch for presigned URLs
        global.fetch = jest.fn().mockResolvedValue({
            json: () => Promise.resolve({
                success: true,
                presigned_posts: [
                    { file_name: 'zag_eoi_20141009_1/v1/content/data/ZAG_EOI_20141009_1.eaf' },
                    { file_name: 'zag_eoi_20141009_1/v1/content/data/ZAG_EOI_20141009_1.wav' },
                    { file_name: 'zag_eoi_20141009_1/v1/content/zag_eoi_20141009_1.xml' },
                    { file_name: 'zag_eoi_20141009_1/0=ocfl_object_1.0' },
                    { file_name: 'zag_eoi_20141009_1/acl.json' }
                ]
            })
        });

        // Mock S3FolderUpload
        window.S3FolderUpload = {
            uploadFiles: jest.fn().mockResolvedValue({
                successful: 5,
                total: 5,
                failed: 0,
                processed_files: [
                    { file_name: 'zag_eoi_20141009_1/v1/content/data/ZAG_EOI_20141009_1.eaf' },
                    { file_name: 'zag_eoi_20141009_1/v1/content/data/ZAG_EOI_20141009_1.wav' },
                    { file_name: 'zag_eoi_20141009_1/v1/content/zag_eoi_20141009_1.xml' },
                    { file_name: 'zag_eoi_20141009_1/0=ocfl_object_1.0' },
                    { file_name: 'zag_eoi_20141009_1/acl.json' }
                ]
            })
        };

        // Mock notifyUploadComplete
        global.notifyUploadComplete = jest.fn().mockResolvedValue({ success: true });

        // Run the scan
        await scanFolder();

        // Get the request body from the fetch call
        const requestBody = JSON.parse(global.fetch.mock.calls[0][1].body);
        
        // Verify the folder structure
        expect(requestBody.files_metadata).toHaveLength(5);
        
        // Check each file's path
        const paths = requestBody.files_metadata.map(f => f.file_name);
        
        // Verify no path duplication
        paths.forEach(path => {
            const pathParts = path.split('/');
            const uniqueParts = new Set(pathParts);
            expect(pathParts.length).toBe(uniqueParts.size);
        });

        // Verify specific paths
        expect(paths).toContain('zag_eoi_20141009_1/v1/content/data/ZAG_EOI_20141009_1.eaf');
        expect(paths).toContain('zag_eoi_20141009_1/v1/content/data/ZAG_EOI_20141009_1.wav');
        expect(paths).toContain('zag_eoi_20141009_1/v1/content/zag_eoi_20141009_1.xml');
        expect(paths).toContain('zag_eoi_20141009_1/0=ocfl_object_1.0');
        expect(paths).toContain('zag_eoi_20141009_1/acl.json');

        // Verify no duplicate folder names in paths
        paths.forEach(path => {
            const parts = path.split('/');
            const folderNames = parts.slice(0, -1); // Exclude filename
            const uniqueFolderNames = new Set(folderNames);
            expect(folderNames.length).toBe(uniqueFolderNames.size);
        });
    });
}); 
