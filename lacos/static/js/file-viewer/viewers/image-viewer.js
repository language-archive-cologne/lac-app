import { modalManager } from '../../modal.js';

export function renderImageViewer(fileData) {
    const html = `
        <img src="data:${fileData.type};base64,${fileData.content}" 
             alt="Image" 
             style="max-width: 100%; max-height: 800px; object-fit: contain;">
        <div class="mt-4 text-sm text-gray-600">
            <p>File Type: ${fileData.type}</p>
            <p>Last Modified: ${fileData.last_modified}</p>
            <p>Size: ${fileData.size} bytes</p>
        </div>
    `;
    
    modalManager.setContent(html);
}
