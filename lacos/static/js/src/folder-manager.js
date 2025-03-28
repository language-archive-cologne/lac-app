// Debug logging
console.log('folder-manager.js loaded');

/**
 * Toggle the visibility of a folder's contents
 * @param {HTMLElement} button - The button element that was clicked
 */
export function toggleFolder(button) {
    console.log("Toggle folder clicked:", button);
    
    // Find the folder contents element (next sibling after the div containing the button)
    const folderItem = button.closest('.folder-item');
    console.log("Folder item found:", folderItem);
    
    const folderContents = folderItem.querySelector('.folder-contents');
    console.log("Folder contents element:", folderContents);
    
    if (!folderContents) {
        console.error("Could not find folder contents element!");
        return;
    }
    
    // Get folder name for debugging
    const folderName = folderItem.querySelector('.folder-name')?.textContent || 'Unknown folder';
    const folderPath = button.getAttribute('data-folder-path') || folderItem.querySelector('.folder-name')?.dataset?.path || 'Unknown path';
    console.log(`Toggling folder "${folderName}" (${folderPath})`);
    
    // Log the current children before toggling
    console.log(`Folder "${folderName}" children:`, folderContents.children.length);
    for (let i = 0; i < folderContents.children.length; i++) {
        console.log(`- Child ${i}:`, folderContents.children[i].outerHTML.substring(0, 100) + '...');
    }
    
    // Toggle the visibility
    if (folderContents.classList.contains('hidden')) {
        // Show the folder contents
        console.log(`Showing contents of "${folderName}"`);
        folderContents.classList.remove('hidden');
        // Rotate the arrow icon
        button.querySelector('svg').classList.add('rotate-90');
        // Update folder state data attribute
        if (button.hasAttribute('data-folder-path')) {
            button.setAttribute('data-folder-state', 'open');
        }
    } else {
        // Hide the folder contents
        console.log(`Hiding contents of "${folderName}"`);
        folderContents.classList.add('hidden');
        // Reset the arrow icon
        button.querySelector('svg').classList.remove('rotate-90');
        // Update folder state data attribute
        if (button.hasAttribute('data-folder-path')) {
            button.setAttribute('data-folder-state', 'closed');
        }
    }
}

/**
 * Expand all folders in the tree
 * @param {string} containerId - The ID of the container element (optional)
 */
export function expandAllFolders(containerId = null) {
    const container = containerId ? document.getElementById(containerId) : document;
    const buttons = container.querySelectorAll('.folder-toggle');
    
    console.log(`Expanding all folders (${buttons.length} found)`, { container, buttons });
    
    buttons.forEach((button, index) => {
        const folderItem = button.closest('.folder-item');
        const folderContents = folderItem.querySelector('.folder-contents');
        const folderName = folderItem.querySelector('.folder-name')?.textContent || `Folder #${index}`;
        
        if (folderContents && folderContents.classList.contains('hidden')) {
            console.log(`Expanding folder: "${folderName}"`);
            folderContents.classList.remove('hidden');
            button.querySelector('svg').classList.add('rotate-90');
        }
    });
    
    console.log('All folders expanded');
}

/**
 * Collapse all folders in the tree
 * @param {string} containerId - The ID of the container element (optional)
 */
export function collapseAllFolders(containerId = null) {
    const container = containerId ? document.getElementById(containerId) : document;
    const buttons = container.querySelectorAll('.folder-toggle');
    
    console.log(`Collapsing all folders (${buttons.length} found)`);
    
    buttons.forEach((button) => {
        const folderItem = button.closest('.folder-item');
        const folderContents = folderItem.querySelector('.folder-contents');
        
        if (folderContents && !folderContents.classList.contains('hidden')) {
            folderContents.classList.add('hidden');
            button.querySelector('svg').classList.remove('rotate-90');
        }
    });
    
    console.log('All folders collapsed');
}

/**
 * Handle folder toggle events
 */
export function initializeFolderManager() {
    // Handle before HTMX request
    document.body.addEventListener('htmx:beforeRequest', function(evt) {
        const button = evt.detail.elt;
        if (button.classList.contains('folder-toggle')) {
            console.log('Folder toggle request starting:', button);
            const currentState = button.getAttribute('data-folder-state');
            
            if (currentState === 'open') {
                // If currently open, just close it without making a request
                const folderContents = button.closest('.folder-item').querySelector('.folder-contents');
                folderContents.classList.add('hidden');
                button.querySelector('svg').classList.remove('rotate-90');
                button.setAttribute('data-folder-state', 'closed');
                evt.preventDefault(); // Prevent the HTMX request
            } else {
                // If closed, show loading state and make the request
                button.querySelector('svg').classList.add('rotate-90');
                button.setAttribute('data-folder-state', 'loading');
            }
        }
    });

    // Handle after HTMX request
    document.body.addEventListener('htmx:afterRequest', function(evt) {
        const button = evt.detail.elt;
        if (button.classList.contains('folder-toggle')) {
            console.log('Folder toggle request completed:', button);
            const folderContents = button.closest('.folder-item').querySelector('.folder-contents');
            
            if (evt.detail.successful) {
                console.log('Request successful, showing contents');
                folderContents.classList.remove('hidden');
                button.setAttribute('data-folder-state', 'open');
                // Keep the arrow rotated
                button.querySelector('svg').classList.add('rotate-90');
            } else {
                console.error('Request failed, hiding contents');
                folderContents.classList.add('hidden');
                button.querySelector('svg').classList.remove('rotate-90');
                button.setAttribute('data-folder-state', 'closed');
            }
        }
    });

    // Handle HTMX swap
    document.body.addEventListener('htmx:afterSwap', function(evt) {
        const button = evt.detail.elt;
        if (button.classList.contains('folder-toggle')) {
            console.log('Content swapped, updating UI');
            const folderContents = button.closest('.folder-item').querySelector('.folder-contents');
            if (folderContents && folderContents.children.length > 0) {
                folderContents.classList.remove('hidden');
                button.setAttribute('data-folder-state', 'open');
            }
        }
    });
}

// Initialize when the script loads
initializeFolderManager();

console.log('folder-manager.js initialization complete');