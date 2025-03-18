/**
 * Toggle the visibility of a folder's contents
 * @param {HTMLElement} button - The button element that was clicked
 */
export function toggleFolder(button) {
    // Find the folder contents element (next sibling after the div containing the button)
    const folderItem = button.closest('.folder-item');
    const folderContents = folderItem.querySelector('.folder-contents');
    
    // Toggle the visibility
    if (folderContents.classList.contains('hidden')) {
        // Show the folder contents
        folderContents.classList.remove('hidden');
        // Rotate the arrow icon
        button.querySelector('svg').classList.add('rotate-90');
    } else {
        // Hide the folder contents
        folderContents.classList.add('hidden');
        // Reset the arrow icon
        button.querySelector('svg').classList.remove('rotate-90');
    }
}