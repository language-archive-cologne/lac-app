// Mock the File System Access API
global.showDirectoryPicker = jest.fn();

// Mock the fetch API
global.fetch = jest.fn();

// Mock the window object
global.window = {
    updateUploadProgress: jest.fn(),
    updateFolderInfo: jest.fn(),
    showSuccessMessage: jest.fn(),
    showErrorMessage: jest.fn(),
    S3FolderUpload: {
        uploadFiles: jest.fn().mockResolvedValue({
            successful: 1,
            total: 1,
            failed: 0,
            processed_files: ['test.txt']
        })
    }
}; 