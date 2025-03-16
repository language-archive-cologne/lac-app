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
});
