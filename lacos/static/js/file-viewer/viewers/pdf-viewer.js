import { modalManager } from '../../modal.js';

export function renderPDFViewer(fileData) {
    const html = `
        <iframe src="${fileData.content}" width="100%" height="800px"></iframe>
        <div class="mt-4 text-sm text-gray-600">
            <p>File Type: ${fileData.type}</p>
            <p>Last Modified: ${fileData.last_modified}</p>
            <p>Size: ${fileData.size} bytes</p>
        </div>
    `;
    
    modalManager.setContent(html);
}
