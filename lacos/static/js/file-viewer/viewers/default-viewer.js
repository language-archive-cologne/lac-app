import { escapeHtml, getLanguage } from '../utils.js';
import { modalManager } from '../../modal.js';

export function renderDefaultViewer(fileData) {
    try {
        const language = getLanguage(fileData);
        console.log('Content type:', fileData.type);
        console.log('Detected language:', language);
        console.log('Prism available:', !!window.Prism);
        console.log('Prism languages:', window.Prism ? Object.keys(Prism.languages) : 'No Prism');
        
        // Build the content HTML with proper Prism structure
        const contentHtml = `
            <div class="p-4">
                <div class="overflow-x-auto">
                    <pre><code class="language-${language}">${escapeHtml(fileData.content)}</code></pre>
                </div>
            </div>
            <div class="border-t p-4">
                <div class="text-sm text-gray-600">
                    <p>
                        Path: ${fileData.path}<br>
                        File Type: ${fileData.type}<br>
                        Last Modified: ${fileData.last_modified}<br>
                        Size: ${fileData.size} bytes
                    </p>
                </div>
            </div>
        `;
        
        modalManager.setContent(contentHtml);
        
        if (window.Prism) {
            console.log('Running Prism.highlightAll()');
            Prism.highlightAll();
            console.log('Prism highlighting complete');
        }
    } catch (e) {
        console.error('Error rendering content:', e);
        modalManager.setContent(`<div class="p-4">Error rendering content: ${e.message}</div>`);
    }
}
