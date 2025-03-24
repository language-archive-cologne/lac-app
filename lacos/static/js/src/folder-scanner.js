/**
 * Folder Scanner
 * Uses traditional file input for cross-browser folder upload support
 */

// Function to scan a folder and collect file paths
export async function scanFolder() {
    try {
      // Create file input for folder selection
      const input = document.createElement('input');
      input.type = 'file';
      input.webkitdirectory = true;
      input.multiple = true;
      
      // Wait for file selection
      const files = await new Promise((resolve) => {
        input.onchange = (e) => {
          const fileList = Array.from(e.target.files);
          // Get folder name from the first file's path
          const folderName = fileList[0]?.webkitRelativePath.split('/')[0] || 'uploaded_folder';
          
          // Transform files to match our structure
          const folderStructure = fileList.map(file => {
            const pathParts = file.webkitRelativePath.split('/');
            const fileName = pathParts.pop();
            const path = pathParts.slice(1).join('/'); // Remove root folder name
            
            return {
              path: path,
              filename: fileName,
              fullPath: pathParts.slice(1).concat(fileName).join('/'),
              content_type: file.type || getContentTypeFromExtension(fileName),
              size: file.size,
              file: file // Keep the actual File object for upload
            };
          });
          resolve({ folderName, folderStructure });
        };
        input.click();
      });
      
      if (!files.folderStructure || files.folderStructure.length === 0) {
        console.error('No files found in the selected folder');
        throw new Error('No files found in the selected folder');
      }
      
      // Calculate total size
      const totalSize = files.folderStructure.reduce((sum, file) => sum + file.size, 0);
      
      console.log(`Found ${files.folderStructure.length} files in folder ${files.folderName}`);
      console.debug('First 5 files:', files.folderStructure.slice(0, 5));
      
      // Update UI with folder info
      if (window.updateFolderInfo) {
        window.updateFolderInfo(files.folderName, files.folderStructure.length, totalSize);
      }
      
      if (window.updateUploadProgress) {
        window.updateUploadProgress('Preparing upload...', 20);
      }
      
      // Transform the folder structure to match what the backend expects
      const filesMetadata = files.folderStructure.map(file => ({
        file_name: file.fullPath,
        file_type: file.content_type,
        path: file.path,
        size: file.size
      }));
      
      console.log('Sending metadata to server for', filesMetadata.length, 'files');
      console.debug('First 5 transformed files:', filesMetadata.slice(0, 5));
      
      // Send structure to your API
      const response = await fetch('/storage/presigned-urls/', {
        method: 'POST',
        body: JSON.stringify({ 
          folder_name: files.folderName,
          files_metadata: filesMetadata
        }),
        headers: { 
          'Content-Type': 'application/json',
          'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      });
      
      const data = await response.json();
      console.log('API Response data:', data);
      
      if (!data.success) {
        console.error(`Failed to get upload URLs: ${data.error || 'Unknown error'}`);
        if (data.invalid_files) {
          console.error('Invalid files:', data.invalid_files);
        }
        throw new Error(`Failed to get upload URLs: ${data.error || 'Unknown error'}`);
      }
      
      // Use either presigned_posts or urls from the response
      const presignedPosts = data.presigned_posts || data.urls || [];
      
      console.log(`Received ${presignedPosts.length} presigned URLs for upload`);
      
      if (window.updateUploadProgress) {
        window.updateUploadProgress('Uploading files...', 30);
      }
      
      // Upload files to their presigned URLs using the S3Uploader
      const uploadResult = await window.S3FolderUpload.uploadFiles(presignedPosts, files.folderStructure, {
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
      const notificationResult = await notifyUploadComplete(files.folderName, uploadResult.processed_files);
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
      
      console.error('Error stack:', error.stack);
    }
}

// Function to notify server that upload is complete
export async function notifyUploadComplete(folderName, uploadedFiles) {
    console.log(`Notifying server about ${uploadedFiles.length} uploaded files in folder ${folderName}`);
    
    try {
        const data = {
            folder_name: folderName,
            uploaded_files: uploadedFiles
        };
        
        const response = await fetch('/storage/mark-uploads-complete/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
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
  const uploadContainer = document.getElementById('file-upload-container');
  if (!uploadContainer) return true;

  if (!window.showDirectoryPicker) {
    // For Firefox, Safari and other browsers
    const message = document.createElement('div');
    message.className = 'p-4 bg-blue-50 text-blue-700 rounded border border-blue-200 mb-4';
    message.innerHTML = `
      <h3 class="font-medium mb-2">Using Traditional Upload Method</h3>
      <p>Your browser will use the traditional folder upload method.</p>
      <p class="mt-2">For the best experience, consider using Chrome or Edge.</p>
    `;
    uploadContainer.insertBefore(message, uploadContainer.firstChild);
  }
  return true;
}

document.addEventListener('DOMContentLoaded', function() {
  checkBrowserCompatibility();
});