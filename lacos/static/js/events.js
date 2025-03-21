import { handleFileViewRequest } from './file-viewer/file-viewer-handler.js';

document.addEventListener('DOMContentLoaded', () => {
    // HTMX event handlers
    document.body.addEventListener('htmx:beforeRequest', (evt) => {
        console.log('HTMX Request starting:', evt.detail);
        evt.detail.xhr.setRequestHeader('X-HTMX-Indicator', 'none');
    });

    document.body.addEventListener('htmx:afterRequest', (evt) => {
        if (evt.detail.elt.classList.contains('view-icon')) {
            handleFileViewRequest(evt);
        }
    });

    document.body.addEventListener('htmx:afterSwap', (event) => {
        if (event.detail.target.id === 'ocfl-structure' || event.detail.target.id === 'staging-structure') {
            console.log('Folder structure updated');
        }
    });

    // Show loading indicator for HTMX requests
    document.body.addEventListener('htmx:beforeSend', function(event) {
        // Show the indicator if it exists and isn't explicitly disabled
        const indicator = document.getElementById('indicator');
        // Check if the indicator should be shown based on request headers
        const headers = event.detail.requestConfig.headers || {};
        if (indicator && headers['X-HTMX-Indicator'] !== 'none') {
            indicator.classList.remove('hidden');
        }
    });

    // Hide loading indicator after HTMX requests
    document.body.addEventListener('htmx:afterRequest', function(event) {
        // Hide the indicator
        const indicator = document.getElementById('indicator');
        if (indicator) {
            indicator.classList.add('hidden');
        }
        
        // Handle delete operations
        if (event.detail.successful && 
            (event.detail.xhr.status === 200 || event.detail.xhr.status === 204) && 
            (event.detail.requestConfig.verb === 'delete' || 
             (event.detail.requestConfig.verb === 'post' && 
              event.detail.requestConfig.path.includes('/delete/')))) {
            // If the parent element is a list item, remove it
            const listItem = event.detail.elt.closest('li');
            if (listItem) {
                listItem.remove();
            }
        }
    });

    // Handle HTMX errors
    document.body.addEventListener('htmx:responseError', function(event) {
        console.error('HTMX request failed:', event.detail);
        
        // Hide the indicator
        const indicator = document.getElementById('indicator');
        if (indicator) {
            indicator.classList.add('hidden');
        }
        
        // Show an error message
        const errorMessage = event.detail.xhr.responseText || 'An error occurred while processing your request.';
        alert('Error: ' + errorMessage);
    });

    // Handle HTMX swapping
    document.body.addEventListener('htmx:afterSwap', function(event) {
        // If the swap target is the upload status, scroll to it
        if (event.detail.target.id === 'upload-status') {
            event.detail.target.scrollIntoView({ behavior: 'smooth' });
        }
    });
});
