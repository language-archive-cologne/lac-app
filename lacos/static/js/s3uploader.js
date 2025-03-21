/**
 * S3 Upload Utility
 * Handles uploads to S3 using presigned URLs
 */
console.log('S3Uploader script loaded!');

// S3FolderUpload for File System API uploads
const S3FolderUpload = {
  /**
   * Upload files to S3 using presigned URLs and File System API
   * @param {Array} presignedPosts - Array of presigned URL data
   * @param {DirectoryHandle} rootDirHandle - Root directory handle from File System API
   * @param {Object} options - Configuration options
   */
  uploadFiles: async function(presignedPosts, rootDirHandle, options = {}) {
    let completed = 0;
    let errors = 0;
    const total = presignedPosts.length;
    const processed_files = [];
    const failed_files = [];
    
    console.log(`Starting upload of ${total} files to S3 using File System API`);
    console.debug('First URL sample:', presignedPosts[0]);
    
    // Create a map to track which files we need to find
    const fileMap = new Map();
    
    // Organize presigned posts by path for easier lookup
    for (const post of presignedPosts) {
      // Extract the filename from the path
      const pathParts = post.file_name.split('/');
      const fileName = pathParts.pop();
      const dirPath = pathParts.join('/');
      
      // Store in map with the directory path and filename as key
      fileMap.set(`${dirPath}/${fileName}`, post);
      fileMap.set(post.file_name, post); // Also store with the full path as key
    }
    
    console.log(`Organized ${fileMap.size} files for upload`);
    
    // Function to recursively process directories
    const processDirectory = async (dirHandle, currentPath = '') => {
      console.log(`Processing directory: ${currentPath || 'root'}`);
      
      for await (const entry of dirHandle.values()) {
        const entryPath = currentPath ? `${currentPath}/${entry.name}` : entry.name;
        
        if (entry.kind === 'file') {
          try {
            // Look up the presigned post for this file
            const post = fileMap.get(entryPath);
            
            if (!post) {
              console.warn(`No presigned URL found for file: ${entryPath}`);
              continue;
            }
            
            // Get the file
            const file = await entry.getFile();
            console.log(`Uploading file (${completed + 1}/${total}): ${entryPath} (${file.size} bytes)`);
            
            // Upload to S3
            const success = await this.uploadFileToS3(file, post);
            
            if (success) {
              // Determine the S3 key - it could be in different places depending on the response format
              const s3Key = post.s3_key || (post.fields && post.fields.key) || post.key || '';
              
              processed_files.push({
                file_name: post.file_name,
                s3_key: s3Key
              });
              completed++;
              
              // Report progress
              if (options.onProgress) {
                options.onProgress(completed, total);
              }
            } else {
              errors++;
              failed_files.push({
                file_name: post.file_name,
                error: 'Upload failed'
              });
            }
          } catch (error) {
            console.error(`Error uploading file ${entryPath}:`, error);
            errors++;
            failed_files.push({
              file_name: entryPath,
              error: error.message || 'Unknown error'
            });
          }
        } else if (entry.kind === 'directory') {
          // Process subdirectory
          await processDirectory(entry, entryPath);
        }
      }
    };
    
    try {
      // Start processing from the root directory
      await processDirectory(rootDirHandle);
      
      console.log(`Upload complete. ${completed} successful, ${errors} failed.`);
      
      return {
        successful: completed,
        failed: errors,
        total: total,
        processed_files: processed_files,
        failed_files: failed_files
      };
    } catch (error) {
      console.error('Error in uploadFiles:', error);
      throw error;
    }
  },
  
  // Upload a single file to S3
  uploadFileToS3: async function(file, post) {
    try {
      // Handle different response formats
      let url, fields;
      
      if (post.url && post.fields) {
        // Standard presigned post format
        url = post.url;
        fields = post.fields;
      } else if (post.presigned_url) {
        // Alternative format with presigned_url
        url = post.presigned_url;
        fields = post.fields || {};
      } else {
        console.error('Unrecognized presigned URL format:', post);
        throw new Error('Invalid presigned URL format');
      }
      
      if (!url) {
        console.error('Missing URL in presigned post data', post);
        throw new Error('Invalid presigned post data: missing URL');
      }
      
      // Create form data with all required fields
      const formData = new FormData();
      if (fields) {
        Object.entries(fields).forEach(([key, value]) => {
          formData.append(key, value);
        });
      }
      
      // Add the file as the last field
      formData.append('file', file);
      
      // Upload to S3
      console.debug(`Uploading to ${url}`);
      const response = await fetch(url, {
        method: 'POST',
        body: formData
      });
      
      // Check response
      if (!response.ok) {
        let responseText = '';
        try {
          responseText = await response.text();
        } catch (e) {
          responseText = 'Could not read response text';
        }
        
        console.error(`S3 upload failed with status ${response.status}:`, responseText);
        throw new Error(`Upload failed: ${response.status} ${response.statusText}`);
      }
      
      console.debug(`Successfully uploaded ${post.file_name}`);
      return true;
    } catch (error) {
      console.error(`Error uploading file ${post.file_name}:`, error);
      return false;
    }
  },
  
  // Verify uploads with server
  verifyUploads: async function(s3Keys, verifyEndpoint, csrfToken) {
    try {
      console.log(`Verifying ${s3Keys.length} uploaded files with server`);
      
      const response = await fetch(verifyEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken
        },
        body: JSON.stringify({ s3_keys: s3Keys })
      });
      
      const result = await response.json();
      console.log('Verification result:', result);
      
      return result;
    } catch (error) {
      console.error('Error verifying uploads:', error);
      throw error;
    }
  },
  
  // Helper function to report errors to server
  reportErrorToServer: async function(errorDetail, endpoint, csrfToken) {
    try {
      console.debug('Reporting error to server:', errorDetail);
      
      await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken
        },
        body: JSON.stringify(errorDetail)
      });
    } catch (e) {
      console.error('Failed to report error to server:', e);
    }
  }
};

// Make globally available
window.S3FolderUpload = S3FolderUpload;

// For backward compatibility, create S3Upload alias
window.S3Upload = {
  uploadFiles: function(presignedData, options = {}) {
    console.warn('S3Upload.uploadFiles is deprecated. Using S3FolderUpload instead');
    // Convert method is dummy - this is just for compatibility
    return { error: 'Use S3FolderUpload directly' };
  }
};
