/**
 * Tests for folder-scanner.js
 */

import { scanFolder } from '../../../static/js/folder-scanner.js';

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
        // Mock the fetch response for getting upload URLs
        global.fetch.mockResolvedValueOnce({
            json: () => Promise.resolve({
                success: true,
                presigned_posts: [
                    { url: 'http://test1.com', fields: {} },
                    { url: 'http://test2.com', fields: {} }
                ]
            })
        });

        // Mock the fetch response for marking upload complete
        global.fetch.mockResolvedValueOnce({
            json: () => Promise.resolve({
                success: true,
                processed_files: ['test.txt', 'subfolder/nested.txt']
            })
        });

        // Call the scanFolder function
        await scanFolder();

        // Log the folder structure for debugging
        console.log('Folder Structure:');
        console.log('----------------');
        console.log('Root folder name:', mockDirHandle.name);
        console.log('Root folder values:', Array.from(mockDirHandle.values()));
        
        // Log the API request
        const firstCall = global.fetch.mock.calls[0];
        const requestBody = JSON.parse(firstCall[1].body);
        console.log('\nAPI Request:');
        console.log('-------------');
        console.log('Folder name:', requestBody.folder_name);
        console.log('Folder structure:', JSON.stringify(requestBody.folder_structure, null, 2));

        // Verify the folder structure was correctly traversed
        expect(mockDirHandle.values).toHaveBeenCalled();
        expect(mockFileHandle.getFile).toHaveBeenCalled();

        // Verify the API calls
        expect(global.fetch).toHaveBeenCalledTimes(2);

        // Verify the first API call (getting upload URLs)
        expect(firstCall[0]).toBe('/api/folder-upload-urls/');
        
        // Verify folder structure
        expect(requestBody.folder_structure).toHaveLength(2);
        
        // Verify root level file
        expect(requestBody.folder_structure[0]).toEqual({
            file_name: 'test.txt',
            file_type: 'text/plain',
            path: '',
            size: 100
        });
        
        // Verify nested file
        expect(requestBody.folder_structure[1]).toEqual({
            file_name: 'subfolder/nested.txt',
            file_type: 'text/plain',
            path: 'subfolder',
            size: 200
        });
    });

    test('should handle complex folder structure with multiple levels', async () => {
        // Create a complex folder structure with multiple files at different levels
        const complexHandle = {
            kind: 'directory',
            name: 'root',
            values: jest.fn().mockImplementation(function* () {
                // Root level file
                yield {
                    kind: 'file',
                    name: 'root.txt',
                    getFile: jest.fn().mockResolvedValue({
                        size: 100,
                        type: 'text/plain'
                    })
                };
                
                // First level directory
                yield {
                    kind: 'directory',
                    name: 'level1',
                    values: jest.fn().mockImplementation(function* () {
                        // First level file
                        yield {
                            kind: 'file',
                            name: 'level1.txt',
                            getFile: jest.fn().mockResolvedValue({
                                size: 200,
                                type: 'text/plain'
                            })
                        };
                        
                        // Second level directory
                        yield {
                            kind: 'directory',
                            name: 'level2',
                            values: jest.fn().mockImplementation(function* () {
                                // Second level file
                                yield {
                                    kind: 'file',
                                    name: 'level2.txt',
                                    getFile: jest.fn().mockResolvedValue({
                                        size: 300,
                                        type: 'text/plain'
                                    })
                                };
                            })
                        };
                    })
                };
            })
        };

        // Mock showDirectoryPicker to return our complex structure
        global.showDirectoryPicker.mockResolvedValueOnce(complexHandle);

        // Mock API response
        global.fetch.mockResolvedValueOnce({
            json: () => Promise.resolve({
                success: true,
                presigned_posts: [
                    { url: 'http://test1.com', fields: {} },
                    { url: 'http://test2.com', fields: {} },
                    { url: 'http://test3.com', fields: {} }
                ]
            })
        });

        // Call scanFolder
        await scanFolder();

        // Log the complex structure for debugging
        console.log('\nComplex Folder Structure:');
        console.log('-------------------------');
        console.log('Root folder name:', complexHandle.name);
        console.log('Root folder values:', Array.from(complexHandle.values()));
        
        // Log the API request
        const firstCall = global.fetch.mock.calls[0];
        const requestBody = JSON.parse(firstCall[1].body);
        console.log('\nAPI Request:');
        console.log('-------------');
        console.log('Folder name:', requestBody.folder_name);
        console.log('Folder structure:', JSON.stringify(requestBody.folder_structure, null, 2));

        // Verify the complex structure was handled correctly
        expect(requestBody.folder_structure).toHaveLength(3);
        
        // Verify root level file
        expect(requestBody.folder_structure[0]).toEqual({
            file_name: 'root.txt',
            file_type: 'text/plain',
            path: '',
            size: 100
        });
        
        // Verify first level file
        expect(requestBody.folder_structure[1]).toEqual({
            file_name: 'level1/level1.txt',
            file_type: 'text/plain',
            path: 'level1',
            size: 200
        });
        
        // Verify second level file
        expect(requestBody.folder_structure[2]).toEqual({
            file_name: 'level1/level2/level2.txt',
            file_type: 'text/plain',
            path: 'level1/level2',
            size: 300
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
        // Create a file with no explicit type
        const noTypeHandle = {
            kind: 'file',
            name: 'test.xml',
            getFile: jest.fn().mockResolvedValue({
                size: 100,
                type: ''  // Empty type
            })
        };

        const dirHandle = {
            kind: 'directory',
            name: 'test_folder',
            values: jest.fn().mockImplementation(function* () {
                yield noTypeHandle;
            })
        };

        // Mock showDirectoryPicker
        global.showDirectoryPicker.mockResolvedValueOnce(dirHandle);

        // Mock API response
        global.fetch.mockResolvedValueOnce({
            json: () => Promise.resolve({
                success: true,
                presigned_posts: [{ url: 'http://test.com', fields: {} }]
            })
        });

        // Call scanFolder
        await scanFolder();

        // Verify content type was correctly determined from extension
        const requestBody = JSON.parse(global.fetch.mock.calls[0][1].body);
        expect(requestBody.folder_structure[0].file_type).toBe('application/xml');
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
}); 