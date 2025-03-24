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
    const folderPath = folderItem.querySelector('.folder-name')?.dataset?.path || 'Unknown path';
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
    } else {
        // Hide the folder contents
        console.log(`Hiding contents of "${folderName}"`);
        folderContents.classList.add('hidden');
        // Reset the arrow icon
        button.querySelector('svg').classList.remove('rotate-90');
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

console.log('folder-manager.js initialization complete');