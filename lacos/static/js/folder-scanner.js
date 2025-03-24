/**
 * Folder Scanner
 * Uses the File System Access API to scan folders and prepare them for upload
 */

// Function to scan a folder and collect file paths
export async function scanFolder() {
    try {
      // Check if File System Access API is supported
      if (!window.showDirectoryPicker) {
        alert('Your browser does not support the File System Access API. Please use Chrome, Edge, or another Chromium-based browser.');
        return;
      }
      
      // Get all files from the directory picker
      const dirHandle = await window.showDirectoryPicker();
      const folderName = dirHandle.name || 'uploaded_folder';
      
      // Update folder name input if it's empty
      const folderNameInput = document.getElementById('folder_name');
      if (!folderNameInput.value.trim()) {
        folderNameInput.value = folderName;
      }
      
      // Show loading indicator
      console.log('Scanning folder structure...');
      if (window.updateUploadProgress) {
        window.updateUploadProgress('Scanning folder...', 10);
      }
      
      // Scan the folder structure
      const folderStructure = [];
      let totalSize = 0;
      await traverseDirectory(dirHandle, '', folderStructure);
      
      // Calculate total size
      folderStructure.forEach(file => {
        totalSize += file.size;
      });
      
      if (folderStructure.length === 0) {
        console.error('No files found in the selected folder');
        throw new Error('No files found in the selected folder');
      }
      
      console.log(`Found ${folderStructure.length} files in folder ${folderName}`);
      console.debug('First 5 files:', folderStructure.slice(0, 5));
      
      // Update UI with folder info
      if (window.updateFolderInfo) {
        window.updateFolderInfo(folderName, folderStructure.length, totalSize);
      }
      
      if (window.updateUploadProgress) {
        window.updateUploadProgress('Preparing upload...', 20);
      }
      
      // Transform the folder structure to match what the backend expects
      const filesMetadata = folderStructure.map(file => ({
        file_name: file.filename,  // Use just the filename, not the full path
        file_type: file.content_type,
        path: file.path,  // This contains the correct relative path
        size: file.size
      }));
      
      console.log('Sending metadata to server for', filesMetadata.length, 'files');
      console.debug('First 5 transformed files:', filesMetadata.slice(0, 5));
      
      // Send structure to your API
      const response = await fetch('/api/folder-upload-urls/', {
        method: 'POST',
        body: JSON.stringify({ 
          folder_name: folderNameInput.value.trim() || folderName,
          folder_structure: filesMetadata
        }),
        headers: { 
          'Content-Type': 'application/json',
          'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
        }
      });
      
      // Log the raw response for debugging
      console.log('API Response status:', response.status);
      
      const data = await response.json();
      console.log('API Response data:', data);
      
      if (!data.success) {
        console.error(`Failed to get upload URLs: ${data.error || 'Unknown error'}`);
        if (data.invalid_files) {
          console.error('Invalid files:', data.invalid_files);
        }
        throw new Error(`Failed to get upload URLs: ${data.error || 'Unknown error'}`);
      }
      
      // Use presigned_posts from the response - handle both formats
      const presignedPosts = data.presigned_posts || data.urls || [];
      
      console.log(`Received ${presignedPosts.length} presigned URLs for upload`);
      if (presignedPosts.length < filesMetadata.length) {
        console.warn(`Warning: Received fewer presigned URLs (${presignedPosts.length}) than files (${filesMetadata.length})`);
      }
      
      if (presignedPosts.length > 0) {
        console.debug('First presigned post:', presignedPosts[0]);
      } else {
        console.error('No presigned URLs received from server');
        throw new Error('No presigned URLs received from server');
      }
      
      if (window.updateUploadProgress) {
        window.updateUploadProgress('Uploading files...', 30);
      }
      
      // Upload files to their presigned URLs using the S3Uploader
      const uploadResult = await window.S3FolderUpload.uploadFiles(presignedPosts, dirHandle, {
        onProgress: (completed, total) => {
          if (window.updateUploadProgress) {
            const percent = 30 + ((completed / total) * 60); // Scale to 30-90%
            window.updateUploadProgress(`Uploading files (${completed}/${total})...`, percent);
          }
        }
      });
      
      console.log('Upload result:', uploadResult);
      
      if (window.updateUploadProgress) {
        window.updateUploadProgress('Processing files...', 90);
      }
      
      // Notify the server that upload is complete
      console.log('Notifying server that upload is complete...');
      const notificationResult = await notifyUploadComplete(folderName, uploadResult.processed_files);
      console.log('Complete notification result:', notificationResult);
      
      if (window.updateUploadProgress) {
        window.updateUploadProgress('Upload complete!', 100);
      }
      
      console.log('Folder upload complete!');
      
      // Show success message
      if (window.showSuccessMessage) {
        window.showSuccessMessage({
          successful: uploadResult.successful,
          total: uploadResult.total,
          failed: uploadResult.failed
        });
      }
      
    } catch (error) {
      console.error("Error processing folder:", error);
      
      // Show error in UI
      if (window.showErrorMessage) {
        window.showErrorMessage({
          message: error.message || 'An unknown error occurred'
        });
      }
      
      // Log additional details to help with debugging
      console.error('Error stack:', error.stack);
    }
  }
  
  // Recursively traverse directories
  export async function traverseDirectory(dirHandle, currentPath, folderStructure) {
    try {
      for await (const entry of dirHandle.values()) {
        // Skip the root folder name from the path
        if (entry.name === dirHandle.name) {
          continue;
        }

        if (entry.kind === 'file') {
          try {
            const file = await entry.getFile();
            const contentType = file.type || getContentTypeFromExtension(entry.name);
            
            // For files, use the current path as is
            folderStructure.push({
              path: currentPath,
              filename: entry.name,
              fullPath: currentPath ? `${currentPath}/${entry.name}` : entry.name,
              content_type: contentType,
              size: file.size
            });
            
            // Log every 100 files to avoid console flooding
            if (folderStructure.length % 100 === 0) {
              console.log(`Scanned ${folderStructure.length} files so far...`);
            }
          } catch (error) {
            console.error(`Error accessing file ${entry.name}:`, error);
          }
        } else if (entry.kind === 'directory') {
          // For directories, only append the directory name to the path
          const newPath = currentPath ? `${currentPath}/${entry.name}` : entry.name;
          await traverseDirectory(entry, newPath, folderStructure);
        }
      }
    } catch (error) {
      console.error(`Error traversing directory ${currentPath}:`, error);
    }
  }
  
  // Function to notify server that upload is complete
  export async function notifyUploadComplete(folderName, uploadedFiles) {
    console.log(`Notifying server about ${uploadedFiles.length} uploaded files in folder ${folderName}`);
    
    try {
        // Make sure we're sending the required parameters
        const data = {
            folder_name: folderName,
            uploaded_files: uploadedFiles
        };
        
        // Send the notification to the server
        const response = await fetch('/api/mark-upload-complete/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        console.log('Processing result:', result);
        return result;
    } catch (error) {
        console.error('Error notifying server about upload completion:', error);
        return { success: false, error: error.message };
    }
  }
  
  // Helper function to get CSRF token
  export function getCsrfToken() {
    return document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || 
           document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
  }
  
  // Helper function to get content type from file extension
  export function getContentTypeFromExtension(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    const mimeTypes = {
      'txt': 'text/plain',
      'html': 'text/html',
      'css': 'text/css',
      'js': 'application/javascript',
      'json': 'application/json',
      'xml': 'application/xml',
      'jpg': 'image/jpeg',
      'jpeg': 'image/jpeg',
      'png': 'image/png',
      'gif': 'image/gif',
      'svg': 'image/svg+xml',
      'pdf': 'application/pdf',
      'doc': 'application/msword',
      'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'xls': 'application/vnd.ms-excel',
      'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'ppt': 'application/vnd.ms-powerpoint',
      'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      'mp3': 'audio/mpeg',
      'mp4': 'video/mp4',
      'wav': 'audio/wav',
      'eaf': 'application/xml'
    };
    
    return mimeTypes[ext] || 'application/octet-stream';
  }

  function checkBrowserCompatibility() {
    if (!window.showDirectoryPicker) {
      document.getElementById('folder-select-button').style.display = 'none';
      document.getElementById('file-upload-container').innerHTML = `
        <div class="p-4 bg-red-50 text-red-700 rounded border border-red-200">
          <h3 class="font-medium mb-2">Browser Not Supported</h3>
          <p>Your browser does not support the File System Access API needed for folder uploads.</p>
          <p class="mt-2">Please use Chrome, Edge, or another Chromium-based browser.</p>
        </div>
      `;
      return false;
    }
    return true;
  }

  document.addEventListener('DOMContentLoaded', function() {
    checkBrowserCompatibility();
  });