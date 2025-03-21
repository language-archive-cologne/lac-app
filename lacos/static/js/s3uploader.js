/**
 * Minimal S3 Direct Upload Utility
 */
console.log('S3Uploader script loaded!');

const S3Upload = {
    /**
     * Start uploading files to S3 using presigned URLs
     * @param {Array} presignedData - Array of presigned URL data
     * @param {Object} options - Configuration options
     */
    uploadFiles: function(presignedData, options = {}) {
        console.log(`S3Upload.uploadFiles called with ${presignedData ? presignedData.length : 0} items`);
        
        const fileInput = document.getElementById(options.fileInputId || 'files');
        if (!fileInput) {
            console.error('File input element not found with ID:', options.fileInputId || 'files');
            if (options.onError) options.onError({ error: 'File input element not found' });
            return;
        }
        
        console.log(`File input has ${fileInput.files ? fileInput.files.length : 0} files`);
        
        // Debug file paths
        if (fileInput.files && fileInput.files.length > 0) {
            console.log('Available files in input:');
            for (let i = 0; i < fileInput.files.length; i++) {
                const file = fileInput.files[i];
                console.log(`- ${file.name} (${file.size} bytes) [webkitRelativePath: ${file.webkitRelativePath || 'N/A'}]`);
            }
        }
        
        const progressBar = document.getElementById(options.progressBarId || 'progress-bar');
        const progressText = document.getElementById(options.progressTextId || 'progress-text');
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        const verifyEndpoint = options.verifyEndpoint || '/storage/upload/complete/';
        const debugEndpoint = options.debugEndpoint || '/storage/upload/debug-error/';
        
        let completed = 0;
        let errors = 0;
        const total = presignedData.length;
        const s3Keys = [];
        const errorDetails = [];
        
        console.log(`Starting upload of ${total} files to S3`);
        
        // Upload each file
        presignedData.forEach(async (post) => {
            try {
                console.log(`Looking for file: ${post.file_name}`);
                
                // Find the file in the input
                let file = null;
                console.log(`Looking for file matching: ${post.file_name}`);
                
                // Log all available files for debugging
                console.log(`Available files (${fileInput.files.length}):`);
                for (let i = 0; i < fileInput.files.length; i++) {
                    const inputFile = fileInput.files[i];
                    const relativePath = inputFile.webkitRelativePath || '';
                    console.log(`${i}: ${inputFile.name} (${relativePath})`);
                }
                
                // Try various ways to match the file
                for (let i = 0; i < fileInput.files.length; i++) {
                    const inputFile = fileInput.files[i];
                    const relativePath = inputFile.webkitRelativePath || '';
                    const fileNameOnly = post.file_name.split('/').pop(); // Get just the filename without path
                    
                    // Try to match by exact filename
                    if (inputFile.name === post.file_name) {
                        console.log(`✅ Found exact match for ${post.file_name}`);
                        file = inputFile;
                        break;
                    }
                    // Try to match by end of relative path
                    else if (relativePath.endsWith(post.file_name)) {
                        console.log(`✅ Found path-end match for ${post.file_name}`);
                        file = inputFile;
                        break;
                    }
                    // Try to match relative path exactly
                    else if (relativePath === post.file_name) {
                        console.log(`✅ Found exact path match for ${post.file_name}`);
                        file = inputFile;
                        break;
                    }
                    // Try to match the last part of the file name (for cases like "0=ocfl_object_1.0")
                    else if (inputFile.name === fileNameOnly) {
                        console.log(`✅ Found match by filename (without path) for ${post.file_name} -> ${fileNameOnly}`);
                        file = inputFile;
                        break;
                    }
                    // For special cases like "0=ocfl_object_1.0"
                    else if (post.file_name.includes("=") && inputFile.name === post.file_name.split("=")[1]) {
                        console.log(`✅ Found special match for ${post.file_name} -> ${post.file_name.split("=")[1]}`);
                        file = inputFile;
                        break;
                    }
                    // Final fallback for "0=ocfl_object_1.0" special case
                    else if (post.file_name === "0=ocfl_object_1.0" && inputFile.name === "ocfl_object_1.0") {
                        console.log(`✅ Found hardcoded match for special OCFL file`);
                        file = inputFile;
                        break;
                    }
                }
                
                if (!file) {
                    console.error(`❌ File not found: ${post.file_name}`);
                    const error = {
                        file_name: post.file_name,
                        s3_key: post.s3_key, 
                        error: 'File not found in input'
                    };
                    errorDetails.push(error);
                    reportErrorToServer(error);
                    updateProgress();
                    return;
                }
                
                // Prepare form data
                console.log(`Preparing presigned POST for: ${post.file_name} → ${post.s3_key}`);
                
                // Log the complete post object structure for debugging
                console.log('Complete post object:', JSON.stringify(post, null, 2));
                
                // The server returns presigned_post which contains url and fields
                if (!post.presigned_post && !post.url) {
                    console.error(`Missing presigned_post or url property for ${post.file_name}`);
                    const error = {
                        file_name: post.file_name,
                        s3_key: post.s3_key, 
                        error: `Missing presigned_post or url property in data. Keys available: ${Object.keys(post).join(", ")}`
                    };
                    errorDetails.push(error);
                    reportErrorToServer(error);
                    updateProgress();
                    return;
                }
                
                // Get the url and fields from either presigned_post or directly from post
                const url = post.presigned_post ? post.presigned_post.url : post.url;
                const fields = post.presigned_post ? post.presigned_post.fields : post.fields;
                
                console.log(`URL: ${url}`);
                console.log(`Fields:`, fields);
                
                if (!fields) {
                    console.error(`Missing fields property for ${post.file_name}`);
                    const error = {
                        file_name: post.file_name,
                        s3_key: post.s3_key, 
                        error: `Missing fields property in presigned data. Data structure: ${JSON.stringify(post)}`
                    };
                    errorDetails.push(error);
                    reportErrorToServer(error);
                    updateProgress();
                    return;
                }
                
                const formData = new FormData();
                Object.entries(fields).forEach(([key, value]) => {
                    formData.append(key, value);
                });
                formData.append('file', file);
                
                // Upload to S3
                console.log(`Sending POST request to S3 for ${post.file_name}`);
                try {
                    const response = await fetch(url, {
                        method: 'POST',
                        body: formData
                    });
                    
                    if (response.ok) {
                        console.log(`✅ Uploaded: ${post.file_name} → ${post.s3_key}, Status: ${response.status}`);
                        s3Keys.push(post.s3_key);
                    } else {
                        const responseText = await response.text();
                        console.error(`❌ Failed to upload: ${post.file_name}, Status: ${response.status}`);
                        console.error(`Response: ${responseText}`);
                        
                        const error = {
                            file_name: post.file_name,
                            s3_key: post.s3_key,
                            error: `HTTP ${response.status}: ${responseText}`
                        };
                        errorDetails.push(error);
                        reportErrorToServer(error);
                        errors++;
                    }
                } catch (fetchError) {
                    console.error(`❌ Fetch error for ${post.file_name}:`, fetchError);
                    
                    const error = {
                        file_name: post.file_name,
                        s3_key: post.s3_key,
                        error: `Fetch error: ${fetchError.message}`
                    };
                    errorDetails.push(error);
                    reportErrorToServer(error);
                    errors++;
                }
            } catch (error) {
                console.error(`Error processing ${post.file_name}:`, error);
                
                const errorDetail = {
                    file_name: post.file_name,
                    s3_key: post.s3_key || 'unknown',
                    error: `Processing error: ${error.message}`
                };
                errorDetails.push(errorDetail);
                reportErrorToServer(errorDetail);
                errors++;
            }
            
            updateProgress();
        });
        
        // Report errors to server for debugging
        async function reportErrorToServer(errorDetail) {
            try {
                await fetch(debugEndpoint, {
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
        
        // Update progress and verify when done
        function updateProgress() {
            completed++;
            
            // Update progress UI
            if (progressBar) {
                const percent = (completed / total) * 100;
                progressBar.style.width = `${percent}%`;
                if (progressText) progressText.textContent = `${Math.round(percent)}%`;
            }
            
            // When all uploads complete, verify with server
            if (completed === total) {
                console.log(`All ${completed} uploads processed, ${s3Keys.length} successful, ${errors} failed`);
                
                if (errors > 0) {
                    console.error('Some files failed to upload:', errorDetails);
                }
                
                if (s3Keys.length > 0) {
                    verifyUploads(s3Keys);
                } else {
                    const errorMsg = {
                        error: 'No files were successfully uploaded',
                        details: errorDetails
                    };
                    console.error(errorMsg.error, errorDetails);
                    if (options.onError) options.onError(errorMsg);
                    
                    // Also send to the server for better debugging
                    reportErrorToServer({
                        file_name: 'all_files',
                        s3_key: 'none',
                        error: errorMsg.error,
                        details: errorDetails
                    });
                }
            }
        }
        
        // Verify uploads with server
        async function verifyUploads(keys) {
            try {
                console.log(`Verifying ${keys.length} uploaded files with server: ${verifyEndpoint}`);
                console.log('S3 Keys:', keys);
                
                const response = await fetch(verifyEndpoint, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify({ s3_keys: keys })
                });
                
                console.log(`Verification response status: ${response.status}`);
                const result = await response.json();
                console.log('Verification result:', result);
                
                if (result.success) {
                    console.log(`Verified ${result.total_verified} files (${result.total_size_formatted})`);
                    if (options.onComplete) options.onComplete(result);
                } else {
                    console.error('Verification failed:', result.error);
                    if (options.onError) options.onError(result);
                }
            } catch (error) {
                console.error('Error verifying uploads:', error);
                if (options.onError) options.onError({ error: error.message });
            }
        }
    }
};

// Make it globally available
window.S3Upload = S3Upload;
